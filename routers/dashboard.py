from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

from services.eval_tracker import get_eval_tracker

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def dashboard_metrics():
    return await get_eval_tracker().metrics(hours=24)


@router.get("/export")
async def dashboard_export():
    csv_text = await get_eval_tracker().export_csv()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="eval_log.csv"'},
    )


@router.get("", response_class=HTMLResponse)
async def dashboard_home():
    return """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RAG Evaluation Dashboard</title>
  <style>
    body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f6f8fb; color: #111827; }
    main { max-width: 1040px; margin: 0 auto; padding: 32px 20px; }
    h1 { font-size: 28px; margin: 0 0 20px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
    .metric { background: white; border: 1px solid #dbe3f0; border-radius: 8px; padding: 16px; }
    .label { color: #64748b; font-size: 13px; }
    .value { font-size: 26px; font-weight: 700; margin-top: 6px; }
    table { width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe3f0; }
    th, td { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; }
    th { background: #eef4ff; font-size: 13px; color: #334155; }
    a { color: #2563eb; font-weight: 600; }
  </style>
</head>
<body>
  <main>
    <h1>RAG Evaluation Dashboard</h1>
    <p><a href="/dashboard/export">Export CSV</a></p>
    <section class="grid" id="metrics"></section>
    <h2>Failing Queries</h2>
    <table>
      <thead><tr><th>#</th><th>Query</th></tr></thead>
      <tbody id="failures"></tbody>
    </table>
  </main>
  <script>
    async function loadMetrics() {
      const response = await fetch('/dashboard/metrics');
      const data = await response.json();
      const items = [
        ['Total queries', data.total_queries],
        ['Avg latency', `${data.avg_latency_ms} ms`],
        ['Source hit rate', `${Math.round(data.source_hit_rate * 100)}%`],
        ['Thumbs up rate', `${Math.round(data.thumbs_up_rate * 100)}%`],
      ];
      document.getElementById('metrics').innerHTML = items.map(([label, value]) => `
        <div class="metric"><div class="label">${label}</div><div class="value">${value}</div></div>
      `).join('');
      document.getElementById('failures').innerHTML = (data.failing_queries || []).map((query, index) => `
        <tr><td>${index + 1}</td><td>${String(query).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</td></tr>
      `).join('');
    }
    loadMetrics();
  </script>
</body>
</html>
"""


def register_dashboard_routes(app) -> None:
    app.include_router(router)

