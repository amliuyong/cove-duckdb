"""Actual local Chromium with a synthetic Query API; not AWS acceptance."""
import copy
import importlib.util
import json
import re
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "infra/web"
DECIMAL = "999999999999999999999999999999999999.99"
DATA = [[str(9007199254740993 + number), DECIMAL,
         "<img src=x onerror=window.PWNED=1>" if number == 0 else "row " + str(number)]
        for number in range(205)]
COLUMNS = [{"name": name, "type": kind, "nullable": False, "encoding": encoding}
           for name, kind, encoding in [
               ("id", "BIGINT", "native_text"), ("amount", "DECIMAL(38,2)", "native_text"),
               ("note", "VARCHAR", "native_json")]]
VERSIONS = [{"dataset": "dwd.result", "release_id": "release_fixture",
             "generation": "gen_fixture", "commit_sequence": 17, "snapshot_sequence": 19}]
DEPLOYMENT_SPEC = importlib.util.spec_from_file_location("editor_browser_template", ROOT / "infra/template.py")
DEPLOYMENT = importlib.util.module_from_spec(DEPLOYMENT_SPEC)
DEPLOYMENT_SPEC.loader.exec_module(DEPLOYMENT)
CSP = DEPLOYMENT.template()["Resources"]["Headers"]["Properties"]["ResponseHeadersPolicyConfig"][
    "SecurityHeadersConfig"]["ContentSecurityPolicy"]["ContentSecurityPolicy"]


class Fixture:
    def __init__(self):
        self.requests, self.jobs, self.nonces = [], {}, {}
        self.lose_reply, self.unavailable, self.expired = False, False, False
        self.rejection, self.lossy_result = None, False
        self.denial_html = False

    def handle(self, method, path, key, body):
        parsed = urlsplit(path)
        fields = parsed.path.split("/")
        options = parse_qs(parsed.query)
        self.requests.append({"method": method, "path": path, "key": key, "body": body})
        if len(fields) < 5 or fields[:3] != ["", "v1", "spaces"] or fields[3] != "analysis":
            return 403, {"code": "FORBIDDEN"}
        if key not in {"fixture_owner", "fixture_other"}:
            return 403, {"code": "FORBIDDEN"}
        if fields[4] == "catalog":
            return 200, {"datasets": [{"dataset": "dwd.result", "schema": [
                {name: column[name] for name in ["name", "type", "nullable"]} for column in COLUMNS]}]}
        if len(fields) == 5:
            if method == "GET":
                return 200, {"queries": [self.metadata(job) for job in self.jobs.values() if job["owner"] == key]}
            if self.rejection:
                return self.rejection, {"code": "QUERY_QUEUE_QUOTA" if self.rejection == 429 else "FORBIDDEN"}
            nonce = key, body["client_request_id"]
            if nonce in self.nonces:
                job = self.jobs[self.nonces[nonce]]
                if job["body"] != body:
                    return 409, {"code": "QUERY_IDEMPOTENCY_CONFLICT"}
            else:
                identity = "query_" + str(len(self.jobs) + 1)
                job = {"query_id": identity, "owner": key, "body": copy.deepcopy(body),
                       "status": "QUEUED", "reads": 0, "rows": copy.deepcopy(DATA)}
                self.jobs[identity] = job
                self.nonces[nonce] = identity
            result = {"query_id": job["query_id"], "status": job["status"],
                      "status_url": "/v1/spaces/analysis/queries/" + job["query_id"]}
            if self.lose_reply:
                self.lose_reply = False
                return None, result
            return 202, result
        identity = fields[5]
        if self.denial_html:
            return 403, "<html><body>Forbidden</body></html>"
        job = self.jobs.get(identity)
        if not job or job["owner"] != key:
            return 403, {"code": "QUERY_OWNER_REQUIRED"}
        if len(fields) == 7 and fields[6] == "cancel":
            if job["status"] not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                job["status"] = "CANCELLED"
            return 200, {"query_id": identity, "status": job["status"]}
        if len(fields) == 7 and fields[6] == "export":
            if self.expired:
                return 410, {"code": "QUERY_LINK_EXPIRED"}
            return 200, {"columns": COLUMNS, "rows": job["rows"],
                         "data_versions": VERSIONS, "truncated": False}
        if options.get("view") == ["sql"]:
            return 200, {**self.metadata(job), "view": "sql", "sql": job["body"]["sql"]}
        if self.unavailable:
            self.unavailable = False
            return 503, {"code": "QUERY_STATE_UNAVAILABLE"}
        if job["status"] != "CANCELLED":
            sql = job["body"]["sql"]
            job["status"] = ("UNKNOWN" if "unknown" in sql else "RUNNING" if "slow" in sql
                             else "FAILED" if "timeout" in sql else "SUCCEEDED")
        result = self.metadata(job)
        if job["status"] == "SUCCEEDED" and options.get("view") == ["result"]:
            index = int(options.get("page_token", ["0"])[0])
            size = int(options.get("page_size", ["100"])[0])
            rows = job["rows"][index:index + size]
            if self.lossy_result and rows:
                rows = copy.deepcopy(rows)
                rows[0][0] = int(rows[0][0])
            result.update(view="result", columns=COLUMNS, rows=rows,
                          data_versions=VERSIONS, row_count=len(job["rows"]), truncated=False,
                          next_page_token=str(index + size) if index + size < len(job["rows"]) else None,
                          export_url="https://gateway.invalid/v1/spaces/analysis/queries/" + identity
                          + "/export?token=fixture_export_token")
        return 200, result

    @staticmethod
    def metadata(job):
        result = {"query_id": job["query_id"], "status": job["status"],
                  "view": "metadata", "elapsed_ms": 25}
        if job["status"] == "FAILED":
            result["error_code"] = "QUERY_TIMEOUT"
        return result


