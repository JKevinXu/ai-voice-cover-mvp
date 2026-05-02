# AI Voice Cover MVP

A consent-based MVP for the workflow:

1. Upload a sample song or clean vocal for the target voice.
2. Upload a guide vocal singing the new song.
3. Use open-source Demucs + RVC-style voice conversion adapters.
4. Download a converted vocal and final mix artifact.

This MVP is intentionally built with guardrails: users must confirm they own the voice or have explicit permission to clone it.

## What this is

This is a lightweight FastAPI orchestration app around open-source projects:

- Demucs for vocal/instrumental separation: https://github.com/facebookresearch/demucs
- RVC WebUI for retrieval-based voice conversion: https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI

The app ships with:

- A simple web upload form.
- A REST API.
- Mock mode for testing the product flow without heavy ML dependencies.
- Real/dry-run mode that builds the Demucs/RVC commands without executing them.
- Configurable command templates so you can adapt it to the exact RVC fork/CLI you install.

## What this is not

This is not a production voice-cloning service yet. It does not bundle model weights, RVC, Demucs, GPUs, or a production job queue. The goal is to provide a clear MVP shell that can be connected to the open-source ML stack.

YouTube input is supported for convenience, but only for voices you own or have explicit permission to clone. Do not use it to clone public figures, artists, celebrities, private individuals, or copyrighted performances without authorization.

## Quick start: mock mode

```bash
cd /Users/kx/ws/ai-voice-cover-mvp
/opt/homebrew/bin/python3.11 -m venv .venv311
. .venv311/bin/activate
pip install -e '.[dev]'
uvicorn voice_cover_mvp.app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Upload:

- sample song / target voice audio, or a YouTube URL for the target voice sample
- guide vocal for the new song
- optional instrumental
- check the consent box
- choose `mock`

Mock mode copies files to prove the workflow and API are working. YouTube URL mode uses `yt-dlp` to download a short audio sample into the job upload directory.

## API

Create job with uploaded sample:

```bash
curl -F consent=true \
  -F mode=mock \
  -F sample_song=@sample.wav \
  -F guide_vocal=@guide.wav \
  http://127.0.0.1:8000/api/jobs
```

Create job with YouTube sample URL:

```bash
curl -F consent=true \
  -F mode=mock \
  -F sample_youtube_url='https://www.youtube.com/watch?v=VIDEO_ID' \
  -F guide_vocal=@guide.wav \
  http://127.0.0.1:8000/api/jobs
```

You must provide exactly one sample source: `sample_song` upload or `sample_youtube_url`.

Get job:

```bash
curl http://127.0.0.1:8000/api/jobs/JOB_ID
```

Download final vocal:

```bash
curl -L -o converted_vocal.wav \
  http://127.0.0.1:8000/api/jobs/JOB_ID/download/final_vocal
```

Download final mix:

```bash
curl -L -o final_mix.wav \
  http://127.0.0.1:8000/api/jobs/JOB_ID/download/final_mix
```

## Real mode concept

Real mode expects open-source tools to be installed separately. By default, command templates assume an RVC checkout under:

```text
third_party/Retrieval-based-Voice-Conversion-WebUI
```

You can run real mode as a dry run first:

```bash
curl -F consent=true \
  -F mode=real \
  -F dry_run=true \
  -F sample_song=@sample.wav \
  -F guide_vocal=@guide.wav \
  http://127.0.0.1:8000/api/jobs
```

Dry-run mode writes placeholder outputs and stores the generated commands in the job log.

## Configuring commands

Different RVC forks expose different CLI entrypoints. Configure commands through environment variables:

```bash
export RVC_ROOT=/absolute/path/to/Retrieval-based-Voice-Conversion-WebUI
export VOICE_COVER_DEMUCS_CMD='demucs --two-stems=vocals -o {stems_dir} {sample_song}'
export VOICE_COVER_RVC_TRAIN_CMD='cd {rvc_root} && python infer/modules/train/train.py --experiment_name {job_id} --dataset {dataset_dir} --save_dir {model_dir}'
export VOICE_COVER_RVC_INFER_CMD='cd {rvc_root} && python tools/infer_cli.py --model {model_dir} --input {guide_vocal} --output {final_vocal}'
```

Available placeholders:

- `{job_id}`
- `{sample_song}`
- `{guide_vocal}`
- `{instrumental}`
- `{stems_dir}`
- `{dataset_dir}`
- `{model_dir}`
- `{output_dir}`
- `{rvc_root}`
- `{final_vocal}`
- `{final_mix}`

## Intended production architecture

For production, replace the in-memory job store and FastAPI background task with:

- PostgreSQL or SQLite job metadata
- S3/R2/GCS object storage for uploads and artifacts
- Celery/RQ/Arq worker queue
- GPU worker machines
- Explicit consent and license records
- Watermarking/provenance metadata
- Abuse prevention for public figures and non-consensual cloning

## Safety and legal note

Only clone your own voice or a voice you have explicit permission to use. Do not clone artists, celebrities, private individuals, or copyrighted performances without authorization.
