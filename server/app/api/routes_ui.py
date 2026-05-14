from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["ui"])


@router.get("/ui", response_class=HTMLResponse)
@router.get("/ui/{page}", response_class=HTMLResponse)
def ui(page: str = "overview") -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>ma3 Knowledge Observatory</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #172033; }}
    nav a {{ margin-right: 1rem; }}
    pre {{ background: #f5f5f5; padding: 1rem; overflow: auto; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: .5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; }}
    .bucket {{ display: inline-block; margin: .2rem .35rem .2rem 0; padding: .25rem .45rem; background: #eef4ff; border-radius: .4rem; }}
    .muted {{ color: #667085; }}
    .pager a {{ margin-right: 1rem; }}
    code {{ background: #f2f4f7; padding: .1rem .25rem; border-radius: .25rem; }}
  </style>
</head>
<body>
  <h1>ma3 Knowledge Observatory</h1>
  <nav>
    <a href="/ui/overview">Overview</a>
    <a href="/ui/topics">Topics</a>
    <a href="/ui/cases">Cases</a>
    <a href="/ui/search-explain">Search Explain</a>
    <a href="/ui/quality-actions">Quality Actions</a>
  </nav>
  <p>Current page: <strong>{page}</strong></p>
  <p><label>API Key (optional, saved locally): <input id="api-key" type="password" style="width:28rem" placeholder="X-API-Key for private libraries" /></label> <button id="save-api-key" type="button">Save</button> <button id="clear-api-key" type="button">Clear</button></p>
  <div id="app">Loading...</div>
  <script>
    const page = {page!r};
    const params = new URLSearchParams(window.location.search);
    const app = document.getElementById("app");
    const esc = (value) => String(value ?? "").replace(/[&<>\"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#39;"}}[ch]));
    const enc = encodeURIComponent;
    const limit = Math.min(Math.max(parseInt(params.get("limit") || "25", 10) || 25, 1), 200);
    const offset = Math.max(parseInt(params.get("offset") || "0", 10) || 0, 0);
    const apiKeyInput = document.getElementById("api-key");
    apiKeyInput.value = localStorage.getItem("ma3_api_key") || "";
    document.getElementById("save-api-key").addEventListener("click", () => localStorage.setItem("ma3_api_key", apiKeyInput.value.trim()));
    document.getElementById("clear-api-key").addEventListener("click", () => {{ localStorage.removeItem("ma3_api_key"); apiKeyInput.value = ""; }});
    function apiHeaders(extra = {{}}) {{
      const key = apiKeyInput.value.trim() || localStorage.getItem("ma3_api_key") || "";
      return key ? {{...extra, "X-API-Key": key}} : extra;
    }}

    async function getJson(url) {{
      const resp = await fetch(url, {{headers: apiHeaders()}});
      if (!resp.ok) throw new Error(`${{resp.status}} ${{resp.statusText}} for ${{url}}`);
      return await resp.json();
    }}

    function renderRaw(result) {{
      app.innerHTML = `<pre>${{esc(JSON.stringify(result, null, 2))}}</pre>`;
    }}

    function renderTopicGroup(title, kind, buckets) {{
      if (!buckets?.length) return `<section><h2>${{esc(title)}}</h2><p class="muted">No buckets.</p></section>`;
      return `<section><h2>${{esc(title)}}</h2>` + buckets.map(bucket =>
        `<a class="bucket" href="/ui/cases?topic_kind=${{enc(kind)}}&topic=${{enc(bucket.name)}}&limit=25&offset=0">${{esc(bucket.name)}} <strong>${{bucket.count}}</strong></a>`
      ).join(" ") + `</section>`;
    }}

    async function renderTopics() {{
      const data = await getJson("/v2/topics");
      app.innerHTML = `
        <p class="muted">Click a topic to drill down to matching cases. Buckets are top-N aggregates over accessible records.</p>
        ${{renderTopicGroup("Products", "product", data.products)}}
        ${{renderTopicGroup("Components", "component", data.components)}}
        ${{renderTopicGroup("Tags", "tag", data.tags)}}
        ${{renderTopicGroup("Problem Families", "problem_family", data.problem_families)}}
        <h2>Totals</h2><pre>${{esc(JSON.stringify(data.totals, null, 2))}}</pre>`;
    }}

    function caseUrl(nextOffset) {{
      const next = new URLSearchParams(params);
      next.set("limit", String(limit));
      next.set("offset", String(Math.max(nextOffset, 0)));
      return `/ui/cases?${{next.toString()}}`;
    }}

    async function renderCases() {{
      const topicKind = params.get("topic_kind");
      const topic = params.get("topic");
      const query = new URLSearchParams({{limit: String(limit), offset: String(offset)}});
      if (topicKind && topic) {{
        query.set("topic_kind", topicKind);
        query.set("topic", topic);
      }}
      const cases = await getJson(`/v2/cases?${{query.toString()}}`);
      const title = topicKind && topic ? `Cases for ${{topicKind}}: ${{topic}}` : "Cases";
      const rows = cases.map(item => `
        <tr>
          <td><a href="/v2/cases/${{enc(item.case_id)}}"><code>${{esc(item.case_id)}}</code></a></td>
          <td>${{esc(item.title)}}<br><span class="muted">${{esc(item.summary).slice(0, 240)}}</span></td>
          <td>${{esc(item.target?.product || "")}}${{item.target?.component ? "/" + esc(item.target.component) : ""}}</td>
          <td>${{esc(item.problem_family || "")}}</td>
          <td>${{(item.tags || []).map(t => `<a href="/ui/cases?topic_kind=tag&topic=${{enc(t)}}">${{esc(t)}}</a>`).join(", ")}}</td>
        </tr>`).join("");
      app.innerHTML = `
        <h2>${{esc(title)}}</h2>
        <p class="muted">Showing ${{cases.length}} case(s), offset ${{offset}}, limit ${{limit}}.</p>
        <div class="pager">
          ${{offset > 0 ? `<a href="${{caseUrl(offset - limit)}}">Previous</a>` : ""}}
          ${{cases.length === limit ? `<a href="${{caseUrl(offset + limit)}}">Next</a>` : ""}}
          <a href="/ui/topics">Back to topics</a>
        </div>
        <table><thead><tr><th>Case</th><th>Title / Summary</th><th>Target</th><th>Family</th><th>Tags</th></tr></thead><tbody>${{rows || `<tr><td colspan="5">No cases.</td></tr>`}}</tbody></table>`;
    }}

    function parseTags(value) {{
      return String(value || "").split(",").map(x => x.trim()).filter(Boolean);
    }}

    function renderSearchResult(data) {{
      const explain = data.explain || {{}};
      const groups = data.cases || [];
      const groupRows = groups.map(group => `
        <tr>
          <td><a href="/v2/cases/${{enc(group.case.case_id)}}"><code>${{esc(group.case.case_id)}}</code></a></td>
          <td>${{esc(group.case.title)}}<br><span class="muted">${{esc(group.case.summary).slice(0, 220)}}</span></td>
          <td>${{Number(group.match_score || 0).toFixed(3)}}</td>
          <td>${{(group.why_matched || []).map(esc).join(", ")}}</td>
          <td>${{(group.records || []).map(r => `<div><code>${{esc(r.record_id)}}</code> ${{esc(r.title || "")}}</div>`).join("")}}</td>
          <td>
            <button data-judgment="useful" data-case-id="${{esc(group.case.case_id)}}">Useful</button>
            <button data-judgment="not_useful" data-case-id="${{esc(group.case.case_id)}}">Not useful</button>
          </td>
        </tr>`).join("");
      const scores = explain.score_breakdown || [];
      const scoreRows = scores.map(item => `
        <tr><td><code>${{esc(item.record_id)}}</code></td><td><code>${{esc(item.case_id || "")}}</code></td><td>${{Number(item.score || 0).toFixed(3)}}</td><td>${{(item.reasons || []).map(esc).join(", ")}}</td></tr>`).join("");
      document.getElementById("search-result").innerHTML = `
        <h2>Results</h2>
        <p><strong>Query hash:</strong> <code id="query-hash">${{esc(explain.query_hash || "")}}</code>
        <strong>Ranking:</strong> ${{esc(explain.ranking_config_version || "")}}
        <strong>Candidates:</strong> ${{explain.candidate_count ?? 0}}
        <strong>Cases:</strong> ${{explain.returned_case_count ?? groups.length}}</p>
        <h3>Matched Cases</h3>
        <table><thead><tr><th>Case</th><th>Title / Summary</th><th>Score</th><th>Why</th><th>Records</th><th>Feedback</th></tr></thead><tbody>${{groupRows || `<tr><td colspan="6">No matched cases.</td></tr>`}}</tbody></table>
        <h3>Explain stages</h3><pre>${{esc(JSON.stringify(explain.stages || [], null, 2))}}</pre>
        <h3>Score breakdown</h3>
        <table><thead><tr><th>Record</th><th>Case</th><th>Score</th><th>Reasons</th></tr></thead><tbody>${{scoreRows || `<tr><td colspan="4">No score breakdown.</td></tr>`}}</tbody></table>
        <h3>Raw response</h3><pre>${{esc(JSON.stringify(data, null, 2))}}</pre>`;
      document.querySelectorAll("button[data-judgment]").forEach(button => {{
        button.addEventListener("click", () => submitSearchFeedback(button.dataset.judgment, button.dataset.caseId));
      }});
    }}

    async function submitSearchFeedback(judgment, caseId) {{
      const queryHash = document.getElementById("query-hash")?.textContent || "";
      const resp = await fetch("/v2/search/feedback", {{
        method: "POST",
        headers: apiHeaders({{"Content-Type": "application/json"}}),
        body: JSON.stringify({{query_hash: queryHash, case_id: caseId, judgment}})
      }});
      const body = await resp.json();
      document.getElementById("feedback-status").textContent = resp.ok ? `Feedback saved: ${{body.feedback_id}}` : JSON.stringify(body);
    }}

    function renderSearchExplain() {{
      app.innerHTML = `
        <form id="search-form">
          <p><label>Problem<br><textarea name="problem" rows="4" style="width:100%">ma3 deployment ltp backup restore</textarea></label></p>
          <p><label>Task type <input name="task_type" value="deployment" /></label>
             <label>Goal <input name="goal" value="start ma3 on ltp" style="width:28rem" /></label></p>
          <p><label>Product <input name="product" value="ma3" /></label>
             <label>Component <input name="component" value="ltp" /></label>
             <label>Tags <input name="tags" value="ltp,deployment" /></label></p>
          <p><label>Max cases <input name="max_cases" type="number" min="1" max="20" value="5" /></label>
             <label>Max records/case <input name="max_records_per_case" type="number" min="1" max="10" value="3" /></label>
             <button type="submit">Run Search Explain</button></p>
        </form>
        <p id="feedback-status" class="muted"></p>
        <div id="search-result"><p class="muted">Submit a query to inspect matching cases, score breakdown, and ranking stages.</p></div>`;
      document.getElementById("search-form").addEventListener("submit", async (event) => {{
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const payload = {{
          problem: form.get("problem"),
          task_type: form.get("task_type") || "general",
          goal: form.get("goal") || "find relevant ma3 knowledge",
          target: {{product: form.get("product") || "general", component: form.get("component") || null}},
          tags: parseTags(form.get("tags")),
          max_cases: Number(form.get("max_cases") || 5),
          max_records_per_case: Number(form.get("max_records_per_case") || 3),
          include_explain: true
        }};
        document.getElementById("search-result").innerHTML = `<p>Searching...</p>`;
        const resp = await fetch("/v2/search/explain", {{method: "POST", headers: apiHeaders({{"Content-Type": "application/json"}}), body: JSON.stringify(payload)}});
        const body = await resp.json();
        if (!resp.ok) throw new Error(JSON.stringify(body));
        renderSearchResult(body);
      }});
    }}

    async function load() {{
      if (page === "search-explain") return renderSearchExplain();
      if (page === "topics") return renderTopics();
      if (page === "cases") return renderCases();
      const endpoints = {{
        "overview": ["/v2/stats/overview", "/v2/stats/search", "/v2/stats/knowledge-quality"],
        "quality-actions": ["/v2/stats/quality-actions"]
      }};
      const urls = endpoints[page] || endpoints["overview"];
      const result = {{}};
      for (const url of urls) result[url] = await getJson(url);
      renderRaw(result);
    }}
    load().catch(err => {{ app.innerHTML = `<pre>${{esc(err.stack || err)}}</pre>`; }});
  </script>
</body>
</html>"""
