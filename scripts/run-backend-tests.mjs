#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const candidates = [
  process.env.LUMEN_PYTHON,
  path.join(root, ".venv", "Scripts", "python.exe"),
  path.join(root, ".venv", "bin", "python"),
  "python",
].filter(Boolean);
const python = candidates.find((candidate) => candidate === "python" || fs.existsSync(candidate));
if (!python) {
  console.error("Python was not found. Create .venv and install backend/requirements-dev.txt.");
  process.exit(1);
}
const result = spawnSync(python, ["-m", "pytest", "backend/tests", "-q", ...process.argv.slice(2)], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  windowsHide: true,
});
process.exit(result.status ?? 1);
