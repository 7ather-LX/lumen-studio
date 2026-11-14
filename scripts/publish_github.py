"""Publish this workspace to GitHub without requiring the git binary.

Used by the maintainer environment where GitHub CLI is authenticated but Git
for Windows is unavailable. Requires GH_TOKEN in the environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

ROOT = Path(__file__).resolve().parent.parent
OWNER = "7ather-LX"
REPO = "lumen-studio"
NAME = "7ather"
EMAIL = "lxnba2932@gmail.com"

TRACKED = [
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".github",
    ".gitignore",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "backend",
    "build/icon.ico",
    "build/icon.png",
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


def main() -> int:
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        print("GH_TOKEN is missing", file=sys.stderr)
        return 2
    if not (ROOT / ".git").exists():
        porcelain.init(str(ROOT))
    repo = Repo(str(ROOT))
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")
    config = repo.get_config()
    config.set((b"user",), b"name", NAME.encode())
    config.set((b"user",), b"email", EMAIL.encode())
    config.write_to_path()
    porcelain.add(repo, paths=[str(ROOT / item) for item in TRACKED if (ROOT / item).exists()])
    status = porcelain.status(repo)
    staged = len(status.staged.get("add", [])) + len(status.staged.get("modify", [])) + len(status.staged.get("delete", []))
    print(f"staged entries: {staged}")
    if not staged:
        print("nothing to commit")
    else:
        commit = porcelain.commit(
            repo,
            message=b"feat: Lumen Studio 0.1.0 local-first AI image studio",
            author=f"{NAME} <{EMAIL}>".encode(),
            committer=f"{NAME} <{EMAIL}>".encode(),
        )
        print("commit", commit.decode())
    url = f"https://x-access-token:{token}@github.com/{OWNER}/{REPO}.git"
    print("pushing main ...")
    porcelain.push(repo, url, refspecs=[b"refs/heads/main:refs/heads/main"])
    print("pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
