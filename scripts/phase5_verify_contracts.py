"""Check Phase 5 runtime OpenAPI and record the tested production assets."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from caf_api.main import app


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert json.loads(Path('openapi.json').read_text()) == app.openapi()
artifacts = {}
for name in ('student', 'curator'):
    dist = Path('web/apps') / name / 'dist'
    html = (dist / 'index.html').read_text()
    referenced = re.findall(r'(?:src|href)="([^"]*/assets/[^"]+)"', html)
    assert len(referenced) >= 2
    assets = []
    for reference in referenced:
        path = dist / 'assets' / reference.rsplit('/', 1)[-1]
        assert path.is_file(), f'Missing referenced asset: {path}'
        assets.append({'path': str(path), 'sha256': checksum(path)})
    bundle = next(dist.glob('assets/*.js')).read_text()
    build = re.search(r'[0-9a-f]{7,40}-[0-9a-f]{12}', bundle)
    assert build, 'Expected embedded tested source build identity'
    artifacts[name] = {'build': build.group(), 'assets': assets}
assert artifacts['student']['build'] == artifacts['curator']['build']
result = {'generated_at': datetime.now(timezone.utc).isoformat(),
    'openapi_matches_application': True, 'openapi_sha256': checksum(Path('openapi.json')),
    'typescript_contract_sha256': checksum(Path('web/packages/api-client/src/generated.ts')),
    'distributions': artifacts}
Path('docs/Phase5_Build_Verification.json').write_text(json.dumps(result, indent=2) + '\n')
print('Phase 5 contracts and production assets verified:', artifacts['student']['build'])
