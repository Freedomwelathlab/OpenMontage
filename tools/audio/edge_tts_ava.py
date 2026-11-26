"""FWL house voice: Microsoft Edge neural TTS (free, no API key), Ava by default.

FWL rule: every channel video uses en-US-AvaMultilingualNeural; only the rate varies.
Writes the MP3 plus word timings (JSON) and an SRT beside it for captions.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

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

FWL_VOICE = "en-US-AvaMultilingualNeural"


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def words_to_srt(words: list[dict], max_words: int = 4) -> str:
    """Group words into short caption chunks (Shorts style)."""
    lines, chunk = [], []
    for w in words:
        chunk.append(w)
        if len(chunk) >= max_words or w["word"].endswith((".", "?", "!", ",")):
            lines.append(chunk)
            chunk = []
    if chunk:
        lines.append(chunk)
    out = []
    for i, c in enumerate(lines, 1):
        out.append(f"{i}\n{_ts(c[0]['start'])} --> {_ts(c[-1]['end'])}\n{' '.join(x['word'] for x in c)}\n")
    return "\n".join(out)


class EdgeTTSAva(BaseTool):
    name = "edge_tts_ava"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "edge-tts"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = "uv pip install edge-tts (free Microsoft Edge voices, no key; needs internet)."
    agent_skills = ["text-to-speech"]
    capabilities = ["text_to_speech", "word_timestamps"]
    supports = {"word_timestamps": True, "srt_output": True, "voice_cloning": False, "offline": False}
    best_for = ["FWL house narration (Ava) for every channel video", "free narration with word-level caption timing"]
    not_good_for = ["fully offline runs", "voice cloning"]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "voice": {"type": "string", "default": FWL_VOICE, "description": "Keep Ava for FWL channels."},
            "rate": {"type": "string", "default": "+0%", "description": "e.g. -8% or +10%"},
            "output_path": {"type": "string", "description": ".mp3 path; .words.json and .srt are written beside it"},
            "caption_words": {"type": "integer", "default": 4},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=10, network_required=True)
    retry_policy = RetryPolicy(max_retries=2)
    idempotency_key_fields = ["text", "voice", "rate"]
    side_effects = ["writes mp3, words.json and srt"]
    user_visible_verification = ["Listen for mispronounced numbers or names"]

    def get_status(self) -> ToolStatus:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    async def _run(self, text: str, voice: str, rate: str, mp3: Path) -> list[dict]:
        import edge_tts

        words: list[dict] = []
        com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
        with open(mp3, "wb") as f:
            async for chunk in com.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append({"word": chunk["text"], "start": round(start, 3),
                                  "end": round(start + chunk["duration"] / 1e7, 3)})
        return words

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error=self.install_instructions)
        voice = inputs.get("voice", FWL_VOICE)
        mp3 = Path(inputs.get("output_path", "narration.mp3"))
        mp3.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        try:
            words = asyncio.run(self._run(inputs["text"], voice, inputs.get("rate", "+0%"), mp3))
        except Exception as exc:
            return ToolResult(success=False, error=f"edge-tts failed: {exc}")
        wj, srt = mp3.with_suffix(".words.json"), mp3.with_suffix(".srt")
        wj.write_text(json.dumps(words, indent=1), encoding="utf-8")
        srt.write_text(words_to_srt(words, int(inputs.get("caption_words", 4))), encoding="utf-8")
        dur = words[-1]["end"] if words else 0.0
        return ToolResult(
            success=True,
            data={"provider": self.provider, "voice": voice, "output": str(mp3), "words": str(wj),
                  "srt": str(srt), "speech_seconds": dur, "word_count": len(words)},
            artifacts=[str(mp3), str(wj), str(srt)],
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
            model=voice,
        )
