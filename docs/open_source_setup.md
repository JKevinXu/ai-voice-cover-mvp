# Open-source setup notes

This MVP is an orchestrator. Install the ML tools separately.

## Demucs

```bash
pip install demucs
```

Project:
https://github.com/facebookresearch/demucs

## RVC WebUI

```bash
mkdir -p third_party
cd third_party
git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git
```

Project:
https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI

RVC's exact install and CLI commands can change between forks and versions. Use this MVP's command-template environment variables to adapt to the installed RVC checkout.

## Recommended real pipeline

1. Upload sample song.
2. Use Demucs to isolate target vocal.
3. Slice/clean vocal dataset.
4. Train or fine-tune RVC model.
5. Upload guide vocal singing the new song.
6. Run RVC inference to convert guide vocal into target voice.
7. Mix converted vocal with instrumental using ffmpeg.

## MVP shortcut

For the first real test, skip training inside the web request:

1. Train an RVC model manually in RVC WebUI.
2. Configure `VOICE_COVER_RVC_INFER_CMD` to use that existing model.
3. Use this app for upload, inference orchestration, and artifact download.
