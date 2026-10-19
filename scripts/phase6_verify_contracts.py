"""Bind the Phase 6 API contracts and production bundles to one source build."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from caf_api.main import app


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert json.loads(Path('openapi.json').read_text()) == app.openapi()
required = {'/api/v1/questions', '/api/v1/questions/{question_id}', '/api/v1/search',
            '/api/v1/appearances/{appearance_id}', '/api/v1/coverage',
            '/api/v1/published-sources/{source_id}', '/api/v1/published-assets/{asset_id}'}
assert required.issubset(app.openapi()['paths'])
artifacts = {}
for name in ('student', 'curator'):
    dist = Path('web/apps') / name / 'dist'
    references = re.findall(r'(?:src|href)="([^"]*/assets/[^"]+)"', (dist / 'index.html').read_text())
    assert len(references) >= 2
    assets = []
    for reference in references:
        path = dist / 'assets' / reference.rsplit('/', 1)[-1]
        assert path.is_file(), f'Missing referenced asset: {path}'
        assets.append({'path': str(path), 'sha256': checksum(path)})
    build = re.search(r'[0-9a-f]{7,40}-[0-9a-f]{12}', next(dist.glob('assets/*.js')).read_text())
    assert build, 'Expected embedded source build identity'
    artifacts[name] = {'build': build.group(), 'assets': assets}
assert artifacts['student']['build'] == artifacts['curator']['build']
result = {'generated_at': datetime.now(timezone.utc).isoformat(),
          'openapi_matches_application': True, 'required_reader_paths_present': True,
          'openapi_sha256': checksum(Path('openapi.json')),
          'typescript_contract_sha256': checksum(Path('web/packages/api-client/src/generated.ts')),
          'distributions': artifacts}
Path('docs/Phase6_Build_Verification.json').write_text(json.dumps(result, indent=2) + '\n')
print('Phase 6 contracts and production assets verified:', artifacts['student']['build'])
