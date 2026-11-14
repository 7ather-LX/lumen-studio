"""Create the GitHub release and upload assets via the REST API.

Used when Git for Windows is unavailable. Reads GH_TOKEN from the environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OWNER = "7ather-LX"
REPO = "lumen-studio"
TAG = "v0.1.0"
TARGET = "a870d3a7d90d0cb890bb0fbf986a6319493c8972"
ASSETS = [
    ROOT / "release" / "Lumen-Studio-Setup-0.1.0.exe",
    ROOT / "release" / "latest.yml",
    ROOT / "release" / "Lumen-Studio-Setup-0.1.0.exe.blockmap",
    ROOT / "release" / "SHA256SUMS.txt",
]


def main() -> int:
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        print("GH_TOKEN missing", file=sys.stderr)
        return 2
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = (ROOT / "docs" / "RELEASE_NOTES_v0.1.0.md").read_text(encoding="utf-8")
    payload = {
        "tag_name": TAG,
        "target_commitish": TARGET,
        "name": "Lumen Studio v0.1.0",
        "body": body,
        "draft": False,
        "prerelease": False,
        "make_latest": "true",
    }
    response = requests.post(
        f"https://api.github.com/repos/{OWNER}/{REPO}/releases",
        headers=headers,
        json=payload,
        timeout=120,
    )
    if response.status_code == 422:
        response = requests.get(
            f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}",
            headers=headers,
            timeout=60,
        )
    if response.status_code >= 400:
        print(response.status_code, response.text[:1000], file=sys.stderr)
        return 1
    release = response.json()
    upload_url = release["upload_url"].split("{", 1)[0]
    release_id = release["id"]
    print("RELEASE", release["html_url"])
    for asset in ASSETS:
        if not asset.exists():
            print("missing asset", asset, file=sys.stderr)
            return 1
        print("uploading", asset.name, f"{asset.stat().st_size / 1024 / 1024:.1f} MB", flush=True)
        with asset.open("rb") as stream:
            upload = requests.post(
                upload_url,
                headers={**headers, "Content-Type": "application/octet-stream"},
                params={"name": asset.name},
                data=stream,
                timeout=1800,
            )
        if upload.status_code not in (200, 201, 422):
            print(upload.status_code, upload.text[:1000], file=sys.stderr)
            return 1
        print("  ", upload.status_code, asset.name, flush=True)
    print("ASSETS", sorted(item["name"] for item in requests.get(
        f"https://api.github.com/repos/{OWNER}/{REPO}/releases/{release_id}/assets",
        headers=headers,
        timeout=60,
    ).json()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
