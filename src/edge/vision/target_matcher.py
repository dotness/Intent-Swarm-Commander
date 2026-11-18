"""Edge LLM target-vs-obstacle discriminator using Google GenAI."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

TARGET_MATCH_CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True)
class TargetClassificationResult:
    """Result of edge LLM evaluation comparing a detected object to an ordered target."""

    detected_class: str
    is_ordered_target: bool
    confidence: float
    rationale: str
    evaluated_by: str = "edge_llm"


class EdgeTargetMatcher:
    """Classifies detected objects as ordered mission targets or non-target obstacles.

    Uses ``google-genai`` for semantic matching with a short-lived in-memory TTL
    cache keyed by ``(mission_id, target_class, attributes, detected_class)`` so
    repeated 10 Hz video frames resolve within sub-millisecond latency.
    """

    def __init__(
        self,
        model: str | None = None,
        client: Any = None,
        cache_ttl_s: float = 30.0,
        confidence_threshold: float = TARGET_MATCH_CONFIDENCE_THRESHOLD,
        max_cache_size: int = 512,
    ) -> None:
        self.model = model or os.getenv("EDGE_LLM_MODEL", "gemini-2.5-flash-lite")
        self.cache_ttl_s = max(0.0, float(cache_ttl_s))
        self.confidence_threshold = float(confidence_threshold)
        self.max_cache_size = max(1, int(max_cache_size))
        self._client = client
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple[str, str, str, str], tuple[float, TargetClassificationResult]] = OrderedDict()

    def _get_client(self) -> Any:
        if self._client is None:
            api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required for EdgeTargetMatcher")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def classify(
        self,
        mission_id: str | None,
        target_class: str,
        detected_class: str,
        target_attributes: dict[str, str] | None = None,
    ) -> TargetClassificationResult:
        """Determine whether ``detected_class`` matches the ordered mission target."""
        attrs_key = json.dumps(target_attributes or {}, sort_keys=True)
        cache_key = (
            str(mission_id or ""),
            target_class.strip().lower(),
            attrs_key,
            detected_class.strip().lower(),
        )
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                expires_at, result = cached
                if now < expires_at:
                    self._cache.move_to_end(cache_key)
                    return result
                self._cache.pop(cache_key, None)

        prompt_payload = {
            "ordered_target_class": target_class,
            "ordered_target_attributes": target_attributes or {},
            "detected_class": detected_class,
        }
        prompt = (
            "You are an edge drone autonomy classifier. Determine if the detected object "
            "matches the ordered mission target (including semantic equivalents like "
            "'truck' for 'military vehicle'), or if it is a non-target physical obstacle "
            "(such as a lamp post, pole, traffic light, tree, or wall).\n"
            f"Input: {json.dumps(prompt_payload)}\n"
            "Respond ONLY with JSON matching: "
            '{"is_ordered_target": bool, "confidence": float_0_to_1, "rationale": str}'
        )

        client = self._get_client()
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        raw_text = (getattr(response, "text", None) or "").strip()
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.warning("EdgeTargetMatcher invalid JSON response (%s); failing safe to obstacle", exc)
            return TargetClassificationResult(
                detected_class=detected_class,
                is_ordered_target=False,
                confidence=0.0,
                rationale="Invalid LLM JSON output; fail-safe obstacle classification",
                evaluated_by="edge_llm",
            )
        raw_matched = bool(parsed.get("is_ordered_target", False))
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
        rationale = str(parsed.get("rationale", ""))

        # Fail-safe: ambiguous or low-confidence target matches default to obstacle
        is_target = raw_matched and (confidence >= self.confidence_threshold)

        result = TargetClassificationResult(
            detected_class=detected_class,
            is_ordered_target=is_target,
            confidence=confidence,
            rationale=rationale,
            evaluated_by="edge_llm",
        )
        if self.cache_ttl_s > 0.0:
            with self._lock:
                self._cache[cache_key] = (now + self.cache_ttl_s, result)
                self._cache.move_to_end(cache_key)
                while len(self._cache) > self.max_cache_size:
                    self._cache.popitem(last=False)
        return result
