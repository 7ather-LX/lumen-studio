from __future__ import annotations

import base64
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import create_app


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    current = {}
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        current = response.json()
        if current["status"] in ("succeeded", "failed", "cancelled"):
            return current
        time.sleep(0.2)
    raise AssertionError(f"job did not finish: {current}")


def test_health_and_presets(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    presets = client.get("/api/meta/presets").json()
    assert presets["styles"]
    assert presets["aspects"]
    assert presets["hardware"]["tiers"]


def test_demo_generation_and_feedback(client: TestClient) -> None:
    response = client.post(
        "/api/generate",
        json={
            "prompt": "a quiet lake at blue hour, mist, cinematic",
            "style": "cinematic",
            "aspect_ratio": "16:9",
            "long_edge": 640,
            "provider_id": "demo",
            "batch_size": 1,
        },
    )
    assert response.status_code == 200, response.text
    submitted = response.json()
    assert submitted["width"] > submitted["height"]
    job = wait_for_job(client, submitted["job_id"])
    assert job["status"] == "succeeded", job
    images = job["result"]["images"]
    assert len(images) == 1
    image = images[0]
    assert image["analysis"]["technical_score"] >= 0
    assert image["width"] > image["height"]

    file_response = client.get(f"/api/images/{image['id']}/file")
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "image/png"
    thumb_response = client.get(f"/api/images/{image['id']}/file?thumb=1")
    assert thumb_response.status_code == 200

    feedback = client.post(f"/api/images/{image['id']}/feedback", json={"rating": 5, "favorite": True})
    assert feedback.status_code == 200
    assert feedback.json()["image"]["rating"] == 5
    insights = client.get("/api/learning/insights").json()
    assert insights["feedback_samples"] == 1

    gallery = client.get("/api/images?limit=10").json()
    assert gallery["total"] == 1
    assert gallery["items"][0]["favorite"] is True


def test_img2img_upload(client: TestClient) -> None:
    source = Image.new("RGB", (256, 256), (70, 110, 90))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    response = client.post(
        "/api/generate",
        json={
            "prompt": "turn this into a glowing forest",
            "mode": "img2img",
            "init_image": data_url,
            "provider_id": "demo",
            "long_edge": 512,
            "strength": 0.6,
        },
    )
    assert response.status_code == 200, response.text
    job = wait_for_job(client, response.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["images"][0]["mode"] == "img2img"


def test_crop_and_reveal(client: TestClient) -> None:
    response = client.post(
        "/api/generate",
        json={"prompt": "a geometric garden", "provider_id": "demo", "long_edge": 512},
    )
    job = wait_for_job(client, response.json()["job_id"])
    source = job["result"]["images"][0]
    cropped = client.post(f"/api/images/{source['id']}/crop", json={"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5})
    assert cropped.status_code == 200, cropped.text
    record = cropped.json()
    assert record["mode"] == "crop"
    assert record["init_image_id"] == source["id"]
    assert record["width"] <= source["width"]
    assert record["height"] <= source["height"]
    assert client.get(f"/api/images/{record['id']}/file").status_code == 200

    reveal = client.get(f"/api/images/{record['id']}/reveal")
    assert reveal.status_code == 200
    assert reveal.json()["path"].endswith(".png")

    invalid = client.post(f"/api/images/{source['id']}/crop", json={"x": 0.8, "y": 0.8, "width": 0.5, "height": 0.5})
    assert invalid.status_code == 422
    assert client.get(f"/api/images/{source['id']}/file").status_code == 200


def test_settings_validation(client: TestClient) -> None:
    bad = client.patch("/api/settings", json={"max_pixels": 100})
    assert bad.status_code == 400
    good = client.patch("/api/settings", json={"adaptive_enabled": False, "local_engine": {"low_vram": True}})
    assert good.status_code == 200
    assert good.json()["adaptive_enabled"] is False
    assert good.json()["local_engine"]["low_vram"] is True


def test_provider_default_is_preserved(client: TestClient) -> None:
    demo = next(item for item in client.get("/api/providers").json() if item["id"] == "demo")
    response = client.put(
        "/api/providers/demo",
        json={
            "name": demo["name"],
            "kind": "demo",
            "base_url": "",
            "model": demo["model"],
            "enabled": True,
            "options": demo["options"],
        },
    )
    assert response.status_code == 200
    assert response.json()["is_default"] is True


def test_token_auth(tmp_path: Path) -> None:
    app = create_app(tmp_path, token="test-token")
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 401
        assert client.get("/api/health", headers={"X-Lumen-Token": "test-token"}).status_code == 200
        assert client.get("/api/health?token=test-token").status_code == 200


def test_learning_model_trains(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        state = app.state.lumen
        rewards = [5, 2, 4, 1, 5, 3, 4, 5, 2, 4]
        for index, rating in enumerate(rewards):
            image_id = f"img_test_{index}"
            width = 512 if index % 2 == 0 else 768
            state.db.insert_image(
                {
                    "id": image_id,
                    "file": f"images/{image_id}.png",
                    "thumb": f"thumbs/{image_id}.webp",
                    "mime": "image/png",
                    "prompt": "misty forest cinematic" if rating >= 4 else "blurry noisy clutter",
                    "negative_prompt": "",
                    "mode": "txt2img",
                    "provider_id": "demo",
                    "provider_name": "Demo",
                    "model": "lumen-demo-v1",
                    "width": width,
                    "height": width,
                    "steps": 4 if rating >= 4 else 25,
                    "guidance": 1.0 if rating >= 4 else 8.0,
                    "seed": index,
                    "strength": 0,
                    "scheduler": "euler" if rating >= 4 else "ddim",
                    "style": "cinematic" if rating >= 4 else "none",
                    "init_image_id": None,
                    "batch_index": 0,
                    "favorite": rating == 5,
                    "rating": rating,
                    "notes": "",
                    "tags": [],
                    "analysis": {"technical_score": 50 + rating * 5, "sharpness": 65},
                    "params": {},
                    "generation_ms": 100,
                    "created_at": f"2026-01-{index + 1:02d}T10:00:00+00:00",
                }
            )
            state.learning.sync_feedback(image_id)
        model = state.learning.train(force=True)
        assert model is not None
        from backend.services.learning import FEATURE_DIM

        assert model["dim"] == FEATURE_DIM
        suggestion = state.learning.suggest(
            prompt="misty forest",
            negative_prompt="",
            style="cinematic",
            width=512,
            height=512,
            provider_id="demo",
            model="lumen-demo-v1",
        )
        assert suggestion is not None
        assert 1 <= suggestion["steps"] <= 100
        insights = client.get("/api/learning/insights").json()
        assert insights["model"]["samples"] == 10
        assert insights["tokens"]["positive"]
