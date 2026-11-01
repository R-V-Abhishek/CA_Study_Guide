import { execFileSync, spawnSync } from "node:child_process";
import { root, sourceHash } from "./source-hash.mjs";

const revision = process.env.CAF_SOURCE_REVISION || execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
const build = `${revision}-${sourceHash()}`;
console.log(`Frontend build: ${build}`);
const result = spawnSync("pnpm", ["exec", "turbo", "build", "--force"], {
  cwd: root, stdio: "inherit", shell: process.platform === "win32",
  env: { ...process.env, VITE_BUILD_REVISION: build },
});
process.exit(result.status ?? 1);
