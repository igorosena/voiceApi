#!/usr/bin/env python3
"""Bulk-register voices from a folder.

Layout (one sub-folder per voice, folder name = voice id):

    voices_src/
      narrator/
        ref.wav          (or .mp3 / .m4a / .ogg — 3-15 s of clean speech)
        ref.txt          exact transcript of the clip
        meta.json        optional: {"name": "Narrator", "language": "en"}
      support-agent/
        ...

Usage:
    python scripts/register_voices.py voices_src --url http://localhost:8000 --key "$VOICE_API_KEY"
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

AUDIO_EXT = (".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".webm", ".aac")


def multipart(fields: dict, file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----voiceapi" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
            f"filename=\"{file_path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
    out += file_path.read_bytes() + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Register every voice folder under SRC with a Voice API server.")
    ap.add_argument("src", type=Path, help="folder with one sub-folder per voice")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--key", default=os.environ.get("VOICE_API_KEY", ""), help="API key (default: $VOICE_API_KEY)")
    ap.add_argument("--language", default="auto")
    args = ap.parse_args()

    failures = 0
    for folder in sorted(p for p in args.src.iterdir() if p.is_dir()):
        clips = [p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT]
        txt = folder / "ref.txt"
        if not clips or not txt.exists():
            print(f"skip {folder.name}: need an audio clip and ref.txt")
            continue
        meta = {}
        if (folder / "meta.json").exists():
            meta = json.loads((folder / "meta.json").read_text("utf-8"))
        fields = {
            "id": folder.name,
            "name": meta.get("name", folder.name),
            "language": meta.get("language", args.language),
            "ref_text": txt.read_text("utf-8").strip(),
        }
        body, ctype = multipart(fields, "ref_audio", clips[0])
        req = urllib.request.Request(f"{args.url.rstrip('/')}/voices", data=body, method="POST")
        req.add_header("Content-Type", ctype)
        # RunPod's Cloudflare proxy rejects urllib's default User-Agent (403 / error 1010).
        req.add_header("User-Agent", "voiceapi-client/1.0")
        if args.key:
            req.add_header("Authorization", f"Bearer {args.key}")
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                print(f"ok   {folder.name}: {resp.read().decode()}")
        except urllib.error.HTTPError as e:
            failures += 1
            print(f"FAIL {folder.name}: {e.code} {e.read().decode()}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
