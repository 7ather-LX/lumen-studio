import base64
import datetime
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parent.parent
exe = root / "release" / "Lumen-Studio-Setup-0.1.1.exe"
data = exe.read_bytes()
digest = base64.b64encode(hashlib.sha512(data).digest()).decode()
sha256 = hashlib.sha256(data).hexdigest().upper()
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
latest = (
    "version: 0.1.1\n"
    "files:\n"
    f"  - url: {exe.name}\n"
    f"    sha512: {digest}\n"
    f"    size: {len(data)}\n"
    f"path: {exe.name}\n"
    f"sha512: {digest}\n"
    f"releaseDate: '{now}'\n"
)
(root / "release" / "latest.yml").write_text(latest, encoding="utf-8")
(root / "release" / "SHA256SUMS.txt").write_text(f"{sha256}  {exe.name}\n", encoding="ascii")
print(sha256)
print(digest)
