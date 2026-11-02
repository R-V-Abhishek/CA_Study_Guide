// Fails when the tracked frontend build output was not produced from the current sources.
// The build id embedded in each bundle is "<git revision>-<source hash>"; only the
// source-hash part is comparable, because a commit cannot contain its own revision.
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { root, sourceHash } from "./source-hash.mjs";

const expected = sourceHash();
let failed = false;
for (const app of ["student", "curator"]) {
  const assets = resolve(root, "apps", app, "dist", "assets");
  const bundles = readdirSync(assets).filter((name) => name.endsWith(".js"));
  const ids = new Set(bundles.flatMap((name) => readFileSync(resolve(assets, name), "utf8").match(/[0-9a-f]{7,40}-[0-9a-f]{12}/g) ?? []));
  const current = [...ids].some((id) => id.endsWith(`-${expected}`));
  console.log(`${app}: ${current ? "current" : "STALE"} (expected -${expected}, found ${[...ids].join(", ") || "none"})`);
  failed ||= !current;
}
if (failed) {
  console.error("Tracked dist is stale. Run `pnpm build` in web/ and commit web/apps/*/dist.");
  process.exit(1);
}
