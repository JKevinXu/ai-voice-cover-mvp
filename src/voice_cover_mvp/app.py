from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .pipeline import PipelineConfig, VoiceCoverPipeline


class JobRecord(BaseModel):
    id: str
    status: str
    mode: str
    sample_song: str
    guide_vocal: str
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


def create_app(workspace: Path | str = "./workspace") -> FastAPI:
    workspace_path = Path(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    store = InMemoryJobStore()
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
              <label>Sample song / target voice audio<br><input name="sample_song" type="file" required></label><br><br>
              <label>Guide vocal for the new song<br><input name="guide_vocal" type="file" required></label><br><br>
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
        sample_song: Annotated[UploadFile, File()],
        guide_vocal: Annotated[UploadFile, File()],
        instrumental: Annotated[UploadFile | None, File()] = None,
        consent: Annotated[str | None, Form()] = None,
        mode: Annotated[str, Form()] = "mock",
        dry_run: Annotated[bool, Form()] = False,
    ) -> JobRecord:
        if str(consent).lower() not in {"true", "1", "yes", "on"}:
            raise HTTPException(status_code=400, detail="Consent is required: only clone your own voice or voices you have explicit permission to use.")
        if mode not in {"mock", "real"}:
            raise HTTPException(status_code=400, detail="mode must be 'mock' or 'real'")

        job_id = uuid.uuid4().hex[:12]
        upload_dir = workspace_path / "jobs" / job_id / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        sample_path = await _save_upload(sample_song, upload_dir)
        guide_path = await _save_upload(guide_vocal, upload_dir)
        instrumental_path = await _save_upload(instrumental, upload_dir) if instrumental else None

        record = store.create(
            JobRecord(
                id=job_id,
                status="queued",
                mode=mode,
                sample_song=str(sample_path),
                guide_vocal=str(guide_path),
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
