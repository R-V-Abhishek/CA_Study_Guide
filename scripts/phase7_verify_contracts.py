"""Bind readiness contracts and every lazy production asset to one source build."""
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
            '/api/v1/coverage', '/api/v1/admin/readiness',
            '/api/v1/admin/readiness/bindings', '/api/v1/admin/readiness/inventory',
            '/api/v1/admin/readiness/priors'}
assert required.issubset(app.openapi()['paths'])
artifacts = {}
for name in ('student', 'curator'):
    dist = Path('web/apps') / name / 'dist'
    references = re.findall(r'(?:src|href)="([^"]*/assets/[^"]+)"', (dist / 'index.html').read_text())
    assert len(references) >= 2
    for reference in references:
        path = dist / 'assets' / reference.rsplit('/', 1)[-1]
        assert path.is_file(), f'Missing referenced asset: {path}'
    builds = set()
    lazy_references = set()
    for bundle in sorted(dist.glob('assets/*.js')):
        content = bundle.read_text()
        builds.update(re.findall(r'[0-9a-f]{7,40}-[0-9a-f]{12}', content))
        # Vite emits static imports, import() chunks and preload dependency arrays.
        for reference in re.findall(r'["\']([^"\']+\.(?:js|css))["\']', content):
            if reference.startswith(('https:', 'http:', 'data:')):
                continue
            if reference.startswith('/assets/') or reference.startswith('/curator/assets/'):
                path = dist / 'assets' / reference.rsplit('/', 1)[-1]
            elif reference.startswith('assets/'):
                path = dist / reference
            elif reference.startswith('./') or '/' not in reference:
                path = bundle.parent / reference
            else:
                continue
            assert path.is_file(), f'Missing lazy/preload asset {reference} in {bundle}'
            lazy_references.add(str(path))
    assert len(builds) == 1, f'Expected one source build identity across all chunks: {builds}'
    assets = [{'path': str(path), 'sha256': checksum(path)}
              for path in sorted((dist / 'assets').iterdir()) if path.is_file()]
    artifacts[name] = {'build': builds.pop(), 'lazy_references_checked': sorted(lazy_references), 'assets': assets}
assert artifacts['student']['build'] == artifacts['curator']['build']
result = {'generated_at': datetime.now(timezone.utc).isoformat(),
          'openapi_matches_application': True, 'required_readiness_paths_present': True,
          'openapi_sha256': checksum(Path('openapi.json')),
          'typescript_contract_sha256': checksum(Path('web/packages/api-client/src/generated.ts')),
          'distributions': artifacts}
Path('docs/Phase7_Build_Verification.json').write_text(json.dumps(result, indent=2) + '\n')
print('Phase 7 contracts and lazy production assets verified:', artifacts['student']['build'])
