import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync, spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const hash = createHash("sha256");
function addDirectory(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    if (["node_modules", "dist", ".turbo"].includes(entry.name)) continue;
    const file = resolve(directory, entry.name);
    if (entry.isDirectory()) addDirectory(file);
    else if (entry.isFile()) hash.update(relative(root, file)).update(readFileSync(file));
  }
}
addDirectory(resolve(root, "apps"));
addDirectory(resolve(root, "packages"));
hash.update(readFileSync(resolve(root, "pnpm-lock.yaml")));
const revision = process.env.CAF_SOURCE_REVISION || execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
const build = `${revision}-${hash.digest("hex").slice(0, 12)}`;
console.log(`Frontend build: ${build}`);
const result = spawnSync("pnpm", ["exec", "turbo", "build", "--force"], {
  cwd: root, stdio: "inherit", shell: process.platform === "win32",
  env: { ...process.env, VITE_BUILD_REVISION: build },
});
process.exit(result.status ?? 1);