def handler(fixture):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            path = urlsplit(self.path).path
            if path.startswith("/v1/"):
                self.server.cookies.append(self.headers.get("Cookie"))
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size)) if size else None
                key = self.headers.get("Authorization", "").removeprefix("Bearer ")
                status, value = fixture.handle(self.command, self.path, key, body)
                if status is None:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                raw, content_type = (value.encode(), "text/html") if isinstance(value, str) else (
                    json.dumps(value).encode(), "application/json")
            else:
                file = (WEB / (path.lstrip("/") or "index.html")).resolve()
                if not file.is_relative_to(WEB) or not file.is_file():
                    status, raw, content_type = 404, b"", "text/plain"
                else:
                    status, raw = 200, file.read_bytes()
                    content_type = {".html": "text/html", ".js": "application/javascript",
                                    ".css": "text/css"}[file.suffix]
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(raw)

        do_GET = dispatch
        do_POST = dispatch
    return Handler


class EditorBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.fixture = Fixture()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.fixture))
        self.server.cookies = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.context = self.browser.new_context(accept_downloads=True, viewport={"width": 1365, "height": 930})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.context.add_cookies([{"name": "unused_cookie", "value": "fixture", "url": self.url}])
        self.page.goto(self.url)
        self.connect()
        self.page.select_option("#consistency", "current")

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertTrue(all(cookie is None for cookie in self.server.cookies))
        self.context.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def connect(self, key="fixture_owner"):
        self.page.fill("#space", "analysis")
        self.page.fill("#api-key", key)
        self.page.click("#connect")
        self.page.wait_for_selector("#workspace", state="visible")

    def submit_query(self, sql="SELECT * FROM dwd.result;"):
        self.page.fill("#sql", sql)
        self.page.click("#run")

    def result(self):
        self.page.wait_for_selector("#results tbody tr")

    def test_pages_and_export_preserve_exact_values_and_do_not_resubmit(self):
        self.submit_query()
        self.result()
        self.assertEqual(self.page.locator("#results tbody tr").count(), 100)
        cells = self.page.locator("#results tbody tr").first.locator("td")
        self.assertEqual(cells.nth(0).inner_text(), "9007199254740993")
        self.assertEqual(cells.nth(1).inner_text(), DECIMAL)
        self.assertEqual(self.page.locator("#results img").count(), 0)
        self.assertIsNone(self.page.evaluate("window.PWNED"))
        self.page.click("#next-page")
        expect(self.page.locator("#page-info")).to_contain_text("第 2 页")
        self.page.click("#next-page")
        expect(self.page.locator("#page-info")).to_contain_text("第 3 页")
        self.assertEqual(self.page.locator("#results tbody tr").count(), 5)
        self.page.click("#previous-page")
        expect(self.page.locator("#page-info")).to_contain_text("第 2 页")
        with self.page.expect_download() as download:
            self.page.click("#export")
        exported = json.loads(Path(download.value.path()).read_text())
        self.assertEqual(exported["rows"], DATA)
        self.assertEqual(exported["data_versions"], VERSIONS)
        self.assertEqual(len([call for call in self.fixture.requests if call["method"] == "POST"]), 1)

    def test_lost_admission_reply_retries_same_request_and_keeps_identity(self):
        self.fixture.lose_reply = True
        self.submit_query()
        self.page.wait_for_selector("#retry-submit", state="visible")
        expect(self.page.locator("#retry-submit")).to_be_enabled()
        self.assertTrue(self.page.locator("#run").is_disabled())
        original = copy.deepcopy(next(call["body"] for call in self.fixture.requests if call["method"] == "POST"))
        self.assertIn(original["client_request_id"], self.page.locator("#query-meta").inner_text())
        self.page.fill("#sql", "SELECT different_input;")
        self.page.click("#retry-submit")
        self.result()
        bodies = [call["body"] for call in self.fixture.requests if call["method"] == "POST"]
        self.assertEqual(bodies, [original, original])
        self.assertEqual(len(self.fixture.jobs), 1)
        self.assertIn("query_1", self.page.locator("#query-meta").inner_text())

    def test_lost_reply_then_throttled_retry_keeps_original_admitted_request(self):
        self.fixture.lose_reply = True
        self.submit_query()
        expect(self.page.locator("#retry-submit")).to_be_enabled()
        original = copy.deepcopy(next(call["body"] for call in self.fixture.requests if call["method"] == "POST"))
        self.fixture.rejection = 429
        self.page.click("#retry-submit")
        expect(self.page.locator("#notice")).to_contain_text("QUERY_QUEUE_QUOTA")
        self.assertTrue(self.page.locator("#run").is_disabled())
        self.assertIn(original["client_request_id"], self.page.locator("#query-meta").inner_text())
        self.fixture.rejection = None
        self.page.click("#retry-submit")
        self.result()
        self.assertEqual(len(self.fixture.jobs), 1)
        self.assertEqual([call["body"] for call in self.fixture.requests if call["method"] == "POST"],
                         [original, original, original])

    def test_unknown_and_timeout_are_actual_states_and_cancel_preserves_query_id(self):
        self.submit_query("SELECT unknown;")
        self.page.wait_for_selector('#query-meta [data-status="UNKNOWN"]')
        self.assertIn("query_1", self.page.locator("#query-meta").inner_text())
        self.page.click("#cancel")
        self.page.wait_for_selector('#query-meta [data-status="CANCELLED"]')
        self.assertIn("query_1", self.page.locator("#query-meta").inner_text())
        self.submit_query("SELECT timeout;")
        self.page.wait_for_selector('#query-meta [data-status="FAILED"]')
        self.assertIn("QUERY_TIMEOUT", self.page.locator("#query-meta").inner_text())
        self.assertEqual(self.page.locator("#results tbody tr").count(), 0)

    def test_unavailable_observation_keeps_query_identity_without_fabricating_unknown(self):
        self.fixture.unavailable = True
        self.submit_query()
        expect(self.page.locator("#query-meta")).to_contain_text("当前状态待核对")
        self.assertIn("query_1", self.page.locator("#query-meta").inner_text())
        self.assertEqual(self.page.locator('#query-meta [data-status="UNKNOWN"]').count(), 0)
        self.page.click("#refresh-query")
        self.result()

    def test_reconnect_clears_sql_results_and_never_persists_credentials(self):
        self.submit_query()
        self.result()
        self.page.click("#restore-sql")
        expect(self.page.locator("#sql")).to_have_value(re.compile("dwd.result"))
        self.assertEqual(self.page.evaluate("JSON.stringify(localStorage)"), "{}")
        self.assertEqual(self.page.evaluate("JSON.stringify(sessionStorage)"), "{}")
        self.page.click("#disconnect")
        self.connect("fixture_other")
        self.assertEqual(self.page.locator("#sql").input_value(), "")
        self.assertEqual(self.page.locator("#results tbody tr").count(), 0)
        self.assertEqual(self.page.locator("#history .history-item").count(), 0)
        status, value = self.fixture.handle("GET", "/v1/spaces/analysis/queries/query_1?view=sql",
                                            "fixture_other", None)
        self.assertEqual((status, value["code"]), (403, "QUERY_OWNER_REQUIRED"))

    def test_browser_back_requires_reauthentication_and_has_no_previous_sql_or_results(self):
        self.submit_query()
        self.result()
        self.page.goto("about:blank")
        self.page.go_back()
        expect(self.page.locator("#connection")).to_be_visible()
        self.assertTrue(self.page.locator("#workspace").is_hidden())
        self.assertEqual(self.page.locator("#sql").input_value(), "")
        self.assertEqual(self.page.locator("#api-key").input_value(), "")
        self.assertEqual(self.page.locator("#results tbody tr").count(), 0)
        self.assertEqual(self.fixture.jobs["query_1"]["status"], "SUCCEEDED")

    def test_authorized_completion_and_explain_use_real_query_request_shape(self):
        self.page.fill("#sql", "SELECT * FROM dw")
        self.page.locator("#sql").press("Control+Space")
        self.page.wait_for_selector("#completion", state="visible")
        self.page.locator("#sql").press("Enter")
        self.assertIn('"dwd"."result"', self.page.locator("#sql").input_value())
        self.page.click("#explain")
        self.result()
        posted = next(call["body"] for call in self.fixture.requests if call["method"] == "POST")
        self.assertTrue(posted["sql"].startswith("EXPLAIN SELECT"))
        self.assertEqual(posted["consistency"], "current")

    def test_highlighting_preserves_sql_literals_comments_selection_and_scroll(self):
        sql = "SELECT 9007199254740993 AS \"FROM\", '<img onerror=window.PWNED=1>'; -- SELECT in comment"
        self.page.fill("#sql", sql)
        self.assertEqual(self.page.locator("#sql-highlight").inner_text(), sql + "\n")
        self.assertEqual(self.page.locator("#sql-highlight .sql-keyword").all_text_contents(), ["SELECT", "AS"])
        self.assertEqual(self.page.locator("#sql-highlight img").count(), 0)
        self.page.locator("#sql").press("Control+Enter")
        self.result()
        posted = next(call["body"] for call in self.fixture.requests if call["method"] == "POST")
        self.assertEqual(posted["sql"], sql)
        self.page.fill("#sql", "SELECT 1;\nSELECT 2;")
        self.page.locator("#sql").press("Control+Home")
        self.page.locator("#sql").press("Shift+End")
        self.page.locator("#sql").press("Control+Enter")
        self.result()
        self.assertEqual([call["body"] for call in self.fixture.requests if call["method"] == "POST"][-1]["sql"],
                         "SELECT 1;")
        self.assertEqual(self.page.locator("#sql").input_value(), "SELECT 1;\nSELECT 2;")
        long_sql = ("-- wide " + "x" * 300 + "\n") * 30
        self.page.fill("#sql", long_sql)
        self.page.locator("#sql").press("Control+End")
        scroll = self.page.evaluate("({editor: document.getElementById('sql').scrollTop, "
                                   "layer: document.getElementById('sql-highlight').scrollTop})")
        self.assertGreater(scroll["editor"], 0)
        self.assertEqual(scroll["editor"], scroll["layer"])
        self.page.click("#disconnect")
        self.assertEqual(self.page.locator("#sql-highlight").text_content(), "\n")

    def test_confirmed_rejection_preserves_client_identity_and_allows_a_new_request(self):
        self.fixture.rejection = 429
        self.submit_query()
        expect(self.page.locator("#notice")).to_contain_text("QUERY_QUEUE_QUOTA")
        original = self.fixture.requests[-1]["body"]
        self.assertIn(original["client_request_id"], self.page.locator("#notice").inner_text())
        self.assertEqual(self.fixture.jobs, {})
        expect(self.page.locator("#run")).to_be_enabled()
        self.assertTrue(self.page.locator("#retry-submit").is_hidden())
        self.fixture.rejection = None
        self.page.click("#run")
        self.result()
        posted = [call["body"] for call in self.fixture.requests if call["method"] == "POST"]
        self.assertNotEqual(posted[0]["client_request_id"], posted[1]["client_request_id"])

    def test_expired_export_clears_result_and_retains_original_query(self):
        self.submit_query()
        self.result()
        self.fixture.expired = True
        self.page.click("#export")
        expect(self.page.locator("#notice")).to_contain_text("QUERY_LINK_EXPIRED")
        self.assertIn("query_1", self.page.locator("#query-meta").inner_text())
        self.assertEqual(self.page.locator("#results tbody tr").count(), 0)
        self.assertTrue(self.page.locator("#export").is_disabled())
        self.assertEqual(len(self.fixture.jobs), 1)

    def test_native_text_numeric_encoding_is_rejected_without_showing_rounded_values(self):
        self.fixture.lossy_result = True
        self.submit_query()
        expect(self.page.locator("#query-meta")).to_contain_text("当前状态待核对")
        self.assertEqual(self.page.locator("#results tbody tr").count(), 0)
        self.assertIn("query_1", self.page.locator("#query-meta").inner_text())

    def test_non_json_authorization_failure_clears_results_and_preserves_query_identity(self):
        self.submit_query()
        self.result()
        self.fixture.denial_html = True
        self.page.click("#refresh-query")
        expect(self.page.locator("#notice")).to_contain_text("REQUEST_FAILED")
        self.assertEqual(self.page.locator("#results tbody tr").count(), 0)
        self.assertIn("query_1", self.page.locator("#query-meta").inner_text())

    def test_consistency_modes_submit_only_the_selected_condition(self):
        for mode, field, identity in [
                ("published", "release_id", "release_fixture"),
                ("after_write", "write_id", "write_fixture"),
                ("after_ingestion", "ingestion_id", "ing_fixture")]:
            self.page.select_option("#consistency", mode)
            self.page.fill("#condition-id", identity)
            self.submit_query()
            self.result()
            posted = [call["body"] for call in self.fixture.requests if call["method"] == "POST"][-1]
            self.assertEqual(posted["consistency"], mode)
            self.assertEqual({name: posted[name] for name in ["release_id", "write_id", "ingestion_id"]
                              if name in posted}, {field: identity})
        self.page.select_option("#consistency", "current")
        self.assertTrue(self.page.locator("#condition-id").is_disabled())
        self.assertEqual(self.page.locator("#condition-id").input_value(), "")


if __name__ == "__main__":
    unittest.main()
