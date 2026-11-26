# OpenMontage

**MANDATORY: Read [`AGENT_GUIDE.md`](AGENT_GUIDE.md) before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

There are no instructions in this file. All instructions are in AGENT_GUIDE.md.

## FWL local stack (added 2026-11-26, read after AGENT_GUIDE.md)

The owner uses free tools only. Generation runs on this PC's RTX 5070 Ti, one GPU engine at a time:
- Video: `ltx23_comfyui` (LTX-2.3, text- and image-to-video, native audio, ~45 s per 5 s clip). Needs `ai-mode media` (ComfyUI on 127.0.0.1:8188). Shorts size 704x1280; `upscale: true` for 2K.
- Images: `colibri_image` (Qwen-Image-2.1, ~25 s at 768x512, 20 steps). Needs `ai-mode image`, which stops ComfyUI.
- Order of work: make all stills first (`ai-mode image`), then switch to `ai-mode media` for clips. Run `ai-mode stop` when done.
- Voice: Piper (local). Music: pixabay_music. Text on screen: Remotion/HyperFrames, never baked into LTX clips.
- No paid API keys are set in `.env`. Ask the owner before adding one or choosing any paid provider.
- LTX can invent people or objects in moving backgrounds: check every clip's frames before using it.
- `ai-mode` lives at `D:\FWL\01_AI_WORKSPACE\OmniRoute\ai-mode.ps1`.
