from __future__ import annotations

import glob
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


Runner = Callable[[list[str]], None]


def validate_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


class YouTubeAudioDownloader:
    """Download a short audio sample from YouTube using yt-dlp.

    This adapter intentionally downloads only the first two minutes by default,
    which is usually enough for MVP voice sampling and avoids unnecessary media
    storage. Users still need explicit permission to clone the sampled voice.
    """

    def __init__(self, runner: Runner | None = None, sample_section: str = "*0:00-2:00") -> None:
        self.runner = runner or self._default_runner
        self.sample_section = sample_section

    def download_audio(self, url: str, output_dir: Path, prefix: str = "sample") -> Path:
        if not validate_youtube_url(url):
            raise ValueError("Only YouTube URLs are supported for audio URL inputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / f"{prefix}.%(id)s.%(ext)s")
        before = set(glob.glob(str(output_dir / f"{prefix}.*")))
        command = [
            "yt-dlp",
            "--extract-audio",
            "--audio-format",
            "m4a",
            "--download-sections",
            self.sample_section,
            "--output",
            output_template,
            url,
        ]
        self.runner(command)
        after = sorted(set(glob.glob(str(output_dir / f"{prefix}.*"))) - before)
        if not after:
            after = sorted(glob.glob(str(output_dir / f"{prefix}.*")))
        if not after:
            raise RuntimeError("yt-dlp completed but no YouTube audio sample was created")
        return Path(after[-1])

    @staticmethod
    def _default_runner(command: list[str]) -> None:
        subprocess.run(command, check=True)
