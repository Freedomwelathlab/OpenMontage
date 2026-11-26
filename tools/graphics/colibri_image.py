"""FWL local images: Qwen-Image-2.1 on the Colibri server (127.0.0.1:18000).

Free and offline but slow (minutes per image) and lower quality than cloud FLUX.
Start it with `ai-mode image` (this stops ComfyUI/LTX, one GPU engine at a time).
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

import requests

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

_BASE = os.environ.get("COLIBRI_URL", f"http://127.0.0.1:{os.environ.get('COLIBRI_PORT', '18000')}")
_HEADERS = {"Authorization": "Bearer local"}


class ColibriImage(BaseTool):
    name = "colibri_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "colibri"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = []
    install_instructions = (
        "FWL local stack: run `ai-mode image` to load Qwen-Image-2.1 on the Colibri server "
        f"({_BASE}). Only one GPU engine runs at a time, so this stops ComfyUI/LTX."
    )
    agent_skills = []
    capabilities = ["text_to_image"]
    supports = {"seed": True, "offline": True}
    best_for = [
        "free offline stills: keyframes for LTX image-to-video, backgrounds, thumbnails drafts",
    ]
    not_good_for = [
        "fast iteration (minutes per image)",
        "photoreal hero images or readable text",
    ]
    fallback = "image_selector"
    fallback_tools = ["pexels_image", "pixabay_image"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "width": {"type": "integer", "default": 768},
            "height": {"type": "integer", "default": 512},
            "steps": {"type": "integer", "default": 20, "description": "20+ avoids ghosting"},
            "seed": {"type": "integer"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=4, ram_mb=16000, vram_mb=12000, disk_mb=50, network_required=False)
    retry_policy = RetryPolicy(max_retries=0)
    idempotency_key_fields = ["prompt", "seed", "width", "height", "steps"]
    side_effects = ["writes PNG to output_path"]
    user_visible_verification = ["Look at the image for ghosting or warped details"]

    def _served(self) -> list[str]:
        try:
            r = requests.get(f"{_BASE}/v1/models", headers=_HEADERS, timeout=3)
            return [m.get("id", "") for m in r.json().get("data", [])]
        except Exception:
            return []

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if any("image" in m for m in self._served()) else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 15.0 * int(inputs.get("steps", 20))

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        models = [m for m in self._served() if "image" in m]
        if not models:
            return ToolResult(success=False, error="Colibri image model is not running. " + self.install_instructions)
        body: dict[str, Any] = {
            "model": models[0],
            "prompt": inputs["prompt"],
            "size": f"{int(inputs.get('width', 768))}x{int(inputs.get('height', 512))}",
            "steps": int(inputs.get("steps", 20)),
            "n": 1,
            "response_format": "b64_json",
        }
        if inputs.get("seed") is not None:
            body["seed"] = int(inputs["seed"])
        start = time.time()
        try:
            r = requests.post(f"{_BASE}/v1/images/generations", json=body, headers=_HEADERS, timeout=3600)
            r.raise_for_status()
            payload = r.json()
            img = base64.b64decode(payload["data"][0]["b64_json"])
        except Exception as exc:
            return ToolResult(success=False, error=f"Colibri image generation failed: {exc}")
        dest = Path(inputs.get("output_path") or f"colibri_{int(time.time())}.png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img)
        seed = payload.get("colibri", {}).get("seed", inputs.get("seed"))
        return ToolResult(
            success=True,
            data={"provider": self.provider, "model": models[0], "prompt": inputs["prompt"], "output": str(dest)},
            artifacts=[str(dest)],
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
            seed=seed,
            model=models[0],
        )
