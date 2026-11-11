"""Runtime configuration, read from environment variables.

Every setting uses the ``VOICE_`` prefix. The legacy ``COUNCIL_`` prefix from
earlier releases is still accepted, so existing deployments keep working.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    for key in (f"VOICE_{name}", f"COUNCIL_{name}"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return default


DATA_DIR = Path(_env("DATA_DIR", "./data")).resolve()
# Keep the Hugging Face model cache next to the voices so a single volume
# holds everything (Docker Compose mounts it at /data, RunPod at /workspace).
os.environ.setdefault("HF_HOME", str(DATA_DIR / "huggingface"))
REFS_DIR = DATA_DIR / "refs"          # normalised reference clips
PROMPTS_DIR = DATA_DIR / "prompts"    # pre-encoded VoiceClonePrompt .pt files
REGISTRY_FILE = DATA_DIR / "voices.json"

MODEL_ID = _env("MODEL", "k2-fsa/OmniVoice")
DEVICE = _env("DEVICE", "auto")                # auto | cuda | mps | cpu
PRELOAD = _env("PRELOAD", "1") == "1"          # load the model at startup
API_KEY = _env("API_KEY", "")                  # empty = no auth

DEFAULT_LANGUAGE = _env("DEFAULT_LANGUAGE", "auto")
DEFAULT_FORMAT = _env("DEFAULT_FORMAT", "mp3")
DEFAULT_NUM_STEP = int(_env("NUM_STEP", "16"))
DEFAULT_GUIDANCE = float(_env("GUIDANCE_SCALE", "2.0"))
MAX_TEXT_CHARS = int(_env("MAX_TEXT_CHARS", "4096"))
MAX_REF_SECONDS = float(_env("MAX_REF_SECONDS", "20"))
NORMALIZE_DBFS = float(_env("NORMALIZE_DBFS", "-2.0"))

# Denoise and dereverb reference clips with DeepFilterNet before encoding.
# Zero-shot cloning copies the room acoustics of the reference, so a podcast
# or stage recording clones with its reverb unless it is cleaned first.
CLEAN_REFS = _env("CLEAN_REFS", "1") == "1"
# Interpreter that has `deepfilternet` installed (defaults to this one).
DFN_PYTHON = _env("DFN_PYTHON", "")

# Unload the model after N idle seconds to free VRAM (0 = keep it resident;
# a reload costs ~10 s).
IDLE_UNLOAD_SECONDS = int(_env("IDLE_UNLOAD_SECONDS", "0"))
