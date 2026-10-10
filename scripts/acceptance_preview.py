"""Human acceptance controls, installed only in the disposable browser harness.

Never import this module in the serving application. No real credentials, corpus
or approvals are used. Local observations survive navigation, not server removal.
"""

from collections.abc import Callable
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from browser_reader import seed_reader
from caf_api.auth import SESSION_COOKIE, create_session, require_account, set_cookie
from caf_db.engine import get_session_factory
from caf_common.settings import get_settings


CHECKLIST = [
    ('navigation', 'Navigation and resume', 'Today → Papers → Syllabus → topic → question → back. Inspect filters and selection.'),
    ('appearance', 'Appearance', 'Inspect desktop and a narrow window, light and dark themes, and 200% zoom.'),
    ('reader', 'Complete reader and sources', 'Read the long case, both parts and the table. Reveal answers and open the source PDF.'),
    ('answers', 'Complete, partial and missing answers', 'Compare the three linked reader examples. Missing content must be unmistakable.'),
    ('importance', 'Topic importance', 'Inspect the components, raw marks, formula and evidence limitations. These values are synthetic.'),
    ('notes', 'Private notes', 'Save a note, edit it and navigate away. Use a second account to check privacy.'),
    ('progress', 'Personal progress', 'Change a topic status and compare your plan and revision queue with the other account.'),
    ('plans', 'Planning', 'Change your profile budget and paper scope. Inspect the resulting allocation.'),
    ('revision', 'Revision outcomes', 'Navigate without recording an outcome, then record one deliberately.'),
    ('classification', 'AI review', 'Read the complete question and labels. Inspect the actual blockers in Review questions.'),
    ('verification', 'Publication and verification', 'Eligible publication fixtures are pending. Current reader publications demonstrate study only.'),
    ('conflicts', 'Revision conflicts', 'Human conflict scenarios are pending; automated Phase 7 coverage is separate evidence.'),
    ('extraction', 'Extraction correction', 'Inspect the Extraction screen. Source-backed editable scenarios are pending.'),
    ('taxonomy', 'Successor taxonomy', 'Phase 8 preparation and migration-preview workflows are pending implementation.'),
    ('incomplete', 'Incomplete corpus', 'Select May 2027 in Profile; inspect the unavailable context without invented scores.'),
    ('access', 'Access control', 'Switch accounts. Students must not see administration controls or another account’s notes.'),
]


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    area: str
    status: str
    screen: str = Field(default='', max_length=500)
    observation: str = Field(default='', max_length=10000)


def seed_acceptance_readers(db, nodes, partial: dict) -> dict:
    require_test_environment()
    return {
        'partial': partial,
        'complete': seed_reader(db, nodes, scenario='complete'),
        'missing': seed_reader(db, nodes, scenario='missing'),
    }


