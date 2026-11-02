import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** Content hash of every frontend source file plus the lockfile; build output is excluded. */
export function sourceHash() {
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
  return hash.digest("hex").slice(0, 12);
}
