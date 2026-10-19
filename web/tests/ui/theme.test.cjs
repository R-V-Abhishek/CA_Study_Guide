const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../..');
const ts = createRequire(path.join(root, 'apps/student/package.json'))('typescript');

function environment(preference, osDark, denied = false) {
  const values = new Map(preference === null ? [] : [['caf_theme', preference]]);
  const classes = new Set(['dark']);
  const media = Object.assign(new EventTarget(), { matches: osDark });
  const window = Object.assign(new EventTarget(), { matchMedia: () => media });
  const effects = [];
  const context = {
    exports: {}, Event, window, matchMedia: window.matchMedia,
    localStorage: { getItem: key => { if (denied) throw Error('Storage unavailable'); return values.get(key) ?? null; }, setItem: (key, value) => values.set(key, value) },
    document: { documentElement: { classList: { toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name) } } },
    require: () => ({ useEffect: fn => effects.push(fn()), useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}] }),
  };
  return { context, classes, values, media, window, effects };
}

for (const app of ['student', 'curator']) {
  const html = fs.readFileSync(path.join(root, `apps/${app}/index.html`), 'utf8');
  const initial = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  for (const osDark of [false, true]) for (const preference of [null, 'invalid', 'light', 'dark', 'system']) {
    test(`${app}: pre-paint ${preference ?? 'missing'} / OS ${osDark ? 'dark' : 'light'}`, () => {
      assert.match(html, /<html lang="en" class="dark">/);
      assert.ok(html.indexOf(initial) < html.indexOf('type="module"'));
      const env = environment(preference, osDark);
      vm.runInNewContext(initial, env.context);
      assert.equal(env.classes.has('dark'), preference === 'light' ? false : preference === 'system' ? osDark : true);
    });
  }
  test(`${app}: pre-paint storage failure stays dark`, () => {
    const env = environment(null, false, true);
    vm.runInNewContext(initial, env.context);
    assert.equal(env.classes.has('dark'), true);
  });
}

test('theme hook persists System and synchronises storage and same-document events', () => {
  const env = environment(null, false);
  const source = fs.readFileSync(path.join(root, 'packages/workspace/theme.tsx'), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } });
  vm.runInNewContext(outputText, env.context);
  const theme = env.context.exports.useTheme();
  assert.equal(theme.preference, 'dark');
  assert.equal(env.classes.has('dark'), true);
  theme.choose('light');
  assert.equal(env.classes.has('dark'), false);
  assert.equal(env.values.get('caf_theme'), 'light');
  theme.choose('system');
  assert.equal(env.values.get('caf_theme'), 'system');
  env.media.matches = true;
  env.media.dispatchEvent(new Event('change'));
  assert.equal(env.classes.has('dark'), true);
  env.values.set('caf_theme', 'light');
  env.window.dispatchEvent(new Event('storage'));
  assert.equal(env.classes.has('dark'), false);
  env.values.set('caf_theme', 'invalid');
  env.window.dispatchEvent(new Event('storage'));
  assert.equal(env.classes.has('dark'), true);
  env.effects.forEach(cleanup => cleanup());
});

function luminance(hex) {
  return hex.match(/[0-9a-f]{2}/gi).map(value => parseInt(value, 16) / 255)
    .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
    .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
}
for (const theme of ['light', 'dark']) {
  test(`${theme}: text, secondary, semantic and action contrast meets 4.5:1`, () => {
    const css = fs.readFileSync(path.join(root, 'packages/workspace/tokens.css'), 'utf8');
    const block = css.match(theme === 'light' ? /:root\s*{([\s\S]*?)}/ : /\.dark\s*{([\s\S]*?)}/)[1];
    const tokens = Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)].map(match => [match[1], match[2]]));
    for (const foreground of ['text', 'secondary', 'accent', 'warning', 'error']) for (const background of ['canvas', 'surface', 'subtle']) {
      const a = luminance(tokens[foreground]); const b = luminance(tokens[background]);
      const ratio = (Math.max(a,b) + .05) / (Math.min(a,b) + .05);
      assert.ok(ratio >= 4.5, `${foreground} on ${background}: ${ratio.toFixed(2)}:1`);
    }
    const a = luminance(tokens['accent']); const b = luminance(tokens['accent-ink']);
    assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05) >= 4.5);
  });
}
