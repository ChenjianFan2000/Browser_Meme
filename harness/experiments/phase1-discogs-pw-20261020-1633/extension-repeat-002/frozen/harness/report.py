"""Static auditable report; all metrics retain their original denominators."""
import html
import json
from pathlib import Path

from .artifacts import write_json


def produce(summary, out):
    out = Path(out)
    write_json(out / 'summary.json', summary)
    rows = ''.join('<tr><td>' + '</td><td>'.join(html.escape(str(value)) for value in
                   (case['id'], case['status'], case['passed'], case.get('error', ''))) + '</td></tr>'
                   for case in summary['cases'])
    body = ('<!doctype html><meta charset="utf-8"><title>Harness run</title>'
            '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto}td,th{padding:8px;border:1px solid #ccc}'
            'table{border-collapse:collapse}pre{white-space:pre-wrap}</style>'
            f'<h1>Run {html.escape(summary["run_id"])}</h1>'
            f'<p><strong>{html.escape(summary.get("measurement_note", ""))}</strong></p>'
            f'<p>Measurement status: {html.escape(summary.get("measurement_status", "unknown"))}. '
            'pipeline_completion_rate counts completed UI actions over planned steps; it is not model task success.</p>'
            '<p>Independent final evaluation determines task success. Prediction matches are reported separately.</p>'
            f'<pre>{html.escape(json.dumps(summary["metrics"], indent=2))}</pre>'
            '<table><tr><th>Case</th><th>Status</th><th>Passed</th><th>Error</th></tr>' + rows + '</table>'
            '<p><a href="summary.json">Full summary</a> · <a href="events.jsonl">Event trace</a> · '
            '<a href="feedback.json">Feedback</a> · <a href="manifest.json">SHA256 manifest</a></p>')
    (out / 'report.html').write_text(body, encoding='utf-8')
