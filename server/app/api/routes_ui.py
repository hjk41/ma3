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
    body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
    nav a {{ margin-right: 1rem; }}
    pre {{ background: #f5f5f5; padding: 1rem; overflow: auto; }}
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
    const endpoints = {{
      "overview": ["/v2/stats/overview", "/v2/stats/search", "/v2/stats/knowledge-quality"],
      "topics": ["/v2/topics"],
      "cases": ["/v2/cases"],
      "quality-actions": ["/v2/stats/quality-actions"],
      "search-explain": []
    }};
    async function load() {{
      if (page === "search-explain") {{
        document.getElementById("app").innerHTML = `<p>Use the API <code>POST /v2/search/explain</code> with a search payload. Interactive query UI will be added after the API stabilizes.</p>`;
        return;
      }}
      const urls = endpoints[page] || endpoints["overview"];
      const result = {{}};
      for (const url of urls) {{
        const resp = await fetch(url);
        result[url] = await resp.json();
      }}
      document.getElementById("app").innerHTML = `<pre>${{JSON.stringify(result, null, 2)}}</pre>`;
    }}
    load().catch(err => {{
      document.getElementById("app").innerHTML = `<pre>${{err.stack || err}}</pre>`;
    }});
  </script>
</body>
</html>"""

