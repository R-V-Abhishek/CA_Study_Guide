"""Verify checked-in contracts and record final built asset identities."""

import hashlib
import json
from pathlib import Path
import re

from caf_api.main import app

assert json.loads(Path('openapi.json').read_text()) == app.openapi()
artifacts = {}
for name in ('student', 'curator'):
    dist = Path('web/apps') / name / 'dist'
    html = (dist / 'index.html').read_text()
    referenced = re.findall(r'(?:src|href)="([^"]+/assets/[^\"]+)"', html)
    if not referenced:
        referenced = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
    assert len(referenced) >= 2
    assets = []
    for reference in referenced:
        file = dist / 'assets' / reference.rsplit('/', 1)[-1]
        assert file.is_file()
        assets.append({'path': str(file), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    bundle = next(dist.glob('assets/*.js')).read_text()
    build = re.search(r'[0-9a-f]{7,40}-[0-9a-f]{12}', bundle)
    assert build, 'Expected embedded tested source build identity'
    artifacts[name] = {'build': build.group(), 'assets': assets}
assert artifacts['student']['build'] == artifacts['curator']['build']
Path('docs/Phase2_Build_Verification.json').write_text(json.dumps({'openapi_matches_application': True,
    'distributions': artifacts, 'real_provider_evidence': 'Phase2_Auth0_Verification.json'}, indent=2) + '\n')
print('OpenAPI and both distributions agree:', artifacts['student']['build'])