def install_acceptance(harness, readers: dict, storage: Path) -> Callable[[], None]:
    require_test_environment()
    evidence_file = storage / 'human-acceptance.json'
    observations = []
    banner = (
        '<style>.workspace-sidebar,.curator-sidebar{top:var(--caf-acceptance-banner-height,34px)}'
        '.workspace-header,.curator-header{top:var(--caf-acceptance-banner-height,34px)}</style>'
        '<aside id="caf-acceptance-banner" aria-label="Acceptance environment" style="position:sticky;top:0;z-index:40;'
        'padding:8px 12px;background:#fff3cd;color:#332600;font:14px system-ui;border-bottom:1px solid #c99">'
        '<strong>LOCAL ACCEPTANCE · SYNTHETIC DATA</strong> · '
        'No real approvals or student records. '
        '<a href="/__acceptance" style="color:inherit;text-decoration:underline">Accounts, examples &amp; feedback</a>'
        '</aside>'
        '<script>new ResizeObserver(entries=>document.documentElement.style.setProperty('
        '"--caf-acceptance-banner-height",entries[0].target.getBoundingClientRect().height+"px"))'
        '.observe(document.getElementById("caf-acceptance-banner"));</script>'
    )

    @harness.middleware('http')
    async def acceptance_label(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/__acceptance'):
            response.headers['Cache-Control'] = 'no-store'
        if response.headers.get('content-type', '').startswith('text/html'):
            body = b''.join([chunk async for chunk in response.body_iterator])
            page = re.sub(r'<body\b[^>]*>', lambda match: match[0] + banner, body.decode(), count=1)
            headers = dict(response.headers)
            headers.pop('content-length', None)
            headers['Cache-Control'] = 'no-store'
            return HTMLResponse(page, status_code=response.status_code, headers=headers)
        return response

    @harness.get('/__acceptance', response_class=HTMLResponse)
    def start():
        account_forms = ''.join(
            f'<form action="/__acceptance/login?account_id={account_id}" method="post">'
            f'<button>{label}</button></form>'
            for account_id, label in [(1, 'Study as Student A'), (2, 'Study as Student B'),
                                       (3, 'Review as Administrator')]
        )
        reader_links = ''.join(
            f'<li><a href="/questions/{value["question_id"]}">{scenario.title()} answer example</a></li>'
            for scenario, value in readers.items()
        )
        rows = ''.join(
            f'<tr><th scope="row">{title}</th><td>{task}</td><td>'
            f'<form data-area="{area}"><label>Judgment<select name="status">'
            '<option>Not tested</option><option>Approved</option><option>Changes requested</option></select></label>'
            '<label>Screen<input name="screen"></label>'
            '<label>Observation<textarea name="observation" rows="2"></textarea></label>'
            '<button>Save feedback</button><output aria-live="polite"></output></form></td></tr>'
            for area, title, task in CHECKLIST
        )
        return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Local acceptance — CA Final Prep</title>
<style>body{margin:0;font:16px/1.55 system-ui;color:#18252d;background:#f8fafb}main{max-width:1100px;margin:auto;padding:24px}
h1,h2{line-height:1.2}a{color:#075c73}button,input,select,textarea{font:inherit}button{padding:8px 12px;cursor:pointer}
.accounts{display:flex;gap:12px;flex-wrap:wrap}.notice{background:#fff3cd;padding:16px;border-radius:8px}
table{width:100%;border-collapse:collapse}td,th{text-align:left;vertical-align:top;padding:12px;border:1px solid #d8e1e5}
th{width:18%}td{width:38%}label{display:block}input,textarea,select{box-sizing:border-box;max-width:100%;width:100%;margin:4px 0 8px}
output{display:block}pre{white-space:pre-wrap}@media(max-width:700px){tr,td,th{display:block;width:auto}thead{display:none}}
@media(prefers-color-scheme:dark){body{background:#162126;color:#eef2f3}a{color:#8cd6e8}.notice{color:#332600}}
</style></head><body><main><h1>Review the local experience</h1>
<p class="notice">This is an isolated acceptance environment. All accounts, sources, publications and scores are synthetic.
Your real database is untouched. These observations do not approve live source content or release a production service.</p>
<h2>Choose an account</h2><p>No passwords or Auth0 credentials are needed. Switching accounts uses the same browser session.
Use separate browser profiles/windows for simultaneous accounts.</p><div class="accounts">''' + account_forms + '''</div>
<h2>Reader examples</h2><ul>''' + reader_links + '''</ul>
<h2>Study and review</h2><ul><li><a href="/">Today</a></li><li><a href="/syllabus">Syllabus and personal notes</a></li>
<li><a href="/plan">Plan</a></li><li><a href="/revision">Revision</a></li>
<li><a href="/curator/classifications">Shared classification review</a></li>
<li><a href="/curator/extraction">Extraction review</a></li><li><a href="/curator/readiness">Administrator readiness</a></li></ul>
<p>To see the unavailable context, open Profile and select May 2027, which has no reviewed binding in this fixture.
Return to May 2026 for the populated synthetic study examples.</p>
<h2>Your observations</h2><p>Sign in with one of the buttons before saving. Include the affected screen and what happened.
Leave unreleased or unexercised workflows as Not tested. Feedback remains available until this disposable server stops;
I will export it before cleanup. <a href="/__acceptance/feedback">View recorded feedback</a>.</p>
<table><thead><tr><th>Area</th><th>Task</th><th>Judgment and observation</th></tr></thead><tbody>''' + rows + '''</tbody></table>
<script>
async function identity(){const r=await fetch('/api/v1/me');if(!r.ok)throw new Error('Choose an account first.');return r.json();}
for(const form of document.querySelectorAll('[data-area]'))form.addEventListener('submit',async event=>{
event.preventDefault();const output=form.querySelector('output');output.textContent='Saving…';
try{const me=await identity();const body=Object.fromEntries(new FormData(form));body.area=form.dataset.area;
const r=await fetch('/__acceptance/feedback',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token,
'X-Expected-Account-Id':String(me.account.id)},body:JSON.stringify(body)});
if(!r.ok)throw new Error('Feedback was not saved ('+r.status+').');output.textContent='Saved.';
}catch(error){output.textContent=error.message;}});
fetch('/__acceptance/feedback').then(r=>r.json()).then(data=>{for(const row of data.observations){const form=document.querySelector('[data-area="'+row.area+'"]');
if(form){for(const name of ['status','screen','observation'])form.elements[name].value=row[name];}}});
</script></main></body></html>'''

    @harness.post('/__acceptance/login')
    def login(account_id: int):
        if account_id not in {1, 2, 3}:
            raise HTTPException(400, 'Unknown synthetic identity')
        with get_session_factory()() as db:
            token, session = create_session(db, account_id)
            db.commit()
            response = RedirectResponse('/curator/classifications' if account_id == 3 else '/', status_code=303)
            set_cookie(response, SESSION_COOKIE, token, 7 * 86400)
            return response

    @harness.get('/__acceptance/feedback')
    def feedback():
        return {'synthetic_environment': True, 'observations': observations}

    @harness.post('/__acceptance/feedback')
    def save_feedback(body: Observation, request: Request):
        principal = require_account(request)
        if body.area not in {area for area, _, _ in CHECKLIST}:
            raise HTTPException(422, 'Unknown acceptance area')
        if body.status not in {'Approved', 'Changes requested', 'Not tested'}:
            raise HTTPException(422, 'Unknown acceptance judgment')
        if body.status == 'Changes requested' and not body.observation.strip():
            raise HTTPException(422, 'Describe the requested change')
        observations[:] = [row for row in observations if row['area'] != body.area]
        observations.append({**body.model_dump(), 'fixture_account_id': principal.id,
            'recorded_at': datetime.now(timezone.utc).isoformat()})
        temp = evidence_file.with_suffix('.tmp')
        temp.write_text(json.dumps({'synthetic_environment': True, 'observations': observations}, indent=2) + '\n')
        temp.replace(evidence_file)
        return {'saved': True, 'area': body.area}

    def reset_feedback() -> None:
        observations.clear()
        evidence_file.unlink(missing_ok=True)

    return reset_feedback


def require_test_environment() -> None:
    if get_settings().app.env != 'test':
        raise RuntimeError('Acceptance controls require the disposable test environment')
