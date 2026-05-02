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
    assert body["sample_source"] == "upload"
    assert (tmp_path / "jobs" / body["id"] / "uploads" / "sample.wav").exists()
    assert (tmp_path / "jobs" / body["id"] / "uploads" / "guide.wav").exists()

    detail = client.get(f"/api/jobs/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == body["id"]


class FakeYouTubeDownloader:
    def download_audio(self, url: str, output_dir: Path) -> Path:
        path = output_dir / "youtube_sample.m4a"
        path.write_bytes(f"downloaded from {url}".encode())
        return path


def test_create_job_accepts_youtube_url_as_sample_source(tmp_path: Path):
    app = create_app(workspace=tmp_path, youtube_downloader=FakeYouTubeDownloader())
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        data={
            "consent": "true",
            "mode": "mock",
            "sample_youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
        files={
            "guide_vocal": ("guide.wav", b"guide-audio", "audio/wav"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sample_source"] == "youtube"
    assert body["sample_youtube_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    sample_path = Path(body["sample_song"])
    assert sample_path.name == "youtube_sample.m4a"
    assert sample_path.exists()


def test_create_job_requires_exactly_one_sample_source(tmp_path: Path):
    app = create_app(workspace=tmp_path, youtube_downloader=FakeYouTubeDownloader())
    client = TestClient(app)

    missing = client.post(
        "/api/jobs",
        data={"consent": "true", "mode": "mock"},
        files={"guide_vocal": ("guide.wav", b"guide-audio", "audio/wav")},
    )
    assert missing.status_code == 400
    assert "sample" in missing.json()["detail"].lower()

    both = client.post(
        "/api/jobs",
        data={
            "consent": "true",
            "mode": "mock",
            "sample_youtube_url": "https://youtu.be/dQw4w9WgXcQ",
        },
        files={
            "sample_song": ("sample.wav", b"sample-audio", "audio/wav"),
            "guide_vocal": ("guide.wav", b"guide-audio", "audio/wav"),
        },
    )
    assert both.status_code == 400
    assert "one sample source" in both.json()["detail"].lower()
