#!/usr/bin/env node
/**
 * Build a self-contained Python runtime for the Windows installer.
 *
 * The Electron installer ships CPython's embeddable distribution plus the
 * lightweight backend dependencies. PyTorch/Diffusers are intentionally NOT
 * bundled: they are 1.5–6 GB and are installed on demand from the in-app
 * "local engine" screen into this same runtime.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const PYTHON_VERSION = process.env.LUMEN_PYTHON_VERSION || "3.12.10";
const root = path.resolve(import.meta.dirname, "..");
const buildDir = path.join(root, "build");
const target = path.join(buildDir, "python");
const zipPath = path.join(buildDir, `python-${PYTHON_VERSION}-embed-amd64.zip`);
const indexUrl = process.env.LUMEN_PIP_INDEX || "https://pypi.org/simple";
const mirrors = [
  process.env.LUMEN_PYTHON_EMBED_URL,
  `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`,
  `https://registry.npmmirror.com/-/binary/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`,
].filter(Boolean);

function run(command, args, options = {}) {
  console.log(`\n> ${command} ${args.join(" ")}`);
  const result = spawnSync(command, args, {
    stdio: "inherit",
    cwd: options.cwd || root,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", ...(options.env || {}) },
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited with ${result.status}`);
}

async function download(url, destination) {
  console.log(`Downloading ${url}`);
  const response = await fetch(url, { redirect: "follow", signal: AbortSignal.timeout(180_000) });
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
  const buffer = Buffer.from(await response.arrayBuffer());
  if (buffer.length < 1024) throw new Error(`Downloaded file is suspiciously small: ${buffer.length} bytes`);
  await fsp.mkdir(path.dirname(destination), { recursive: true });
  await fsp.writeFile(destination, buffer);
  return buffer.length;
}

async function main() {
  if (process.platform !== "win32") {
    throw new Error("The packaged backend runtime currently targets Windows x64 only.");
  }
  if (process.env.LUMEN_SKIP_BACKEND_BUILD === "1") {
    console.log("LUMEN_SKIP_BACKEND_BUILD=1, skipping.");
    return;
  }
  await fsp.mkdir(buildDir, { recursive: true });
  await fsp.mkdir(path.join(buildDir, ".piptmp"), { recursive: true });
  if (fs.existsSync(target)) {
    console.log("Removing previous build/python …");
    await fsp.rm(target, { recursive: true, force: true });
  }

  let lastError;
  const cachedZip = fs.existsSync(zipPath) && fs.statSync(zipPath).size > 5_000_000;
  if (cachedZip) {
    console.log(`Using cached ${path.basename(zipPath)}`);
  } else {
    for (const url of mirrors) {
      try {
        await download(url, zipPath);
        lastError = null;
        break;
      } catch (error) {
        lastError = error;
        console.warn(`Mirror failed: ${error.message}`);
      }
    }
    if (lastError) throw lastError;
  }

  console.log("Extracting CPython embeddable runtime …");
  await fsp.mkdir(target, { recursive: true });
  run("tar.exe", ["-xf", zipPath, "-C", target]);

  const pthPath = path.join(target, "python312._pth");
  const originalPth = fs.existsSync(pthPath) ? await fsp.readFile(pthPath, "utf8") : "python312.zip\n.\n";
  const pthLines = originalPth
    .split(/\r?\n/)
    .filter((line) => line.trim() && line.trim() !== "#import site" && line.trim() !== "import site");
  pthLines.push("Lib\\site-packages", "..", "import site");
  await fsp.writeFile(pthPath, `${[...new Set(pthLines)].join("\r\n")}\r\n`, "utf8");
  await fsp.mkdir(path.join(target, "Lib", "site-packages"), { recursive: true });

  // The embeddable distribution has no pip. Install pip and the pure-Python
  // backend stack with the host Python 3.12 into the embeddable site-packages;
  // this avoids a second network bootstrap and is reproducible in CI.
  const hostCandidates = [
    process.env.LUMEN_HOST_PYTHON,
    "python",
    path.join(root, ".venv", "Scripts", "python.exe"),
  ].filter(Boolean);
  let hostPython;
  for (const candidate of hostCandidates) {
    if (candidate !== "python" && !fs.existsSync(candidate)) continue;
    const probe = spawnSync(candidate, ["-c", "import sys, pip; assert sys.version_info[:2] == (3, 12)"], {
      stdio: "ignore",
      windowsHide: true,
    });
    if (probe.status === 0) {
      hostPython = candidate;
      break;
    }
  }
  if (!hostPython) {
    throw new Error("A Python 3.12 host with pip was not found (set LUMEN_HOST_PYTHON).");
  }
  console.log(`Host Python: ${hostPython}`);

  console.log(`Installing pip and backend dependencies from ${indexUrl} …`);
  const pipArgs = [
    "-m",
    "pip",
    "install",
    "--target",
    path.join(target, "Lib", "site-packages"),
    "--upgrade",
    "--no-cache-dir",
    "--disable-pip-version-check",
    "--no-warn-script-location",
    "--index-url",
    indexUrl,
    "pip",
    "-r",
    path.join(root, "backend", "requirements-core.txt"),
  ];
  if (indexUrl.includes("tuna.tsinghua.edu.cn")) pipArgs.push("--trusted-host", "pypi.tuna.tsinghua.edu.cn");
  run(hostPython, pipArgs, {
    cwd: root,
    env: { PIP_DISABLE_PIP_VERSION_CHECK: "1", TEMP: path.join(buildDir, ".piptmp"), TMP: path.join(buildDir, ".piptmp") },
  });

  console.log("Verifying runtime …");
  run(path.join(target, "python.exe"), [
    "-c",
    "import fastapi, uvicorn, httpx, pydantic, PIL, numpy, pip, sys; print('runtime ok', sys.version)",
  ]);

  // Strip caches and tests to keep the installer lean.
  async function clean(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of await fsp.readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__") {
          await fsp.rm(full, { recursive: true, force: true });
        } else {
          await clean(full);
        }
      } else if (entry.name.endsWith(".pyc") || entry.name.endsWith(".pyo")) {
        await fsp.rm(full, { force: true });
      }
    }
  }
  await clean(path.join(target, "Lib", "site-packages"));
  await fsp.rm(zipPath, { force: true });
  await fsp.rm(path.join(buildDir, ".piptmp"), { recursive: true, force: true });

  let size = 0;
  async function measure(dir) {
    for (const entry of await fsp.readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) await measure(full);
      else size += (await fsp.stat(full)).size;
    }
  }
  await measure(target);
  console.log(`\nBackend runtime ready: ${target} (${(size / 1024 / 1024).toFixed(1)} MB)`);
  console.log("PyTorch/Diffusers will be installed on demand into this runtime.");
}

main().catch((error) => {
  console.error("\nBackend runtime build failed:", error);
  process.exit(1);
});
