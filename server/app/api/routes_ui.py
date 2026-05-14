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
  <div id="app">Loading...</div>
  <script>
    const page = {page!r};
    const params = new URLSearchParams(window.location.search);
    const app = document.getElementById("app");
    const esc = (value) => String(value ?? "").replace(/[&<>\"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#39;"}}[ch]));
    const enc = encodeURIComponent;
    const limit = Math.min(Math.max(parseInt(params.get("limit") || "25", 10) || 25, 1), 200);
    const offset = Math.max(parseInt(params.get("offset") || "0", 10) || 0, 0);

    async function getJson(url) {{
      const resp = await fetch(url);
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

    async function load() {{
      if (page === "search-explain") {{
        app.innerHTML = `<p>Use the API <code>POST /v2/search/explain</code> with a search payload. Interactive query UI will be added after the API stabilizes.</p>`;
        return;
      }}
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
