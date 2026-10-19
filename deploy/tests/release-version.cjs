// Run with NODE_PATH pointing at a temporary installation of release-please@17.3.0.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
require('release-please'); // Initialize the library before loading strategy modules.
const base = path.dirname(require.resolve('release-please'));
const { GenericToml } = require(path.join(base, 'updaters/generic-toml'));
const { Version } = require(path.join(base, 'version'));
const { Python } = require(path.join(base, 'strategies/python'));
const { parseConventionalCommits } = require(path.join(base, 'commit'));
const root = path.resolve(__dirname, '../..');
const config = JSON.parse(fs.readFileSync(path.join(root, 'release-please-config.json'))).packages['.'];
const original = fs.readFileSync(path.join(root, 'uv.lock'), 'utf8');
const oldVersion = JSON.parse(fs.readFileSync(path.join(root, '.release-please-manifest.json')))['.'];
const updated = new GenericToml(config['extra-files'][0].jsonpath, Version.parse('8.7.6')).updateContent(original);
const expected = original.replace(`name = "ca-final"\nversion = "${oldVersion}"`, 'name = "ca-final"\nversion = "8.7.6"');
assert(expected !== original, 'Fixture must locate the root project lock entry');
assert(updated === expected, 'Only the root project lock version may change');
const strategy = new Python({ github: { repository: { owner: 'fixture', repo: 'fixture' } }, targetBranch: 'main' });
const commits = parseConventionalCommits([{ sha: 'a'.repeat(40), message: 'feat: release automation\n\nRelease-As: 0.2.0' }]);
strategy.buildNewVersion(commits).then(version => {
  assert.equal(version.toString(), '0.2.0');
  console.log('PASS: pinned release version calculation and precise uv.lock update');
}).catch(error => { console.error(error.message); process.exitCode = 1; });
