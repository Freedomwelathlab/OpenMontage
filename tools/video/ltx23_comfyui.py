"""FWL local video: LTX-2.3 distilled (video + native audio) on the local ComfyUI.

Wraps D:/FWL/05_MEDIA_STUDIO/Workflows/ltx_video.mjs so the workflow stays defined
in one place. Free, offline, RTX 5070 Ti. Start ComfyUI first with `ai-mode media`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from tools._comfyui.client import ComfyUIClient
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

_SCRIPT = Path(os.environ.get("FWL_LTX_SCRIPT", r"D:\FWL\05_MEDIA_STUDIO\Workflows\ltx_video.mjs"))
_OUT_LINE = re.compile(r"^(video/[^\s]+\.(?:mp4|webm|mov))\s*$", re.M)


def _snap64(v: int) -> int:
    return max(64, int(round(v / 64)) * 64)


class LTX23ComfyUIVideo(BaseTool):
    name = "ltx23_comfyui"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "comfyui-ltx23"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = []
    install_instructions = (
        "FWL local stack: run `ai-mode media` (starts ComfyUI on 127.0.0.1:8188 and frees the GPU). "
        f"Needs node and {_SCRIPT}. Models live in D:/FWL/04_AI_MODELS/ComfyUI/models."
    )
    agent_skills = ["ltx2", "ai-video-gen"]
    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "seed": True,
        "reference_image": True,
        "offline": True,
        "native_audio": True,
        "local_gpu": True,
        "upscale_2x": True,
    }
    best_for = [
        "FWL default video generator: free, offline, no API key",
        "5-10 s b-roll and scene clips with matching ambient audio",
        "image-to-video from a still (keyframe, product shot, Colibri image)",
        "9:16 Shorts (704x1280) and 16:9 (1280x704); --up gives 2K",
    ]
    not_good_for = [
        "readable on-screen text (render text in Remotion/HyperFrames instead)",
        "lip-synced talking presenters",
        "running while another GPU model (Colibri/Ollama) holds the VRAM",
    ]
    fallback = "comfyui_video"
    fallback_tools = ["image_selector"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string", "description": "Subject, action, camera, light, sound. Under ~80 words."},
            "operation": {"type": "string", "enum": ["text_to_video", "image_to_video"], "default": "text_to_video"},
            "reference_image_path": {"type": "string", "description": "Local image for image_to_video (cropped to fit)."},
            "width": {"type": "integer", "default": 1280, "description": "Snapped to a multiple of 64. Shorts: 704."},
            "height": {"type": "integer", "default": 704, "description": "Snapped to a multiple of 64. Shorts: 1280."},
            "duration_seconds": {"type": "number", "default": 5},
            "fps": {"type": "integer", "default": 25},
            "seed": {"type": "integer"},
            "upscale": {"type": "boolean", "default": False, "description": "RelayVSR 2x upscale (slower)."},
            "enhance_prompt": {"type": "boolean", "default": False, "description": "Rewrite the prompt with local Ollama first."},
            "strength": {"type": "number", "default": 0.7, "description": "image_to_video adherence to the still."},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=4, ram_mb=24000, vram_mb=15000, disk_mb=2000, network_required=False)
    retry_policy = RetryPolicy(max_retries=1)
    idempotency_key_fields = ["prompt", "operation", "seed", "width", "height", "duration_seconds"]
    side_effects = ["writes video file to output_path", "occupies the GPU while running"]
    user_visible_verification = ["Watch the clip: LTX can invent extra objects or people in moving backgrounds"]

    def __init__(self) -> None:
        super().__init__()
        self._client = ComfyUIClient(os.environ.get("COMFYUI_SERVER_URL", "http://127.0.0.1:8188"))

    def get_status(self) -> ToolStatus:
        if not _SCRIPT.exists() or shutil.which("node") is None:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE if self._client.is_available() else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        secs = float(inputs.get("duration_seconds", 5))
        return 25.0 + 12.0 * secs * (2.5 if inputs.get("upscale") else 1.0)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="LTX-2.3 local video is unavailable. " + self.install_instructions)
        op = inputs.get("operation", "text_to_video")
        w, h = _snap64(int(inputs.get("width", 1280))), _snap64(int(inputs.get("height", 704)))
        secs, fps = float(inputs.get("duration_seconds", 5)), int(inputs.get("fps", 25))
        seed = int(inputs.get("seed") or ComfyUIClient.random_seed() % 2_000_000_000)
        cmd = ["node", str(_SCRIPT), "--prompt", str(inputs["prompt"]), "--w", str(w), "--h", str(h),
               "--sec", str(secs), "--fps", str(fps), "--seed", str(seed), "--url", self._client.server_url]
        if op == "image_to_video":
            ref = inputs.get("reference_image_path")
            if not ref or not Path(ref).exists():
                return ToolResult(success=False, error="image_to_video needs an existing reference_image_path")
            # ltx_video.mjs splits the path on "/" to name the upload, so pass forward slashes
            cmd += ["--image", Path(ref).resolve().as_posix(),"--strength", str(inputs.get("strength", 0.7))]
        if inputs.get("upscale"):
            cmd.append("--up")
        if inputs.get("enhance_prompt"):
            cmd.append("--enhance")

        start = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        log = (proc.stdout or "") + (proc.stderr or "")
        outs = _OUT_LINE.findall(log)
        if proc.returncode != 0 or "success" not in log or not outs:
            return ToolResult(success=False, error=f"LTX-2.3 run failed (exit {proc.returncode}): {log[-1500:]}")

        chosen = next((o for o in outs if "_2x" in o), outs[-1])
        subfolder, filename = chosen.rsplit("/", 1)
        dest = Path(inputs.get("output_path") or f"ltx23_{op}_{seed}.mp4")
        self._client.download(filename, subfolder, dest)
        out_w, out_h = (w * 2, h * 2) if inputs.get("upscale") else (w, h)
        frames = int(secs * fps // 8 * 8 + 1)
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": "ltx-2.3-22b-distilled-fp8",
                "prompt": inputs["prompt"],
                "operation": op,
                "width": out_w,
                "height": out_h,
                "num_frames": frames,
                "fps": fps,
                "duration_seconds": round(frames / fps, 2),
                "native_audio": True,
                "output": str(dest),
                "format": "mp4",
            },
            artifacts=[str(dest)],
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
            seed=seed,
            model="ltx-2.3-22b-distilled-fp8",
        )
