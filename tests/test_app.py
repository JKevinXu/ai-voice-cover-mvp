from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from voice_cover_mvp.app import create_app


def test_create_job_requires_consent(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    client = TestClient(app)
    sample = ("sample.wav", b"sample-audio", "audio/wav")
    guide = ("guide.wav", b"guide-audio", "audio/wav")

    response = client.post(
        "/api/jobs",
        data={"mode": "mock"},
        files={"sample_song": sample, "guide_vocal": guide},
    )

    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()


def test_create_mock_job_saves_uploads_and_returns_job(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        data={"consent": "true", "mode": "mock"},
        files={
            "sample_song": ("sample.wav", b"sample-audio", "audio/wav"),
            "guide_vocal": ("guide.wav", b"guide-audio", "audio/wav"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"queued", "running", "completed"}
    assert body["id"]
    assert (tmp_path / "jobs" / body["id"] / "uploads" / "sample.wav").exists()
    assert (tmp_path / "jobs" / body["id"] / "uploads" / "guide.wav").exists()

    detail = client.get(f"/api/jobs/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == body["id"]
