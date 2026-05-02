from pathlib import Path

import pytest

from voice_cover_mvp.youtube import YouTubeAudioDownloader, validate_youtube_url


def test_validate_youtube_url_accepts_youtube_hosts():
    assert validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert validate_youtube_url("https://youtu.be/dQw4w9WgXcQ")


def test_validate_youtube_url_rejects_non_youtube_hosts():
    assert not validate_youtube_url("https://example.com/watch?v=dQw4w9WgXcQ")


def test_downloader_builds_yt_dlp_audio_command(tmp_path: Path):
    commands: list[list[str]] = []

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        (tmp_path / "target.abc123.m4a").write_bytes(b"audio")

    downloader = YouTubeAudioDownloader(runner=fake_runner)
    path = downloader.download_audio("https://youtu.be/dQw4w9WgXcQ", tmp_path, prefix="target")

    assert path.name == "target.abc123.m4a"
    assert path.exists()
    command = commands[0]
    assert command[0] == "yt-dlp"
    assert "--extract-audio" in command
    assert "--download-sections" in command
    assert "*0:00-2:00" in command


def test_downloader_rejects_non_youtube_url(tmp_path: Path):
    downloader = YouTubeAudioDownloader(runner=lambda command: None)
    with pytest.raises(ValueError, match="YouTube"):
        downloader.download_audio("https://example.com/video", tmp_path)
