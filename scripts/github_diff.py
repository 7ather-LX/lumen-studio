import hashlib
import json
import subprocess
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

root = Path(__file__).resolve().parent.parent
repo = Repo(str(root))
porcelain.add(repo, paths=[str(root / p) for p in [
    "backend", "docs", "electron", "public", "scripts", "src",
    "README.md", "CHANGELOG.md", "package.json", "pnpm-lock.yaml",
    "index.html", "build/icon.ico", "build/icon.png", "build/icon-generated.png",
    ".github", "SMARTSCREEN.txt",
] if (root / p).exists()])
index = repo.open_index()


def gh(args):
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout


remote = json.loads(gh(["repos/7ather-LX/lumen-studio/git/trees/main?recursive=1"]))
remote_map = {item["path"]: item["sha"] for item in remote["tree"] if item["type"] == "blob"}
changed = []
for path, entry in index.items():
    name = path.decode("utf-8")
    file = root / name
    if not file.is_file():
        continue
    data = file.read_bytes()
    sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if remote_map.get(name) != sha:
        changed.append((name, len(data)))
for item in sorted(changed):
    print(item)
print("count", len(changed))
