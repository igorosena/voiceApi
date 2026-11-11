# Deploying on RunPod (GPU)

This guide runs the prebuilt image `ghcr.io/igorosena/voiceapi:latest` on a
RunPod GPU pod. Any GPU with 8 GB+ of VRAM works (RTX 3090, A5000, RTX 4000...).

## 1. Create the pod

RunPod → **Pods** → **Deploy**, pick a GPU, then open **Edit Template**:

| Field | Value |
|---|---|
| Container Image | `ghcr.io/igorosena/voiceapi:latest` |
| Container Disk | 20 GB |
| Volume Disk | 20 GB (persistent: model and voices) |
| Volume Mount Path | `/workspace` |
| Expose HTTP Ports | `8000` |

Environment variables:

| Name | Value |
|---|---|
| `VOICE_API_KEY` | a long random string (`openssl rand -base64 32`) |
| `VOICE_DATA_DIR` | `/workspace/data` |
| `VOICE_DEVICE` | `cuda` |

Leave the start command empty; the image starts uvicorn on port 8000.

## 2. Wait for the model download

On the first start the pod downloads about 2.4 GB from Hugging Face into the
volume. Watch the pod logs until `model ready` appears. Later starts reuse the
cached model and boot in about 15 seconds.

The public URL is under **Connect → HTTP Service [Port 8000]**:
`https://<POD_ID>-8000.proxy.runpod.net`.

```bash
export VOICE_URL=https://<POD_ID>-8000.proxy.runpod.net
export VOICE_API_KEY=...
curl $VOICE_URL/health
```

## 3. Register voices

From your machine, with one folder per voice (see the main README):

```bash
python scripts/register_voices.py voices --url $VOICE_URL --key "$VOICE_API_KEY"
```

Each voice takes a few seconds on a GPU (cleanup plus encoding). Voices live on
the volume, so they survive pod restarts.

## 4. Test

```bash
curl -X POST $VOICE_URL/speak \
  -H "Authorization: Bearer $VOICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"voice": "narrator", "text": "Testing the deployment."}' \
  -D - --output test.mp3 | grep -i x-gen-time
```

`X-Gen-Time` is the generation time in seconds. On a GPU it should stay under
2 seconds from the second call onward.

## Cost

A running pod is billed per second. A stopped pod only pays for the volume
(cents per day), so stop it when idle and start it when needed; the model and
voices stay on the volume.

## Updating

Pushing to `main` runs the tests and publishes a new image. Restart the pod to
pull the new `:latest`.
