from __future__ import annotations

import hashlib
import json
import math
import random
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.db import Database
from backend.utils.prompts import (
    SCHEDULER_PRESETS,
    STYLE_PRESETS,
    model_defaults,
    tokenize,
)

FEATURE_VERSION = 1
STYLE_IDS = [str(item["id"]) for item in STYLE_PRESETS]
SCHEDULER_IDS = [item["id"] for item in SCHEDULER_PRESETS if item["id"] != "auto"]
TOKEN_DIM = 64
PROVIDER_DIM = 8
MODEL_DIM = 8
SCALAR_DIM = 9
METRIC_DIM = 8
FEATURE_DIM = (
    SCALAR_DIM
    + PROVIDER_DIM
    + MODEL_DIM
    + len(STYLE_IDS)
    + len(SCHEDULER_IDS)
    + TOKEN_DIM
    + METRIC_DIM
)

RATING_REWARD = {1: -1.0, 2: -0.55, 3: 0.0, 4: 0.55, 5: 1.0}
NEUTRAL_METRICS = {
    "technical_score": 65.0,
    "sharpness": 58.0,
    "exposure": 70.0,
    "contrast": 60.0,
    "colorfulness": 55.0,
    "entropy": 65.0,
    "composition": 65.0,
    "saturation": 55.0,
}


def _hash_index(value: str, size: int) -> int:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest[:4], "little") % size


def _hash_sign(value: str) -> float:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return 1.0 if digest[4] % 2 == 0 else -1.0


