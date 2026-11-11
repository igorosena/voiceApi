# Voice API

[![CI](https://github.com/igorosena/voiceApi/actions/workflows/ci.yml/badge.svg)](https://github.com/igorosena/voiceApi/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

A self-hosted text-to-speech API with voice cloning. Run it on your own VPS,
GPU cloud pod or workstation, register a voice from a few seconds of audio,
then turn any text into speech in that voice with a single HTTP call.

- **Zero-shot voice cloning**: a 3 to 15 second clip and its transcript are
  enough to create a voice. No training or fine-tuning.
- **600+ languages** through the [OmniVoice](https://huggingface.co/k2-fsa/OmniVoice)
  model (Apache-2.0), 24 kHz mono output.
- **OpenAI-compatible** `/v1/audio/speech` endpoint, so existing OpenAI TTS
  clients work by changing the base URL.
- **Private by design**: audio and text never leave your machine. No
  third-party API, no per-character billing.
- **Production details handled**: API key auth, reference-clip denoising and
  dereverberation, cached voice embeddings, GPU/CPU/Apple Silicon support,
  a Docker image built by CI, and a health check.

## How it works

```
                 register once                              every request
  clip + transcript ─► POST /voices                 {voice, text} ─► POST /speak
                          │                                              │
                 ffmpeg: 24 kHz mono                         load cached prompt
                 DeepFilterNet: denoise + dereverb           OmniVoice generation
                 OmniVoice: encode voice prompt              ffmpeg: mp3/opus/wav/flac
                          │                                              │
                 data/prompts/<id>.pt  ─────────────────────►    audio bytes
```

The expensive part of cloning (encoding the reference voice) happens once at
registration and is saved to disk. Each `/speak` call only runs generation,
which takes about a second for a short sentence on a modern GPU.

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/igorosena/voiceApi.git && cd voiceApi
cp .env.example .env              # set VOICE_API_KEY
docker compose up -d --build      # NVIDIA GPU (needs nvidia-container-toolkit)
docker logs -f voice-api          # the first start downloads the model (~2.4 GB)
```

No GPU? Remove the `deploy:` block from `docker-compose.yml` and build the
much smaller CPU image:

```bash
docker compose build \
  --build-arg BASE_IMAGE=python:3.12-slim \
  --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu
docker compose up -d
```

A prebuilt CUDA image is published on every push to `main`:
`ghcr.io/igorosena/voiceapi:latest`.

### Local development

Requires Python 3.12 and `ffmpeg` on the `PATH`.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
VOICE_API_KEY= .venv/bin/uvicorn app.main:app --port 8000
```

Interactive API docs are served at `http://localhost:8000/docs`.

## Usage

### 1. Register a voice

You need a clean clip of **3 to 15 seconds** (wav, mp3, m4a, ogg, flac, webm)
and the **exact transcript** of what is said in it. The transcript matters
more for clone quality than anything else.

```bash
curl -X POST http://localhost:8000/voices \
  -H "Authorization: Bearer $VOICE_API_KEY" \
  -F id=narrator \
  -F name="Narrator" \
  -F language=en \
  -F ref_audio=@narrator.wav \
  -F ref_text="Welcome back. Today we are going to look at something new."
```

Registering again with the same `id` replaces the voice.

To register many voices at once, put one folder per voice under a directory
and run the bundled script:

```
voices/
  narrator/
    ref.wav
    ref.txt          # exact transcript of ref.wav
    meta.json        # optional: {"name": "Narrator", "language": "en"}
  support-agent/
    ...
```

```bash
python scripts/register_voices.py voices --url http://localhost:8000
```

### 2. Generate speech

```bash
curl -X POST http://localhost:8000/speak \
  -H "Authorization: Bearer $VOICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"voice": "narrator", "text": "Your order has shipped and will arrive on Friday."}' \
  --output speech.mp3
```

From Node.js:

```js
const res = await fetch("https://voice.example.com/speak", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.VOICE_API_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({ voice: "narrator", text: "Hello from Node." }),
});
const audio = Buffer.from(await res.arrayBuffer());
```

With the official OpenAI SDK (Python):

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="your-voice-api-key")
with client.audio.speech.with_streaming_response.create(
    model="omnivoice", voice="narrator", input="Hello from the OpenAI SDK."
) as response:
    response.stream_to_file("speech.mp3")
```

## API reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Status, device, model loaded, voice count. No auth. |
| `POST` | `/voices` | Register a voice. Multipart: `id`, `ref_audio`, `ref_text`, `name?`, `language?` |
| `GET` | `/voices` | List registered voices |
| `DELETE` | `/voices/{id}` | Delete a voice and its files |
| `POST` | `/speak` | Generate speech, returns audio bytes |
| `POST` | `/v1/audio/speech` | OpenAI-compatible alias: `input`, `voice`, `response_format`, `speed` |
| `GET` | `/v1/audio/voices` | Voice list for OpenAI-style clients |

`POST /speak` body:

| Field | Default | Notes |
|---|---|---|
| `voice` | required | A registered voice id |
| `text` | required | Up to 4096 characters; long text is split internally |
| `language` | the voice's language | `en`, `pt`, `es`, `pt-BR`, ... or `auto` |
| `format` | `mp3` | `mp3`, `wav`, `opus`, `flac`, `pcm` (s16le, 24 kHz) |
| `speed` | `1.0` | 0.5 to 2.0 |
| `num_step` | `16` | Diffusion steps: 16 is fast, 32 is best quality |
| `guidance_scale` | `2.0` | 0.5 to 5.0 |
| `seed` | random | Fix it for reproducible output |

Responses include `X-Audio-Duration`, `X-Gen-Time` (seconds) and
`X-Sample-Rate` headers. Errors are JSON: `{"detail": "..."}`.

**Authentication**: when `VOICE_API_KEY` is set, every route except `/health`
requires `Authorization: Bearer <key>` or `X-API-Key: <key>`.

## Configuration

All settings are environment variables (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `VOICE_API_KEY` | empty | Required key for all routes except `/health` (empty disables auth) |
| `VOICE_DATA_DIR` | `./data` (`/data` in Docker) | Voices, encoded prompts and the model cache |
| `VOICE_DEVICE` | `auto` | `cuda`, `mps` or `cpu` |
| `VOICE_PRELOAD` | `1` | Load the model at startup instead of on the first request |
| `VOICE_DEFAULT_LANGUAGE` | `auto` | Language assigned to new voices when none is given |
| `VOICE_DEFAULT_FORMAT` | `mp3` | Default output format |
| `VOICE_NUM_STEP` | `16` | Default diffusion steps |
| `VOICE_GUIDANCE_SCALE` | `2.0` | Default guidance scale |
| `VOICE_MAX_TEXT_CHARS` | `4096` | Maximum text length per request |
| `VOICE_MAX_REF_SECONDS` | `20` | Maximum reference clip length |
| `VOICE_CLEAN_REFS` | `1` | Denoise and dereverb reference clips with DeepFilterNet |
| `VOICE_DFN_PYTHON` | empty | Python interpreter with `deepfilternet`, if it lives in another venv |
| `VOICE_IDLE_UNLOAD_SECONDS` | `0` | Unload the model after N idle seconds to free VRAM (0 = never) |
| `HF_TOKEN` | empty | Only if your network requires a Hugging Face token |

## Hardware and performance

| Setup | Speed |
|---|---|
| NVIDIA GPU, 6 GB+ VRAM | About 1 s per short sentence after warm-up |
| CPU | Works, 10 to 50 times slower; best for batch jobs or pre-generated audio |
| Apple Silicon (dev) | Use `VOICE_DEVICE=cpu`; about 13 s for 5 s of speech on an M4 |

Generation runs one request at a time (the model is not thread-safe);
concurrent requests queue. For live traffic on CPU, generate ahead of time and
cache the audio.

On macOS, DeepFilterNet needs torch 2.8, which conflicts with newer torch
versions. Install it in a separate venv and point `VOICE_DFN_PYTHON` at it:

```bash
uv venv --python 3.11 .venv-tools
uv pip install --python .venv-tools/bin/python torch==2.8.0 torchaudio==2.8.0 deepfilternet soundfile
VOICE_DFN_PYTHON=$PWD/.venv-tools/bin/python .venv/bin/uvicorn app.main:app --port 8000
```

The Docker image already ships torch 2.8 and DeepFilterNet.

## Deployment

- **VPS**: the container binds to `127.0.0.1:8000`. Put Caddy or Nginx with
  TLS in front of it and never expose the port directly. With Caddy:

  ```
  voice.example.com {
      reverse_proxy 127.0.0.1:8000
  }
  ```

- **GPU cloud**: see [deploy/runpod.md](deploy/runpod.md) for a step-by-step
  RunPod setup using the prebuilt image.

## Project layout

```
app/
  main.py      FastAPI routes, auth, request validation
  engine.py    model lifecycle, voice encoding, synthesis, audio encoding
  voices.py    JSON-backed voice registry
  config.py    environment configuration
scripts/
  register_voices.py   bulk voice registration
  clean_ref.py         DeepFilterNet cleanup (runs as a subprocess)
omnivoice/     vendored OmniVoice model code (Apache-2.0)
tests/         API tests with a stubbed model (no GPU needed)
```

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests replace the model with a fake, so they run in under a second
without torch or a GPU. CI runs them on every push before building the image.

## Responsible use

Only clone voices you have the right to use: your own, or those of people who
have given explicit consent. Do not use this project to impersonate anyone or
to mislead listeners about who is speaking.

## License

Apache-2.0. The model code in `omnivoice/` comes from
[k2-fsa/OmniVoice](https://github.com/k2-fsa/OmniVoice), also Apache-2.0.
See [LICENSE](LICENSE) and [NOTICE](NOTICE).
