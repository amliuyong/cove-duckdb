"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const terminal = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
  const state = {
    context: null, epoch: 0, requests: new Set(), catalog: [], history: [],
    query: null, pending: null, pendingUnconfirmed: false, poll: null, revision: 0, observation: 0,
    pages: [null], page: 0, nextPage: null, exportPath: null, suggestions: [], suggestion: 0,
  };

  class ApiError extends Error {
    constructor(status, code, message) {
      super(message || code || "请求失败");
      this.status = status;
      this.code = code || "REQUEST_FAILED";
    }
  }

  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  }

  function notice(message, error = false) {
    $("notice").textContent = message;
    $("notice").classList.toggle("error", error);
    $("notice").hidden = !message;
  }

  function current(context, revision = null) {
    return state.context === context && (revision === null || revision === state.revision);
  }

  function base(context = state.context) {
    if (!context) throw new Error("请先连接数据空间");
    return "/v1/spaces/" + encodeURIComponent(context.space);
  }

  async function api(path, options = {}, context = state.context) {
    const prefix = base(context) + "/";
    if (!path.startsWith(prefix) || path.includes("#")) throw new Error("请求不属于当前数据空间");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    state.requests.add(controller);
    try {
      const response = await fetch(path, {
        method: options.method || "GET",
        headers: { Authorization: "Bearer " + context.key, "Content-Type": "application/json" },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal, cache: "no-store", credentials: "omit",
        redirect: "error", referrerPolicy: "no-referrer",
      });
      let value;
      try {
        value = await response.json();
      } catch (error) {
        if (response.ok) throw error;
        value = {};
      }
      if (!current(context)) throw new Error("CONNECTION_CHANGED");
      if (!response.ok) throw new ApiError(response.status, value.code || value.error, value.message);
      return value;
    } finally {
      clearTimeout(timer);
      state.requests.delete(controller);
    }
  }

  function report(error, context = state.context) {
    if (!context || !current(context)) return;
    const message = error instanceof ApiError
      ? error.code + " · " + error.message
      : "请求未确认。请保留查询身份并核对状态。";
    notice(message, true);
    if (error.status === 401 || error.status === 403 || error.status === 410) clearResult();
  }

  function stopPoll() {
    clearTimeout(state.poll);
    state.poll = null;
  }

  function clearResult() {
    $("results").replaceChildren();
    $("versions").replaceChildren();
    $("page-info").textContent = "";
    $("previous-page").disabled = true;
    $("next-page").disabled = true;
    $("export").disabled = true;
    state.exportPath = null;
    state.nextPage = null;
  }

  function badge(status) {
    const node = text("span", status, "status-badge");
    node.dataset.status = status;
    return node;
  }

  function renderQuery(unconfirmed = false) {
    const query = state.query;
    const meta = $("query-meta");
    meta.replaceChildren();
    if (!query) {
      meta.append(text("span", state.pending ? "提交待核对" : "执行查询后，在这里查看结果。", "muted"));
      if (state.pending) meta.append(text("code", state.pending.client_request_id));
    } else {
      meta.append(badge(query.status), text("code", query.query_id));
      if (query.elapsed_ms !== undefined) meta.append(text("span", query.elapsed_ms + " ms"));
      if (query.error_code) meta.append(text("span", query.error_code));
      if (unconfirmed) meta.append(text("span", "当前状态待核对", "muted"));
      if (state.pending) meta.append(text("code", "提交待核对 · " + state.pending.client_request_id));
    }
    $("refresh-query").disabled = !query;
    $("restore-sql").disabled = !query;
    $("cancel").disabled = !query || terminal.has(query.status);
    $("retry-submit").hidden = !state.pending;
  }

  function format(value) {
    if (value === null) return "NULL";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function exportPath(value, queryId, context) {
    if (!value) return null;
    const parsed = new URL(value, location.origin);
    const expected = base(context) + "/queries/" + encodeURIComponent(queryId) + "/export";
    if (parsed.pathname !== expected || parsed.hash || parsed.searchParams.getAll("token").length !== 1
        || !parsed.searchParams.get("token")
        || [...parsed.searchParams.keys()].some((key) => key !== "token")) {
      throw new Error("导出引用与原查询不一致");
    }
    // Use the authenticated same-origin API even when the server returns its
    // public Gateway URL. No credentials are sent to a response-supplied host.
    return expected + parsed.search;
  }

  function validateResult(value) {
    if (!Array.isArray(value.columns) || !Array.isArray(value.rows)
        || value.columns.some((column) => typeof column.name !== "string"
          || typeof column.type !== "string" || !["native_json", "native_text"].includes(column.encoding))
        || value.rows.some((row) => !Array.isArray(row) || row.length !== value.columns.length
          || row.some((cell, index) => value.columns[index].encoding === "native_text"
            && cell !== null && typeof cell !== "string"))) {
      throw new Error("原查询结果类型尚未确认");
    }
  }

  function renderResult(value, context) {
    validateResult(value);
    clearResult();
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    for (const column of value.columns || []) {
      const cell = document.createElement("th");
      cell.append(text("span", column.name), text("small", column.type));
      head.append(cell);
    }
    const body = table.createTBody();
    for (const row of value.rows || []) {
      const tr = body.insertRow();
      for (const [index, cell] of row.entries()) {
        const td = tr.insertCell();
        td.textContent = format(cell);
        if (cell === null) td.className = "null";
        td.dataset.encoding = value.columns[index].encoding;
      }
    }
    $("results").append(table);
    for (const version of value.data_versions || []) {
      const parts = [version.dataset, version.release_id || "无分析发布版本"];
      if (version.commit_sequence !== undefined) parts.push("提交水位 " + version.commit_sequence);
      if (version.snapshot_sequence !== undefined) parts.push("读取水位 " + version.snapshot_sequence);
      $("versions").append(text("div", parts.join(" · ")));
    }
    const rows = value.rows || [];
    $("page-info").textContent = "第 " + (state.page + 1) + " 页 · 本页 " + rows.length
      + " 行 / 共 " + value.row_count + " 行" + (value.truncated ? " · 达到返回行数上限" : "");
    $("result-message").textContent = rows.length ? "" : "查询成功，结果为空。";
    state.nextPage = value.next_page_token || null;
    state.exportPath = exportPath(value.export_url, value.query_id, context);
    $("previous-page").disabled = state.page === 0;
    $("next-page").disabled = !state.nextPage;
    $("export").disabled = !state.exportPath;
  }

  async function page(index) {
    const context = state.context;
    const revision = state.revision;
    const query = state.query;
    if (!query || query.status !== "SUCCEEDED") return;
    const observation = ++state.observation;
    const token = state.pages[index];
    const options = new URLSearchParams({ view: "result", page_size: "100" });
    if (token) options.set("page_token", token);
    try {
      const value = await api(base(context) + "/queries/" + encodeURIComponent(query.query_id)
        + "?" + options, {}, context);
      if (!current(context, revision) || observation !== state.observation) return;
      if (value.query_id !== query.query_id || value.status !== "SUCCEEDED" || value.view !== "result") {
        throw new Error("原查询结果尚未确认");
      }
      state.page = index;
      state.query = value;
      renderQuery();
      renderResult(value, context);
    } catch (error) {
      if (!current(context, revision) || observation !== state.observation) return;
      clearResult();
      renderQuery(true);
      report(error, context);
    }
  }

  async function observe() {
    stopPoll();
    const context = state.context;
    const revision = state.revision;
    const query = state.query;
    if (!context || !query) return;
    const observation = ++state.observation;
    try {
      const value = await api(base(context) + "/queries/" + encodeURIComponent(query.query_id)
        + "?view=metadata", {}, context);
      if (!current(context, revision) || observation !== state.observation) return;
      if (value.query_id !== query.query_id) throw new Error("查询身份不一致");
      state.query = value;
      renderQuery();
      if (value.status === "SUCCEEDED") {
        await page(state.page);
        await refreshHistory();
      } else if (terminal.has(value.status)) {
        clearResult();
        $("result-message").textContent = value.status + (value.error_code ? " · " + value.error_code : "");
        await refreshHistory();
      } else {
        $("result-message").textContent = value.status === "UNKNOWN"
          ? "服务端正在核对执行结果。查询身份保持不变，可继续核对或请求取消。"
          : "查询仍在进行。关闭页面不会自动取消任务。";
        state.poll = setTimeout(observe, 1500);
      }
    } catch (error) {
      if (!current(context, revision) || observation !== state.observation) return;
      renderQuery(true);
      report(error, context);
      if (!(error instanceof ApiError && [401, 403, 404, 410].includes(error.status))) {
        state.poll = setTimeout(observe, 5000);
      }
    }
  }

  function selectQuery(query) {
    stopPoll();
    state.revision++;
    state.observation++;
    state.query = query;
    state.pages = [null];
    state.page = 0;
    clearResult();
    renderQuery();
    $("result-message").textContent = "正在核对原查询…";
    observe();
  }

  async function refreshHistory() {
    const context = state.context;
    if (!context) return;
    try {
      const value = await api(base(context) + "/queries", {}, context);
      if (!current(context)) return;
      state.history = value.queries || [];
      $("history").replaceChildren();
      if (!state.history.length) $("history").append(text("p", "暂无保留的查询。", "small muted"));
      for (const query of state.history) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "history-item";
        item.append(text("code", query.query_id));
        const detail = text("span", "", "small");
        detail.append(badge(query.status), text("span", (query.elapsed_ms || 0) + " ms", "muted"));
        item.append(detail);
        item.addEventListener("click", () => selectQuery(query));
        $("history").append(item);
      }
    } catch (error) {
      if (!current(context)) return;
      $("history").replaceChildren(text("p", "历史尚未取得。请刷新核对。", "small muted"));
      report(error, context);
    }
  }

  function quoted(value) {
    return '"' + value.replaceAll('"', '""') + '"';
  }

  function syncHighlight() {
    const editor = $("sql");
    const layer = $("sql-highlight");
    layer.style.width = (editor.clientWidth + 2) + "px";
    layer.style.height = (editor.clientHeight + 2) + "px";
    layer.scrollTop = editor.scrollTop;
    layer.scrollLeft = editor.scrollLeft;
  }

  function highlight() {
    const sql = $("sql").value;
    const pattern = /--[^\r\n]*|\/\*[\s\S]*?(?:\*\/|$)|'(?:''|[^'])*(?:'|$)|"(?:""|[^"])*(?:"|$)|\b(?:SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|USING|WITH|AS|DISTINCT|GROUP|BY|HAVING|ORDER|LIMIT|OFFSET|UNION|ALL|EXPLAIN|ANALYZE|CASE|WHEN|THEN|ELSE|END|AND|OR|NOT|IN|IS|NULL|TRUE|FALSE|ASC|DESC|OVER|PARTITION|COUNT|SUM|AVG|MIN|MAX)\b|\b\d+(?:\.\d*)?(?:e[+-]?\d+)?\b/gi;
    const fragment = document.createDocumentFragment();
    let offset = 0;
    for (const match of sql.matchAll(pattern)) {
      fragment.append(document.createTextNode(sql.slice(offset, match.index)));
      const token = match[0];
      const kind = token.startsWith("--") || token.startsWith("/*") ? "comment"
        : token.startsWith("'") ? "string" : token.startsWith('"') ? "identifier"
        : /^\d/.test(token) ? "number" : "keyword";
      fragment.append(text("span", token, "sql-" + kind));
      offset = match.index + token.length;
    }
    fragment.append(document.createTextNode(sql.slice(offset) + "\n"));
    $("sql-highlight").replaceChildren(fragment);
    syncHighlight();
  }

  function insert(value, start = $("sql").selectionStart, end = $("sql").selectionEnd) {
    $("sql").setRangeText(value, start, end, "end");
    highlight();
    $("sql").focus();
  }

  function renderCatalog() {
    const filter = $("catalog-filter").value.toLowerCase();
    $("catalog").replaceChildren();
    for (const dataset of state.catalog) {
      if (!(dataset.dataset + " " + dataset.schema.map((column) => column.name).join(" "))
        .toLowerCase().includes(filter)) continue;
      const group = document.createElement("details");
      group.append(text("summary", dataset.dataset));
      const button = text("button", "插入查询", "dataset-query");
      button.type = "button";
      button.addEventListener("click", () => insert("SELECT * FROM "
        + dataset.dataset.split(".").map(quoted).join(".") + " LIMIT 100;"));
      group.append(button);
      for (const column of dataset.schema) {
        const detail = text("div", "", "column-detail");
        detail.append(text("code", column.name), text("span", column.type));
        group.append(detail);
      }
      $("catalog").append(group);
    }
    if (!$("catalog").childElementCount) {
      $("catalog").append(text("p", filter ? "没有匹配的数据集。" : "暂无可读取的数据集。", "small muted"));
    }
  }

  async function refreshCatalog() {
    const context = state.context;
    const value = await api(base(context) + "/catalog", {}, context);
    if (!current(context)) return;
    state.catalog = value.datasets || [];
    renderCatalog();
  }

  function disconnect() {
    stopPoll();
    state.context = null;
    state.epoch++;
    state.revision++;
    state.observation++;
    for (const controller of state.requests) controller.abort();
    state.catalog = [];
    state.history = [];
    state.query = null;
    state.pending = null;
    state.pendingUnconfirmed = false;
    state.suggestions = [];
    $("api-key").value = "";
    $("sql").value = "";
    highlight();
    $("catalog").replaceChildren();
    $("history").replaceChildren();
    $("completion").hidden = true;
    $("workspace").hidden = true;
    $("connection").hidden = false;
    $("connection-status").textContent = "未连接";
    $("disconnect").disabled = true;
    $("connect").disabled = false;
    $("run").disabled = false;
    $("explain").disabled = false;
    $("retry-submit").disabled = false;
    $("result-message").textContent = "";
    clearResult();
    renderQuery();
    notice("");
  }

  async function connect(event) {
    event.preventDefault();
    const space = $("space").value.trim();
    const key = $("api-key").value.trim();
    if (!space || space.length > 128 || !key) {
      notice("请输入数据空间和 API Key。", true);
      return;
    }
    disconnect();
    const context = { space, key, epoch: state.epoch };
    state.context = context;
    $("connect").disabled = true;
    $("connection-status").textContent = "正在连接…";
    try {
      await refreshCatalog();
      if (!current(context)) return;
      $("connection").hidden = true;
      $("workspace").hidden = false;
      $("disconnect").disabled = false;
      $("connection-status").textContent = context.space;
      await refreshHistory();
      $("sql").focus();
    } catch (error) {
      if (!current(context)) return;
      disconnect();
      notice(error instanceof ApiError ? error.code + " · " + error.message
        : "连接未确认，请重新连接。", true);
    } finally {
      if (current(context) || !state.context) $("connect").disabled = false;
    }
  }

  function request(explain) {
    const editor = $("sql");
    let sql = editor.selectionStart === editor.selectionEnd
      ? editor.value : editor.value.slice(editor.selectionStart, editor.selectionEnd);
    sql = sql.trim();
    if (!sql) throw new Error("请输入或选中要执行的 SQL。");
    const maxRows = Number($("max-rows").value);
    const seconds = Number($("timeout").value);
    if (!Number.isInteger(maxRows) || maxRows < 1 || maxRows > 10000
        || !Number.isInteger(seconds) || seconds < 1 || seconds > 300) {
      throw new Error("返回行数须为 1–10000，超时须为 1–300 秒。");
    }
    const consistency = $("consistency").value;
    const condition = $("condition-id").value.trim();
    const body = {
      sql: explain ? "EXPLAIN " + sql : sql,
      client_request_id: "client_" + crypto.randomUUID().replaceAll("-", ""),
      max_rows: maxRows, timeout_ms: seconds * 1000, consistency,
    };
    if (consistency === "after_write" || consistency === "after_ingestion") {
      if (!condition) throw new Error("请填写对应的提交 ID。");
      body[consistency === "after_write" ? "write_id" : "ingestion_id"] = condition;
    } else if (consistency === "published" && condition) {
      body.release_id = condition;
    }
    return body;
  }

  async function submit(body) {
    const context = state.context;
    const revision = state.revision;
    const originalUnconfirmed = state.pending === body && state.pendingUnconfirmed;
    state.pending = body;
    renderQuery();
    $("retry-submit").disabled = true;
    $("run").disabled = true;
    $("explain").disabled = true;
    try {
      const value = await api(base(context) + "/queries", { method: "POST", body }, context);
      if (!current(context) || state.pending !== body) return;
      if (!value.query_id || !value.status) throw new Error("原提交身份尚未确认");
      state.pending = null;
      state.pendingUnconfirmed = false;
      notice("查询已提交 · " + value.query_id);
      if (revision === state.revision) selectQuery(value);
      else renderQuery();
      await refreshHistory();
    } catch (error) {
      if (!current(context) || state.pending !== body) return;
      if (!originalUnconfirmed && error instanceof ApiError
          && [400, 401, 403, 413, 429].includes(error.status)) {
        state.pending = null;
        state.pendingUnconfirmed = false;
        renderQuery();
        notice(error.code + " · " + error.message + " · 请求身份 " + body.client_request_id, true);
        $("result-message").textContent = "提交被拒绝。";
        return;
      }
      state.pendingUnconfirmed = true;
      renderQuery(true);
      notice("提交待核对 · " + body.client_request_id + "。核对原提交会使用相同请求身份。"
        + (error instanceof ApiError ? " " + error.code : ""), true);
    } finally {
      if (current(context)) {
        $("retry-submit").disabled = false;
        $("run").disabled = Boolean(state.pending);
        $("explain").disabled = Boolean(state.pending);
      }
    }
  }

  function run(explain = false) {
    if (!state.context) return;
    if (state.pending) {
      notice("请先核对原提交，查询身份为 " + state.pending.client_request_id + "。", true);
      return;
    }
    try {
      const body = request(explain);
      stopPoll();
      state.revision++;
      state.query = null;
      clearResult();
      $("result-message").textContent = "正在提交查询…";
      submit(body);
    } catch (error) {
      notice(error.message, true);
    }
  }

  async function cancel() {
    const context = state.context;
    const revision = state.revision;
    const query = state.query;
    if (!query) return;
    $("cancel").disabled = true;
    try {
      const value = await api(base(context) + "/queries/" + encodeURIComponent(query.query_id)
        + "/cancel", { method: "POST", body: {} }, context);
      if (!current(context, revision)) return;
      if (value.query_id !== query.query_id) throw new Error("取消请求身份不一致");
      state.query = { ...query, ...value };
      renderQuery();
      observe();
    } catch (error) {
      if (!current(context, revision)) return;
      renderQuery(true);
      report(error, context);
    }
  }

  async function restoreSql() {
    const context = state.context;
    const revision = state.revision;
    const query = state.query;
    if (!query) return;
    try {
      const value = await api(base(context) + "/queries/" + encodeURIComponent(query.query_id)
        + "?view=sql", {}, context);
      if (!current(context, revision)) return;
      if (value.query_id !== query.query_id || value.view !== "sql") throw new Error("SQL 身份尚未确认");
      $("sql").value = value.sql;
      highlight();
      $("sql").focus();
    } catch (error) {
      if (current(context, revision)) report(error, context);
    }
  }

  async function download() {
    const context = state.context;
    const revision = state.revision;
    const query = state.query;
    const path = state.exportPath;
    if (!path || !query) return;
    $("export").disabled = true;
    try {
      const value = await api(path, {}, context);
      if (!current(context, revision)) return;
      validateResult(value);
      const blob = new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.download = query.query_id + ".json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      if (current(context, revision)) report(error, context);
    } finally {
      if (current(context, revision)) $("export").disabled = !state.exportPath;
    }
  }

  function complete() {
    const editor = $("sql");
    const before = editor.value.slice(0, editor.selectionStart);
    const prefix = (before.match(/[A-Za-z0-9_.]*$/) || [""])[0];
    const words = [
      "SELECT", "FROM", "WHERE", "JOIN", "LEFT JOIN", "GROUP BY", "ORDER BY", "LIMIT",
      "WITH", "AS", "DISTINCT", "COUNT", "SUM", "AVG", "CASE", "WHEN", "THEN", "END",
      ...state.catalog.map((dataset) => dataset.dataset.split(".").map(quoted).join(".")),
      ...state.catalog.flatMap((dataset) => dataset.schema.map((column) => quoted(column.name))),
    ];
    state.suggestions = [...new Set(words)]
      .filter((value) => value.replaceAll('"', "").toLowerCase().startsWith(prefix.toLowerCase()))
      .slice(0, 60);
    state.suggestion = 0;
    state.completionStart = editor.selectionStart - prefix.length;
    state.completionEnd = editor.selectionEnd;
    $("completion").replaceChildren();
    state.suggestions.forEach((value, index) => {
      const item = text("button", value);
      item.type = "button";
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(index === 0));
      item.addEventListener("click", () => acceptCompletion(index));
      $("completion").append(item);
    });
    $("completion").hidden = !state.suggestions.length;
  }

  function acceptCompletion(index) {
    const value = state.suggestions[index];
    if (value === undefined) return;
    insert(value, state.completionStart, state.completionEnd);
    $("completion").hidden = true;
  }

  function conditionLabel() {
    const mode = $("consistency").value;
    const choices = {
      published: ["Release ID（可选）", "留空读取当前发布版本"],
      current: ["当前状态", "无需提交或发布 ID"],
      after_write: ["Write ID", "write_…"],
      after_ingestion: ["Ingestion ID", "ing_…"],
    };
    $("condition-label").firstChild.textContent = choices[mode][0];
    $("condition-id").placeholder = choices[mode][1];
    $("condition-id").disabled = mode === "current";
    $("condition-id").value = "";
  }

  $("connect-form").addEventListener("submit", connect);
  $("disconnect").addEventListener("click", disconnect);
  $("refresh-catalog").addEventListener("click", () => refreshCatalog().catch((error) => report(error)));
  $("catalog-filter").addEventListener("input", renderCatalog);
  $("refresh-history").addEventListener("click", refreshHistory);
  $("refresh-query").addEventListener("click", observe);
  $("run").addEventListener("click", () => run(false));
  $("explain").addEventListener("click", () => run(true));
  $("retry-submit").addEventListener("click", () => {
    if (state.pending) submit(state.pending);
  });
  $("cancel").addEventListener("click", cancel);
  $("restore-sql").addEventListener("click", restoreSql);
  $("export").addEventListener("click", download);
  $("consistency").addEventListener("change", conditionLabel);
  $("previous-page").addEventListener("click", () => {
    if (state.page > 0) page(state.page - 1);
  });
  $("next-page").addEventListener("click", () => {
    if (!state.nextPage) return;
    state.pages = state.pages.slice(0, state.page + 1);
    state.pages.push(state.nextPage);
    page(state.page + 1);
  });
  $("sql").addEventListener("input", () => {
    $("completion").hidden = true;
    highlight();
  });
  $("sql").addEventListener("scroll", syncHighlight);
  new ResizeObserver(syncHighlight).observe($("sql"));
  highlight();
  $("sql").addEventListener("keydown", (event) => {
    if (event.isComposing) return;
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      run(false);
    } else if (event.ctrlKey && event.code === "Space") {
      event.preventDefault();
      complete();
    } else if (!$("completion").hidden) {
      if (event.key === "Escape") {
        $("completion").hidden = true;
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        state.suggestion = (state.suggestion + (event.key === "ArrowDown" ? 1 : -1)
          + state.suggestions.length) % state.suggestions.length;
        [...$("completion").children].forEach((node, index) =>
          node.setAttribute("aria-selected", String(index === state.suggestion)));
      } else if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        acceptCompletion(state.suggestion);
      }
    }
  });
  window.addEventListener("pagehide", disconnect);
})();
