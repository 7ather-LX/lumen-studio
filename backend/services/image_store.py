from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

from PIL import Image

from backend.config import SettingsStore
from backend.db import Database, new_id, utcnow
from backend.services.analysis import analyze_image
from backend.services.learning import LearningService
from backend.utils.images import hamming_hex, save_png, save_thumbnail


class ImageStore:
    def __init__(self, db: Database, data_dir: Path, settings: SettingsStore, learning: LearningService):
        self.db = db
        self.data_dir = data_dir
        self.settings = settings
        self.learning = learning
        self.images_dir = data_dir / "images"
        self.thumbs_dir = data_dir / "thumbs"
        self.uploads_dir = data_dir / "uploads"
        for directory in (self.images_dir, self.thumbs_dir, self.uploads_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def save_upload(self, image: Image.Image, name: str = "init.png") -> dict[str, Any]:
        upload_id = new_id("up_")
        path = self.uploads_dir / f"{upload_id}.png"
        save_png(image, path)
        return {"id": upload_id, "path": path, "name": name, "image": image}

    def load_init(self, image_id: str | None, data_url_image: Image.Image | None) -> tuple[Image.Image | None, str | None, str | None]:
        """Return (PIL image, gallery image id, upload path)."""
        if data_url_image is not None:
            upload = self.save_upload(data_url_image)
            return data_url_image, None, str(upload["path"])
        if image_id:
            record = self.db.get_image(image_id)
            if not record:
                raise ValueError("参考图片不存在")
            path = self.resolve(record["file"])
            if not path.exists():
                raise ValueError("参考图片文件缺失")
            image = Image.open(path)
            image.load()
            return image, image_id, None
        return None, None, None

    def resolve(self, relative: str) -> Path:
        path = (self.data_dir / relative).resolve()
        if self.data_dir.resolve() not in path.parents and path != self.data_dir.resolve():
            raise ValueError("非法文件路径")
        return path

    def _duplicate(self, analysis: dict[str, Any]) -> tuple[str | None, int | None]:
        try:
            candidates = self.db.recent_images(80)
        except Exception:
            return None, None
        best_id = None
        best_distance = 65
        for candidate in candidates:
            other = candidate.get("analysis") or {}
            if not other.get("phash"):
                continue
            distance = hamming_hex(str(analysis.get("phash", "")), str(other["phash"]))
            if distance < best_distance:
                best_distance = distance
                best_id = candidate["id"]
        if best_id and best_distance <= 5:
            return best_id, best_distance
        return None, None

    def save_generated(
        self,
        image: Image.Image,
        *,
        prompt: str,
        negative_prompt: str,
        resolved_prompt: str,
        resolved_negative: str,
        mode: str,
        provider: dict[str, Any],
        model: str,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        seed: int,
        strength: float,
        scheduler: str,
        style: str,
        init_image_id: str | None,
        batch_index: int,
        generation_ms: int,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        image_id = new_id("img_")
        image_file = self.images_dir / f"{image_id}.png"
        thumb_file = self.thumbs_dir / f"{image_id}.webp"
        metadata = {
            "Lumen.Prompt": resolved_prompt,
            "Lumen.NegativePrompt": resolved_negative,
            "Lumen.OriginalPrompt": prompt,
            "Lumen.Provider": provider["name"],
            "Lumen.Model": model,
            "Lumen.Seed": seed,
            "Lumen.Steps": steps,
            "Lumen.Guidance": guidance,
            "Lumen.Scheduler": scheduler,
            "Lumen.Size": f"{width}x{height}",
            "Lumen.Software": "Lumen Studio",
        }
        if self.settings.get("privacy.strip_png_metadata", False):
            metadata = {}
        save_png(image, image_file, metadata)
        save_thumbnail(image, thumb_file)
        analysis = analyze_image(image) if self.settings.get("auto_analyze", True) else {}
        if analysis:
            duplicate_id, distance = self._duplicate(analysis)
            if duplicate_id:
                analysis["duplicate_of"] = duplicate_id
                analysis["duplicate_distance"] = distance
                analysis["tags"] = [*analysis.get("tags", []), "相似构图"]
        record = self.db.insert_image(
            {
                "id": image_id,
                "file": str(image_file.relative_to(self.data_dir)),
                "thumb": str(thumb_file.relative_to(self.data_dir)),
                "mime": "image/png",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "mode": mode,
                "provider_id": provider["id"],
                "provider_name": provider["name"],
                "model": model,
                "width": width,
                "height": height,
                "steps": steps,
                "guidance": guidance,
                "seed": seed,
                "strength": strength,
                "scheduler": scheduler,
                "style": style,
                "init_image_id": init_image_id,
                "batch_index": batch_index,
                "favorite": False,
                "rating": None,
                "notes": "",
                "tags": analysis.get("tags", []) if analysis else [],
                "analysis": analysis,
                "params": params,
                "generation_ms": generation_ms,
                "created_at": utcnow(),
            }
        )
        assert record is not None
        return record

    def crop(self, image_id: str, x: float, y: float, width: float, height: float) -> dict[str, Any] | None:
        record = self.db.get_image(image_id)
        if not record:
            return None
        path = self.resolve(record["file"])
        if not path.exists():
            raise ValueError("原图文件缺失")
        with Image.open(path) as source:
            source.load()
            image = source.convert("RGB")
        original_width, original_height = image.size
        left = max(0, min(original_width - 1, round(x * original_width)))
        top = max(0, min(original_height - 1, round(y * original_height)))
        right = max(left + 32, min(original_width, round((x + width) * original_width)))
        bottom = max(top + 32, min(original_height, round((y + height) * original_height)))
        cropped = image.crop((left, top, right, bottom))
        if cropped.width < 32 or cropped.height < 32:
            raise ValueError("裁切区域太小")
        params = dict(record.get("params") or {})
        params["operation"] = "crop"
        params["source_image_id"] = image_id
        params["source_box"] = {
            "x": round(left / original_width, 4),
            "y": round(top / original_height, 4),
            "width": round((right - left) / original_width, 4),
            "height": round((bottom - top) / original_height, 4),
        }
        provider = {"id": "crop", "name": "本地裁切", "kind": "local"}
        return self.save_generated(
            cropped,
            prompt=record["prompt"],
            negative_prompt=record["negative_prompt"],
            resolved_prompt=str(params.get("resolved_prompt") or record["prompt"]),
            resolved_negative=str(params.get("resolved_negative") or record["negative_prompt"]),
            mode="crop",
            provider=provider,
            model="local-crop",
            width=cropped.width,
            height=cropped.height,
            steps=0,
            guidance=0,
            seed=0,
            strength=0,
            scheduler="none",
            style=record.get("style") or "none",
            init_image_id=image_id,
            batch_index=0,
            generation_ms=0,
            params=params,
        )

    def reveal(self, image_id: str) -> str | None:
        record = self.db.get_image(image_id)
        if not record:
            return None
        path = self.resolve(record["file"])
        if not path.exists():
            return None
        return str(path)

    def delete(self, image_id: str) -> bool:
        record = self.db.delete_image(image_id)
        if not record:
            return False
        for key in ("file", "thumb"):
            try:
                self.resolve(record[key]).unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        self.learning.invalidate()
        return True

    def prune_uploads(self, older_than_hours: int = 72) -> None:
        cutoff = time.time() - older_than_hours * 3600
        if not self.settings.get("privacy.keep_init_uploads", True):
            cutoff = time.time()
        for file in self.uploads_dir.glob("*.png"):
            try:
                if file.stat().st_mtime < cutoff:
                    file.unlink()
            except OSError:
                pass
