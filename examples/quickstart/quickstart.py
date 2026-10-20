#!/usr/bin/env python3
"""Cove DuckDB quickstart: the documented API, SQL and Python examples against one installed environment.

Given the API URL, a new space and its bootstrap administrator token (scripts/aws/control.py bootstrap-key), it:
creates role keys, registers the datasets of examples/orders, builds the two runtime environments, publishes
and runs the orders SQL + pandas pipeline, ingests the documented events, writes a direct table row
synchronously and reads it back after_write, and checks the published ADS dashboard equals the documented
result. Every response is printed; any difference exits non-zero. Standard library plus PyYAML only.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

ORDERS = Path(__file__).resolve().parents[1] / "orders"
EXPECTED_DASHBOARD = [["2026-10-14", "610.00", 3, 1], ["2026-10-15", "50.00", 1, 0]]
EVENTS = [(1, 1, "2026-10-14", "10.00", "upsert"), (1, 2, "2026-10-14", "12.34", "upsert"),
          (2, 1, "2026-10-14", "600.00", "upsert"), (3, 1, "2026-10-14", "-2.34", "upsert"),
          (4, 1, "2026-10-14", "100.00", "upsert"), (4, 2, "2026-10-14", "100.00", "delete"),
          (5, 1, "2026-10-15", "50.00", "upsert")]
ENVIRONMENTS = {"pandas-demo": "numpy==2.2.6\npandas==2.2.3\npyarrow==24.0.0\n",
                "sql-demo": "duckdb==1.5.6\npyarrow==24.0.0\n"}


class Api:
    def __init__(self, url):
        self.url = url.rstrip("/")

    def __call__(self, method, path, token, body=None, headers=None, expected=(200,)):
        request = Request(self.url + path, method=method, data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + token,
                                   **(headers or {})})
        try:
            with urlopen(request, timeout=60) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        value = json.loads(raw) if raw else None
        print(json.dumps({"request": method + " " + path, "status": status}), flush=True)
        if status not in expected:
            raise SystemExit(method + " " + path + " -> " + str(status) + " " + json.dumps(value)[:400])
        return value


def column(name, kind, nullable=False):
    return {"name": name, "type": kind, "nullable": nullable}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--space", required=True)
    parser.add_argument("--admin-token-file", type=Path, required=True)
    args = parser.parse_args()
    api, space, admin = Api(args.api_url), args.space, args.admin_token_file.read_text().strip()
    expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 6 * 3600))
    tokens = {}
    for name, scopes in [("developer", ["datasets:manage", "pipeline:manage", "pipeline:run", "runtime:manage",
                                        "monitor:read"]),
                         ("ingest", ["ingest:write"]), ("writer", ["data:write", "query:read"]),
                         ("analyst", ["query:read"])]:
        tokens[name] = api("POST", f"/v1/admin/spaces/{space}/api-keys", admin,
                           {"name": "quickstart-" + name, "scopes": scopes, "expires_at": expires},
                           expected=(201,))["token"]
    definition = yaml.safe_load((ORDERS / "pipeline.yaml").read_text())
    definition["schedule"] = {"owner": "none"}
    configuration = api("GET", f"/v1/admin/spaces/{space}/configuration", admin)
    datasets = [{"dataset": "ods.orders", "schema_version": 1, "write_owner": "ingestion",
                 "schema": [column("event_id", "VARCHAR"), column("order_id", "BIGINT"),
                            column("source_version", "BIGINT"), column("event_time", "TIMESTAMP"),
                            column("amount", "DECIMAL(18,2)")],
                 "key_columns": ["order_id"], "partition_columns": [],
                 "ingestion": {"operations": ["upsert", "delete"], "event_id_column": "event_id",
                               "source_version_column": "source_version"}},
                {"dataset": "dwd.accounts", "schema_version": 1, "write_owner": "direct",
                 "schema": [column("id", "BIGINT"), column("name", "VARCHAR"), column("balance", "DECIMAL(18,2)")],
                 "key_columns": ["id"], "partition_columns": [], "constraints": {"primary_key": ["id"]}}]
    for task in definition["tasks"]:
        output = task["output"]
        datasets.append({"dataset": output["dataset"], "schema_version": 1, "write_owner": "pipeline",
                         "schema": output["schema"], "key_columns": output["key_columns"], "partition_columns": []})
    for value in datasets:
        configuration = api("GET", f"/v1/admin/spaces/{space}/configuration", admin)
        api("POST", f"/v1/admin/spaces/{space}/datasets", admin, value,
            {"If-Match": '"' + configuration["generation"] + '"'}, expected=(201,))
    developer = tokens["developer"]
    for environment, requirements in ENVIRONMENTS.items():
        api("POST", f"/v1/spaces/{space}/runtime-environments", developer, {
            "environment_id": environment, "version": "v1", "python_version": "3.12", "platform": "linux_arm64",
            "build_profile": "binary_wheels", "dependency_source": {"format": "requirements", "content": requirements}},
            expected=(201,))
        api("POST", f"/v1/spaces/{space}/runtime-environments/{environment}/versions/v1/build", developer, None,
            {"Idempotency-Key": "quickstart-" + environment}, expected=(202,))
    for environment in ENVIRONMENTS:
        deadline = time.time() + 1800
        while True:
            status = api("GET", f"/v1/spaces/{space}/runtime-environments/{environment}/versions/v1", developer)
            if status["status"] in {"READY", "FAILED"} or time.time() > deadline:
                break
            time.sleep(20)
        if status["status"] != "READY":
            raise SystemExit("environment " + environment + " " + status["status"])
    files = {task["entrypoint"]: (ORDERS / task["entrypoint"]).read_bytes() for task in definition["tasks"]}
    artifacts = [{"path": path, "upload_id": "pending", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
                 for path, raw in sorted(files.items())]
    pipeline = definition["pipeline_id"]
    api("POST", f"/v1/spaces/{space}/pipelines", developer, {"definition": definition, "artifacts": artifacts},
        expected=(201,))
    for artifact in artifacts:
        receipt = api("POST", f"/v1/spaces/{space}/pipelines/{pipeline}/artifact-uploads", developer,
                      {name: artifact[name] for name in ["path", "sha256", "bytes"]}, expected=(201,))
        with urlopen(Request(receipt["upload_url"], method="PUT", data=files[artifact["path"]],
                             headers=receipt["upload_headers"]), timeout=60):
            pass
        artifact["upload_id"] = receipt["upload_id"]
    metadata = api("GET", f"/v1/spaces/{space}/pipelines/{pipeline}", developer)
    draft = api("PUT", f"/v1/spaces/{space}/pipelines/{pipeline}/draft", developer,
                {"definition": definition, "artifacts": artifacts}, {"If-Match": '"' + metadata["revision"] + '"'})
    check = api("POST", f"/v1/spaces/{space}/pipelines/{pipeline}/validate", developer,
                {"draft_revision": draft["revision"]})
    if not check["valid"]:
        raise SystemExit("pipeline does not validate: " + json.dumps(check))
    version = api("POST", f"/v1/spaces/{space}/pipelines/{pipeline}/versions", developer,
                  {"draft_revision": draft["revision"]}, {"Idempotency-Key": "quickstart-publish"},
                  expected=(201,))["pipeline_version"]
    metadata = api("GET", f"/v1/spaces/{space}/pipelines/{pipeline}", developer)
    api("POST", f"/v1/spaces/{space}/pipelines/{pipeline}/activate", developer, {"pipeline_version": version},
        {"If-Match": '"' + metadata["revision"] + '"'})
    for operation in ["upsert", "delete"]:
        records = [{"event_id": "quickstart-%d-%d" % (order, version_), "order_id": order, "source_version": version_,
                    "event_time": day + "T00:00:00", **({"amount": amount} if operation == "upsert" else {})}
                   for order, version_, day, amount, kind in EVENTS if kind == operation]
        accepted = api("POST", f"/v1/spaces/{space}/ingestions", tokens["ingest"],
                       {"dataset": "orders", "schema_version": 1, "operation": operation, "records": records},
                       {"Idempotency-Key": "quickstart-" + operation}, expected=(202,))
        deadline = time.time() + 300
        while True:
            status = api("GET", accepted["status_url"], tokens["ingest"])
            if status["status"] in {"COMMITTED", "PUBLISHED", "FAILED"} or time.time() > deadline:
                break
            time.sleep(2)
        if status["status"] not in {"COMMITTED", "PUBLISHED"}:
            raise SystemExit("ingestion " + operation + " " + status["status"])
    run = api("POST", f"/v1/spaces/{space}/pipelines/{pipeline}/runs", developer,
              {"pipeline_version": version, "mode": "snapshot"}, {"Idempotency-Key": "quickstart-run"},
              expected=(202,))
    deadline = time.time() + 2400
    while True:
        status = api("GET", f"/v1/spaces/{space}/pipelines/{pipeline}/runs/{run['run_id']}", developer)
        if status["status"] in {"PUBLISHED", "FAILED", "CANCELLED"} or time.time() > deadline:
            break
        time.sleep(15)
    if status["status"] != "PUBLISHED":
        raise SystemExit("run " + status["status"])

    def query(token, sql, name, **fields):
        receipt = api("POST", f"/v1/spaces/{space}/queries", token, {
            "sql": sql, "client_request_id": "quickstart_" + name, **fields}, expected=(202,))
        deadline = time.time() + 300
        while True:
            value = api("GET", receipt["status_url"], token)
            if value["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"} or time.time() > deadline:
                return value
            time.sleep(1)

    dashboard = query(tokens["analyst"], "SELECT CAST(order_date AS VARCHAR), revenue, order_count, high_value_count "
                      "FROM ads.dashboard ORDER BY order_date", "dashboard", consistency="published")
    write = api("POST", f"/v1/spaces/{space}/writes", tokens["writer"], {
        "dataset": "dwd.accounts", "schema_version": 1, "operation": "insert",
        "records": [{"id": 1, "name": "first account", "balance": "100.00"}]},
        {"Idempotency-Key": "quickstart-account-1"})
    account = query(tokens["writer"], "SELECT id, name, balance FROM dwd.accounts", "account",
                    consistency="after_write", write_id=write["write_id"])
    result = {"dashboard": dashboard.get("rows"), "dashboard_versions": dashboard.get("data_versions"),
              "write": {name: write[name] for name in ["write_id", "status", "commit_sequence"]},
              "account": account.get("rows")}
    print(json.dumps(result, indent=2))
    if dashboard.get("rows") != EXPECTED_DASHBOARD or account.get("rows") != [[1, "first account", "100.00"]]:
        raise SystemExit("results differ from the documented expectation")
    print("PASS: API, SQL and pandas examples produced the documented results")


if __name__ == "__main__":
    main()