def _sigmoid(value: np.ndarray | float) -> np.ndarray | float:
    clipped = np.clip(value, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def features_from_fields(
    prompt: str,
    negative_prompt: str,
    style: str,
    steps: int,
    guidance: float,
    scheduler: str,
    width: int,
    height: int,
    provider_id: str,
    model: str,
    analysis: dict[str, Any] | None,
    mode: str = "txt2img",
    strength: float = 0.0,
) -> np.ndarray:
    vector = np.zeros(FEATURE_DIM, dtype=np.float64)
    pixels = max(1, width * height)
    ratio = width / max(1, height)
    vector[0] = min(1.0, steps / 40.0)
    vector[1] = min(1.0, guidance / 15.0)
    vector[2] = min(1.0, math.log2(pixels) / 22.0)
    vector[3] = min(1.0, max(1 / 2.5, min(2.5, ratio)) / 2.5)
    vector[4] = min(1.0, len(prompt) / 600.0)
    vector[5] = min(1.0, len(negative_prompt) / 300.0)
    vector[6] = strength
    vector[7] = 1.0 if mode == "img2img" else 0.0
    vector[8] = 0.0 if style in ("", "none") else 1.0

    offset = SCALAR_DIM
    if provider_id:
        vector[offset + _hash_index(provider_id, PROVIDER_DIM)] = 1.0
    offset += PROVIDER_DIM
    if model:
        vector[offset + _hash_index(model.lower(), MODEL_DIM)] = 1.0
    offset += MODEL_DIM
    if style in STYLE_IDS:
        vector[offset + STYLE_IDS.index(style)] = 1.0
    offset += len(STYLE_IDS)
    if scheduler in SCHEDULER_IDS:
        vector[offset + SCHEDULER_IDS.index(scheduler)] = 1.0
    offset += len(SCHEDULER_IDS)

    tokens = list(dict.fromkeys(tokenize(prompt)))[:40]
    scale = 1.0 / math.sqrt(max(1, len(tokens)))
    for token in tokens:
        index = _hash_index("token:" + token, TOKEN_DIM)
        vector[offset + index] += _hash_sign(token) * scale
    offset += TOKEN_DIM

    metrics = analysis or {}
    values = [float(metrics.get(key, NEUTRAL_METRICS[key])) / 100.0 for key in NEUTRAL_METRICS]
    vector[offset : offset + METRIC_DIM] = np.clip(values, 0.0, 1.0)
    return vector


def _reward(rating: int | None, favorite: bool) -> float:
    reward = RATING_REWARD.get(int(rating), 0.0) if rating is not None else 0.0
    if favorite:
        reward += 0.28
        if rating is None:
            reward = 0.68
    return max(-1.0, min(1.0, reward))


def _fit_logistic(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    epochs: int = 420,
    learning_rate: float = 0.38,
    l2: float = 0.025,
) -> tuple[np.ndarray, float]:
    weights_sum = float(weights.sum()) or 1.0
    bias = math.log(max(1e-4, min(1 - 1e-4, float((y * weights).sum() / weights_sum))) / max(1e-4, 1 - float((y * weights).sum() / weights_sum)))
    coef = np.zeros(x.shape[1], dtype=np.float64)
    for _ in range(epochs):
        prediction = _sigmoid(x @ coef + bias)
        error = (prediction - y) * weights
        gradient = (x.T @ error) / weights_sum + l2 * coef
        coef -= learning_rate * gradient
        bias -= learning_rate * float(error.sum() / weights_sum)
    return coef, float(bias)


class LearningService:
    def __init__(self, db: Database, data_dir: Path, settings):
        self.db = db
        self.settings = settings
        self.path = data_dir / "learning_model.json"
        self._lock = threading.RLock()
        self._model: dict[str, Any] | None = self._load()
        self._trained_count = int(self._model.get("samples", -1)) if self._model else -1

    def _load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            model = json.loads(self.path.read_text(encoding="utf-8"))
            if model.get("feature_version") != FEATURE_VERSION or model.get("dim") != FEATURE_DIM:
                return None
            if len(model.get("weights", [])) != FEATURE_DIM:
                return None
            return model
        except Exception:
            return None

    def _save(self, model: dict[str, Any]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def invalidate(self) -> None:
        with self._lock:
            self._trained_count = -1

    def sync_feedback(self, image_id: str) -> None:
        image = self.db.get_image(image_id)
        if not image:
            return
        rating = image.get("rating")
        favorite = bool(image.get("favorite"))
        if rating is None and not favorite:
            self.db.delete_feedback(image_id)
            self.invalidate()
            return
        reward = _reward(rating, favorite)
        features = {
            "tokens": list(dict.fromkeys(tokenize(image["prompt"])))[:40],
            "style": image.get("style"),
            "mode": image.get("mode"),
            "reward": reward,
        }
        self.db.upsert_feedback(image_id, reward, features)
        self.invalidate()

    def preferred_tokens(self, rows: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
        rows = self.db.feedback_rows() if rows is None else rows
        if len(rows) < 4:
            return {"positive": [], "negative": []}
        all_rewards = [float(row["reward"]) for row in rows]
        global_mean = sum(all_rewards) / len(all_rewards)
        counts: dict[str, list[float]] = {}
        for row, reward in zip(rows, all_rewards):
            for token in set(tokenize(row.get("prompt", ""))):
                counts.setdefault(token, []).append(reward)
        total = len(rows)
        scored: list[dict[str, Any]] = []
        for token, rewards in counts.items():
            if len(rewards) < 2 or len(rewards) >= total * 0.7:
                continue
            present_mean = sum(rewards) / len(rewards)
            absent = [reward for row, reward in zip(rows, all_rewards) if token not in set(tokenize(row.get("prompt", "")))]
            if len(absent) < 2:
                continue
            absent_mean = sum(absent) / len(absent)
            lift = present_mean - absent_mean
            confidence = math.sqrt(len(rewards) / total)
            scored.append(
                {
                    "token": token,
                    "lift": round(lift, 3),
                    "count": len(rewards),
                    "score": round(lift * confidence, 3),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        positive = [item for item in scored if item["lift"] > 0.06][:6]
        negative = [item for item in reversed(scored) if item["lift"] < -0.06][:4]
        return {"positive": positive, "negative": negative}

    def learned_prompt_additions(self) -> tuple[list[str], list[str]]:
        if not self.settings.get("adaptive_prompt", True):
            return [], []
        tokens = self.preferred_tokens()
        positive = [item["token"] for item in tokens["positive"][:4] if float(item["count"]) >= 2]
        negative = [item["token"] for item in tokens["negative"][:3] if float(item["count"]) >= 2]
        return positive, negative

    def _training_rows(self) -> list[dict[str, Any]]:
        return self.db.feedback_rows()

    def train(self, force: bool = False) -> dict[str, Any] | None:
        with self._lock:
            rows = self._training_rows()
            if len(rows) < 4:
                self._model = None
                self._trained_count = len(rows)
                return None
            if not force and self._model and self._trained_count == len(rows):
                return self._model

            x_rows = []
            y_rows = []
            weights = []
            now = datetime.now(timezone.utc)
            for row in rows:
                vector = features_from_fields(
                    prompt=row.get("prompt", ""),
                    negative_prompt=row.get("negative_prompt", ""),
                    style=row.get("style", "none"),
                    steps=int(row.get("steps") or 0),
                    guidance=float(row.get("guidance") or 0),
                    scheduler=row.get("scheduler", "auto"),
                    width=int(row.get("width") or 1024),
                    height=int(row.get("height") or 1024),
                    provider_id=row.get("provider_id", ""),
                    model=row.get("model", ""),
                    analysis=row.get("analysis"),
                    mode=row.get("mode", "txt2img"),
                    strength=float(row.get("strength") or 0),
                )
                reward = float(row.get("reward", 0))
                x_rows.append(vector)
                y_rows.append((reward + 1.0) / 2.0)
                age_days = 0.0
                try:
                    created = datetime.fromisoformat(str(row.get("created_at")).replace("Z", "+00:00"))
                    age_days = max(0.0, (now - created).total_seconds() / 86400)
                except Exception:
                    pass
                recency = math.pow(0.82, age_days / 30.0)
                weights.append((0.45 + abs(reward)) * recency)

            x = np.asarray(x_rows, dtype=np.float64)
            y = np.asarray(y_rows, dtype=np.float64)
            sample_weights = np.asarray(weights, dtype=np.float64)
            coef, bias = _fit_logistic(x, y, sample_weights)

            predictions = _sigmoid(x @ coef + bias)
            train_accuracy = float(np.mean((predictions >= 0.5) == (y >= 0.5)))
            cross_val = None
            if len(rows) >= 10:
                fold_scores = []
                for fold in range(4):
                    train_mask = np.arange(len(rows)) % 4 != fold
                    test_mask = ~train_mask
                    if train_mask.sum() < 3 or test_mask.sum() < 1:
                        continue
                    fold_coef, fold_bias = _fit_logistic(x[train_mask], y[train_mask], sample_weights[train_mask], epochs=260)
                    fold_pred = _sigmoid(x[test_mask] @ fold_coef + fold_bias)
                    fold_scores.append(float(np.mean((fold_pred >= 0.5) == (y[test_mask] >= 0.5))))
                if fold_scores:
                    cross_val = float(np.mean(fold_scores))

            positives = int((y >= 0.5).sum())
            negatives = int((y < 0.5).sum())
            model = {
                "feature_version": FEATURE_VERSION,
                "dim": FEATURE_DIM,
                "weights": [round(float(value), 7) for value in coef],
                "bias": round(float(bias), 7),
                "samples": len(rows),
                "train_accuracy": round(train_accuracy, 3),
                "cross_val_accuracy": round(cross_val, 3) if cross_val is not None else None,
                "positives": positives,
                "negatives": negatives,
                "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "model_name": "local-logistic-preference",
            }
            self._model = model
            self._trained_count = len(rows)
            self._save(model)
            return model

    def _ensure_model(self) -> dict[str, Any] | None:
        rows = self._training_rows()
        if len(rows) < 4:
            return None
        if self._model is None or self._trained_count != len(rows):
            return self.train()
        return self._model

    def suggest(
        self,
        prompt: str,
        negative_prompt: str,
        style: str,
        width: int,
        height: int,
        provider_id: str,
        model: str,
        mode: str = "txt2img",
        strength: float = 0.0,
    ) -> dict[str, Any] | None:
        if not self.settings.get("adaptive_enabled", True):
            return None
        trained = self._ensure_model()
        if not trained:
            return None
        base_steps, base_guidance = model_defaults(model)
        if base_steps <= 6:
            step_options = [2, 3, 4, 5, 6, 8]
        elif base_steps <= 12:
            step_options = [4, 6, 8, 10, 12, 16]
        else:
            step_options = [8, 12, 16, 20, 25, 30, 36]
        if base_guidance <= 1.5:
            guidance_options = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
        else:
            guidance_options = [2.0, 3.5, 5.0, 6.0, 7.5, 9.0]
        scheduler_options = ["dpmpp_2m_karras", "euler", "euler_a", "lcm", "ddim"]
        coef = np.asarray(trained["weights"], dtype=np.float64)
        bias = float(trained["bias"])
        candidates = []
        for steps in step_options:
            for guidance in guidance_options:
                for scheduler in scheduler_options:
                    vector = features_from_fields(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        style=style,
                        steps=steps,
                        guidance=guidance,
                        scheduler=scheduler,
                        width=width,
                        height=height,
                        provider_id=provider_id,
                        model=model,
                        analysis=NEUTRAL_METRICS,
                        mode=mode,
                        strength=strength,
                    )
                    score = float(_sigmoid(vector @ coef + bias))
                    prior = 0.12 * abs(steps - base_steps) / max(1, base_steps) + 0.05 * abs(guidance - base_guidance) / max(1.0, base_guidance)
                    candidates.append((score - prior, steps, guidance, scheduler))
        candidates.sort(reverse=True)
        explore = random.random() < 0.15
        if explore:
            pool = candidates[: max(4, len(candidates) // 3)]
            advantage, steps, guidance, scheduler = random.choice(pool)
            reason = "按历史偏好探索一组邻近参数"
        else:
            advantage, steps, guidance, scheduler = candidates[0]
            reason = "根据已评分作品学习到的参数偏好"
        if steps == base_steps and abs(guidance - base_guidance) < 0.01:
            reason = "历史偏好与模型推荐参数一致"
        confidence = min(0.92, 0.35 + len(self.db.feedback_rows()) / 40.0)
        if trained.get("cross_val_accuracy") is not None:
            confidence = min(0.95, 0.45 + 0.5 * float(trained["cross_val_accuracy"]))
        return {
            "steps": int(steps),
            "guidance": float(guidance),
            "scheduler": scheduler,
            "style": style,
            "confidence": round(confidence, 2),
            "reason": reason,
            "explore": explore,
            "samples": int(trained["samples"]),
            "predicted_score": round(float(advantage), 3),
        }

    def insights(self) -> dict[str, Any]:
        stats = self.db.stats()
        rows = self.db.feedback_rows()
        trained = self._ensure_model()
        token_data = self.preferred_tokens(rows)
        recent = list(reversed(self.db.recent_images(80)))
        trend = []
        for image in recent[-40:]:
            analysis = image.get("analysis") or {}
            if not analysis:
                continue
            trend.append(
                {
                    "id": image["id"],
                    "date": image["created_at"],
                    "quality": analysis.get("technical_score", 0),
                    "rating": image.get("rating"),
                }
            )
        qualities = [float(point["quality"]) for point in trend]
        delta = None
        if len(qualities) >= 10:
            recent_avg = sum(qualities[-10:]) / 10
            previous = qualities[-20:-10] if len(qualities) >= 20 else qualities[:-10]
            if previous:
                delta = round(recent_avg - sum(previous) / len(previous), 1)

        style_stats: dict[str, dict[str, Any]] = {}
        for row in rows:
            style = row.get("style") or "none"
            bucket = style_stats.setdefault(style, {"style": style, "count": 0, "total": 0.0})
            bucket["count"] += 1
            bucket["total"] += float(row.get("reward", 0))
        styles = [
            {"style": item["style"], "count": item["count"], "avg_reward": round(item["total"] / item["count"], 2)}
            for item in style_stats.values()
        ]
        styles.sort(key=lambda item: item["avg_reward"], reverse=True)

        provider_stats: dict[str, dict[str, Any]] = {}
        for row in rows:
            provider = row.get("provider_id") or "unknown"
            bucket = provider_stats.setdefault(provider, {"provider_id": provider, "count": 0, "total": 0.0})
            bucket["count"] += 1
            bucket["total"] += float(row.get("reward", 0))
        providers = [
            {"provider_id": item["provider_id"], "count": item["count"], "avg_reward": round(item["total"] / item["count"], 2)}
            for item in provider_stats.values()
        ]

        suggestion = None
        if trained:
            suggestion = self.suggest(
                prompt="",
                negative_prompt="",
                style="none",
                width=1024,
                height=1024,
                provider_id="",
                model="",
                mode="txt2img",
            )
        sample_count = len(rows)
        if sample_count < 6:
            stage = "探索期"
            summary = "继续生成并给作品打分。积累 4 条反馈后开始学习，6 条后参数建议会更稳定。"
        elif sample_count < 20:
            stage = "学习中"
            summary = "偏好模型已开始工作。更多对比评分会让建议更稳定。"
        else:
            stage = "已适应"
            summary = "偏好模型已积累足够样本，会自动微调步数、引导强度和采样器。"
        return {
            "stage": stage,
            "summary": summary,
            "stats": stats,
            "feedback_samples": sample_count,
            "model": {
                "name": "本地逻辑回归偏好模型",
                "samples": sample_count,
                "train_accuracy": trained.get("train_accuracy") if trained else None,
                "cross_val_accuracy": trained.get("cross_val_accuracy") if trained else None,
                "trained_at": trained.get("trained_at") if trained else None,
                "weights": len(trained["weights"]) if trained else 0,
            }
            if trained
            else None,
            "quality": {
                "average": round(sum(qualities) / len(qualities), 1) if qualities else None,
                "recent_delta": delta,
                "trend": trend,
            },
            "tokens": token_data,
            "styles": styles,
            "providers": providers,
            "suggestion": suggestion,
            "adaptive_enabled": bool(self.settings.get("adaptive_enabled", True)),
            "adaptive_prompt": bool(self.settings.get("adaptive_prompt", True)),
        }

    def reset(self) -> None:
        with self._lock:
            self._model = None
            self._trained_count = -1
            if self.path.exists():
                self.path.unlink()
