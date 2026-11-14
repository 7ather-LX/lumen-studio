"""Publish changed files through the GitHub Git Data API.

Fallback for networks that block git-receive-pack but allow REST. Uses the
authenticated GitHub CLI, compares local Git blob hashes to the remote tree,
uploads only changed blobs in parallel, then creates a tree/commit and moves
main. No token is printed.
"""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

ROOT = Path(__file__).resolve().parent.parent
OWNER = "7ather-LX"
REPO = "lumen-studio"
API = f"repos/{OWNER}/{REPO}"
GH = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
TRACKED = [
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".github",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "SMARTSCREEN.txt",
    "backend",
    "build/icon.ico",
    "build/icon.png",
    "build/icon-generated.png",
    "docs",
    "electron",
    "index.html",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "public",
    "scripts",
    "src",
    "tsconfig.json",
    "vite.config.mts",
]


def gh(args: list[str], payload: dict | None = None) -> str:
    command = [GH, "api", *args]
    if payload is not None:
        command.extend(["--input", "-"])
    last = ""
    for attempt in range(4):
        result = subprocess.run(
            command,
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        last = result.stderr
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"gh api failed: {' '.join(args)}\n{last[:800]}")


def main() -> int:
    repo = Repo(str(ROOT))
    porcelain.add(repo, paths=[str(ROOT / p) for p in TRACKED if (ROOT / p).exists()])
    index = repo.open_index()
    remote = json.loads(gh([f"{API}/git/trees/main?recursive=1"]))
    remote_map = {item["path"]: item["sha"] for item in remote["tree"] if item["type"] == "blob"}
    changed: list[tuple[str, bytes]] = []
    for path, _entry in index.items():
        name = path.decode("utf-8")
        file = ROOT / name
        if not file.is_file():
            continue
        data = file.read_bytes()
        local_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if remote_map.get(name) != local_sha:
            changed.append((name, data))
    print("changed", len(changed), flush=True)
    parent = gh([f"{API}/git/ref/heads/main", "--jq", ".object.sha"])
    print("parent", parent, flush=True)
    base_tree = gh([f"{API}/git/commits/{parent}", "--jq", ".tree.sha"])

    def upload(item: tuple[str, bytes]) -> dict:
        name, data = item
        sha = gh(
            ["--method", "POST", f"{API}/git/blobs", "--jq", ".sha"],
            {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
        )
        return {"path": name, "mode": "100644", "type": "blob", "sha": sha}

    entries = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for idx, entry in enumerate(pool.map(upload, changed), 1):
            entries.append(entry)
            if idx % 10 == 0:
                print("blobs", idx, flush=True)
    tree_sha = gh(
        ["--method", "POST", f"{API}/git/trees", "--jq", ".sha"],
        {"base_tree": base_tree, "tree": entries},
    )
    message = os.environ.get("COMMIT_MESSAGE", "release: Lumen Studio 0.1.1")
    commit_sha = gh(
        ["--method", "POST", f"{API}/git/commits", "--jq", ".sha"],
        {"message": message, "tree": tree_sha, "parents": [parent]},
    )
    gh(
        ["--method", "PATCH", f"{API}/git/refs/heads/main"],
        {"sha": commit_sha, "force": False},
    )
    print("PUSHED", commit_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
