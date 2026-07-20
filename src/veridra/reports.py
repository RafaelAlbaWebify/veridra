from __future__ import annotations

import html
import json

from .core import Assessment

_SCOPE = (
    "Scope: bounded public checks only. This is not a penetration test and "
    "does not inspect authenticated functionality, source code, server "
    "configuration, or private infrastructure."
)


def render_report(assessment: Assessment) -> str:
    target = html.escape(str(assessment.target))
    summary_cards = "".join(
        "<article><span>{label}</span><strong>{value}</strong></article>".format(
            label=html.escape(key.title()),
            value=value,
        )
        for key, value in assessment.summary.items()
    )
    rows = "".join(
        "<tr><td>{status}</td><td>{area}</td><td>{title}</td>"
        "<td>{summary}</td><td>{recommendation}</td><td><pre>{evidence}</pre></td></tr>".format(
            status=html.escape(item.status.value),
            area=html.escape(item.area),
            title=html.escape(item.title),
            summary=html.escape(item.summary),
            recommendation=html.escape(item.recommendation or "No action required."),
            evidence=html.escape(
                json.dumps(item.evidence, indent=2, sort_keys=True, ensure_ascii=False)
            ),
        )
        for item in assessment.findings
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veridra assessment report</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef1f4;color:#17191c;font:14px Arial,sans-serif}}main{{max-width:1300px;margin:32px auto;background:white;padding:40px;border:1px solid #dfe3e8}}header{{display:flex;justify-content:space-between;gap:24px;border-bottom:1px solid #dfe3e8;padding-bottom:22px}}h1{{margin:0 0 8px;font-size:30px}}.target{{word-break:break-all;color:#555}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}}article{{border:1px solid #dfe3e8;padding:16px}}article span{{display:block;text-transform:uppercase;font-size:11px;color:#68707a}}article strong{{display:block;font-size:26px;margin-top:8px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #e5e7ea}}th{{font-size:11px;text-transform:uppercase;color:#68707a}}pre{{white-space:pre-wrap;word-break:break-word;font-size:11px;margin:0}}.scope{{margin-top:26px;padding:14px;background:#f6f7f9;border-left:3px solid #707780}}@media(max-width:800px){{main{{margin:0;padding:20px}}.cards{{grid-template-columns:repeat(2,1fr)}}table{{display:block;overflow:auto}}}}@media print{{body{{background:white}}main{{border:0;margin:0;max-width:none;padding:0}}button{{display:none}}}}
</style>
</head>
<body>
<main>
<header><div><h1>Veridra assessment report</h1><div class="target">{target}</div></div><button onclick="window.print()">Print report</button></header>
<div class="cards">{summary_cards}</div>
<h2>Evidence-backed findings</h2>
<table><thead><tr><th>Status</th><th>Area</th><th>Finding</th><th>Observation</th><th>Recommended action</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>
<p class="scope">{html.escape(_SCOPE)}</p>
</main>
</body>
</html>"""
