from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .pipeline import PipelineConfig, VoiceCoverPipeline
from .youtube import YouTubeAudioDownloader


class JobRecord(BaseModel):
    id: str
    status: str
    mode: str
    sample_song: str
    sample_source: str = "upload"
    sample_youtube_url: str | None = None
    guide_vocal: str
    guide_source: str = "upload"
    guide_youtube_url: str | None = None
    instrumental: str | None = None
    final_vocal: str | None = None
    final_mix: str | None = None
    log: str = ""
    error: str | None = None


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def create(self, record: JobRecord) -> JobRecord:
        self._jobs[record.id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **changes: object) -> JobRecord:
        current = self._jobs[job_id]
        updated = current.model_copy(update=changes)
        self._jobs[job_id] = updated
        return updated


def create_app(workspace: Path | str = "./workspace", youtube_downloader: YouTubeAudioDownloader | None = None) -> FastAPI:
    workspace_path = Path(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    store = InMemoryJobStore()
    downloader = youtube_downloader or YouTubeAudioDownloader()
    app = FastAPI(title="AI Voice Cover MVP", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """
        <!doctype html>
        <html>
          <head><title>AI Voice Cover MVP</title></head>
          <body style="font-family: sans-serif; max-width: 760px; margin: 40px auto;">
            <h1>AI Voice Cover MVP</h1>
            <p>Consent-based singing voice conversion using open-source Demucs + RVC adapters.</p>
            <form action="/api/jobs" method="post" enctype="multipart/form-data">
              <label>Sample song / target voice audio<br><input name="sample_song" type="file"></label><br>
              <label>Or YouTube URL for target voice sample<br><input name="sample_youtube_url" type="url" placeholder="https://www.youtube.com/watch?v=..."></label>
              <p style="font-size: 0.9em; color: #555;">Provide exactly one sample source: upload OR YouTube URL. Only use voices you own or have permission to clone.</p>
              <label>Guide vocal for the new song<br><input name="guide_vocal" type="file"></label><br>
              <label>Or YouTube URL for guide vocal<br><input name="guide_youtube_url" type="url" placeholder="https://www.youtube.com/watch?v=..."></label>
              <p style="font-size: 0.9em; color: #555;">Provide exactly one guide source: upload OR YouTube URL.</p>
              <label>Optional instrumental track<br><input name="instrumental" type="file"></label><br><br>
              <label>Mode
                <select name="mode">
                  <option value="mock">mock - verify workflow without ML</option>
                  <option value="real">real - run configured Demucs/RVC commands</option>
                </select>
              </label><br><br>
              <label><input name="consent" value="true" type="checkbox" required> I own or have explicit permission to clone this voice.</label><br><br>
              <button type="submit">Create job</button>
            </form>
          </body>
        </html>
        """

    @app.post("/api/jobs", response_model=JobRecord)
    async def create_job(
        background_tasks: BackgroundTasks,
        sample_song: Annotated[UploadFile | None, File()] = None,
        guide_vocal: Annotated[UploadFile | None, File()] = None,
        instrumental: Annotated[UploadFile | None, File()] = None,
        sample_youtube_url: Annotated[str | None, Form()] = None,
        guide_youtube_url: Annotated[str | None, Form()] = None,
        consent: Annotated[str | None, Form()] = None,
        mode: Annotated[str, Form()] = "mock",
        dry_run: Annotated[bool, Form()] = False,
    ) -> JobRecord:
        if str(consent).lower() not in {"true", "1", "yes", "on"}:
            raise HTTPException(status_code=400, detail="Consent is required: only clone your own voice or voices you have explicit permission to use.")
        if mode not in {"mock", "real"}:
            raise HTTPException(status_code=400, detail="mode must be 'mock' or 'real'")

        youtube_url = sample_youtube_url.strip() if sample_youtube_url else None
        guide_url = guide_youtube_url.strip() if guide_youtube_url else None
        has_upload = sample_song is not None and bool(sample_song.filename)
        has_youtube = bool(youtube_url)
        has_guide_upload = guide_vocal is not None and bool(guide_vocal.filename)
        has_guide_youtube = bool(guide_url)
        if has_upload == has_youtube:
            raise HTTPException(status_code=400, detail="Provide exactly one sample source: sample_song upload or sample_youtube_url")
        if has_guide_upload == has_guide_youtube:
            raise HTTPException(status_code=400, detail="Provide exactly one guide source: guide_vocal upload or guide_youtube_url")

        job_id = uuid.uuid4().hex[:12]
        upload_dir = workspace_path / "jobs" / job_id / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        if has_youtube:
            try:
                sample_path = downloader.download_audio(youtube_url, upload_dir, prefix="sample")  # type: ignore[arg-type]
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Could not download YouTube sample: {exc}") from exc
            sample_source = "youtube"
        else:
            sample_path = await _save_upload(sample_song, upload_dir)  # type: ignore[arg-type]
            sample_source = "upload"
        if has_guide_youtube:
            try:
                guide_path = downloader.download_audio(guide_url, upload_dir, prefix="guide")  # type: ignore[arg-type]
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Could not download YouTube guide vocal: {exc}") from exc
            guide_source = "youtube"
        else:
            guide_path = await _save_upload(guide_vocal, upload_dir)  # type: ignore[arg-type]
            guide_source = "upload"
        instrumental_path = await _save_upload(instrumental, upload_dir) if instrumental else None

        record = store.create(
            JobRecord(
                id=job_id,
                status="queued",
                mode=mode,
                sample_song=str(sample_path),
                sample_source=sample_source,
                sample_youtube_url=youtube_url if has_youtube else None,
                guide_vocal=str(guide_path),
                guide_source=guide_source,
                guide_youtube_url=guide_url if has_guide_youtube else None,
                instrumental=str(instrumental_path) if instrumental_path else None,
            )
        )
        background_tasks.add_task(_run_job, store, workspace_path, job_id, mode, dry_run)
        return record

    @app.get("/api/jobs/{job_id}", response_model=JobRecord)
    def get_job(job_id: str) -> JobRecord:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="job not found")
        return record

    @app.get("/api/jobs/{job_id}/download/{artifact}")
    def download(job_id: str, artifact: str) -> FileResponse:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="job not found")
        if artifact not in {"final_vocal", "final_mix"}:
            raise HTTPException(status_code=400, detail="artifact must be final_vocal or final_mix")
        path_value = getattr(record, artifact)
        if not path_value:
            raise HTTPException(status_code=404, detail="artifact not ready")
        path = Path(path_value)
        if not path.exists():
            raise HTTPException(status_code=404, detail="artifact file missing")
        return FileResponse(path)

    return app


async def _save_upload(upload: UploadFile, upload_dir: Path) -> Path:
    safe_name = Path(upload.filename or "upload.bin").name
    path = upload_dir / safe_name
    with path.open("wb") as fh:
        while chunk := await upload.read(1024 * 1024):
            fh.write(chunk)
    return path


def _run_job(store: InMemoryJobStore, workspace: Path, job_id: str, mode: str, dry_run: bool) -> None:
    record = store.update(job_id, status="running")
    try:
        config = PipelineConfig.from_env(workspace=workspace, mode=mode, dry_run=dry_run)
        pipeline = VoiceCoverPipeline(config)
        result = pipeline.run(
            job_id=job_id,
            sample_song=Path(record.sample_song),
            guide_vocal=Path(record.guide_vocal),
            instrumental=Path(record.instrumental) if record.instrumental else None,
        )
        store.update(
            job_id,
            status="completed",
            final_vocal=str(result.final_vocal),
            final_mix=str(result.final_mix),
            log=result.log,
        )
    except Exception as exc:  # pragma: no cover - defensive background task guard
        store.update(job_id, status="failed", error=str(exc))


app = create_app()
