from __future__ import annotations

import io

import numpy as np
from PIL import Image

from backend.services.analysis import analyze_image
from backend.services.learning import FEATURE_DIM, features_from_fields
from backend.utils.dimensions import resolve_dimensions
from backend.utils.prompts import compose_negative, compose_prompt, model_defaults, tokenize


def test_dimensions_align_and_cap() -> None:
    square = resolve_dimensions("1:1", 1024)
    assert (square.width, square.height) == (1024, 1024)
    assert square.width % 16 == 0 and square.height % 16 == 0

    wide = resolve_dimensions("16:9", 1024)
    assert wide.width > wide.height
    assert wide.width % 16 == 0 and wide.height % 16 == 0

    capped = resolve_dimensions("1:1", 2048, max_pixels=2_000_000)
    assert capped.width * capped.height <= 2_100_000

    custom = resolve_dimensions("1:1", 1024, width=777, height=555)
    assert custom.width % 16 == 0 and custom.height % 16 == 0


def test_prompt_composition_is_idempotent() -> None:
    once = compose_prompt("a quiet lake", "cinematic", ["mist"], enhance=True)
    twice = compose_prompt(once, "cinematic", ["mist"], enhance=True)
    assert once == twice
    assert "cinematic lighting" in once
    assert "mist" in once
    assert "illustration" in compose_negative("", "photography", ["blurry"])


def test_model_defaults() -> None:
    assert model_defaults("stabilityai/sd-turbo") == (4, 0.0)
    assert model_defaults("stabilityai/stable-diffusion-xl-base-1.0")[0] == 28
    assert model_defaults("black-forest-labs/FLUX.1-schnell")[0] == 4


def test_tokenize() -> None:
    tokens = tokenize("A misty forest, 发光的水面, cinematic lighting")
    assert "misty" in tokens
    assert "forest" in tokens
    assert any("\u4e00" <= char <= "\u9fff" for char in "".join(tokens))


def test_image_analysis() -> None:
    rng = np.random.default_rng(42)
    array = rng.integers(0, 255, (384, 384, 3), dtype=np.uint8)
    noisy = Image.fromarray(array, "RGB")
    result = analyze_image(noisy)
    assert 0 <= result["technical_score"] <= 100
    assert result["phash"]
    assert len(result["palette"]) >= 1
    assert result["tags"]

    smooth = Image.new("RGB", (384, 384), (18, 20, 24))
    result_smooth = analyze_image(smooth)
    assert result_smooth["sharpness"] <= result["sharpness"] + 1


def test_feature_vector_shape() -> None:
    vector = features_from_fields(
        prompt="a quiet lake",
        negative_prompt="blur",
        style="cinematic",
        steps=8,
        guidance=2.5,
        scheduler="euler",
        width=1024,
        height=768,
        provider_id="local",
        model="sd-turbo",
        analysis={"technical_score": 70},
        mode="txt2img",
        strength=0,
    )
    assert vector.shape == (FEATURE_DIM,)
    assert vector.max() <= 2.0
