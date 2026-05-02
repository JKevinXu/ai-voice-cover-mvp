from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    workspace: Path
    mode: str = "mock"
    dry_run: bool = False
    rvc_root: Path | None = None
    demucs_cmd: str | None = None
    rvc_train_cmd: str | None = None
    rvc_infer_cmd: str | None = None

    @classmethod
    def from_env(cls, workspace: Path, mode: str = "mock", dry_run: bool = False) -> "PipelineConfig":
        return cls(
            workspace=workspace,
            mode=mode,
            dry_run=dry_run,
            rvc_root=Path(os.getenv("RVC_ROOT", "third_party/Retrieval-based-Voice-Conversion-WebUI")),
            demucs_cmd=os.getenv("VOICE_COVER_DEMUCS_CMD"),
            rvc_train_cmd=os.getenv("VOICE_COVER_RVC_TRAIN_CMD"),
            rvc_infer_cmd=os.getenv("VOICE_COVER_RVC_INFER_CMD"),
        )


@dataclass(frozen=True)
class PipelineResult:
    final_vocal: Path
    final_mix: Path
    model_dir: Path
    log: str


class VoiceCoverPipeline:
    """Small adapter around open-source Demucs + RVC style workflows.

    The MVP intentionally supports a safe `mock` mode and a `real` dry-run mode.
    Real execution is command-template based because RVC forks expose different
    CLIs. Users can set VOICE_COVER_*_CMD environment variables to match their
    local RVC checkout.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.workspace = Path(config.workspace)

    def run(
        self,
        job_id: str,
        sample_song: Path,
        guide_vocal: Path,
        instrumental: Path | None = None,
    ) -> PipelineResult:
        job_dir = self.workspace / "jobs" / job_id
        stems_dir = job_dir / "stems"
        dataset_dir = job_dir / "dataset"
        model_dir = job_dir / "model"
        output_dir = job_dir / "outputs"
        for directory in (stems_dir, dataset_dir, model_dir, output_dir):
            directory.mkdir(parents=True, exist_ok=True)

        log_lines: list[str] = []
        if self.config.mode == "mock":
            return self._run_mock(sample_song, guide_vocal, instrumental, dataset_dir, model_dir, output_dir)

        context = {
            "job_id": job_id,
            "sample_song": str(sample_song),
            "guide_vocal": str(guide_vocal),
            "instrumental": str(instrumental or ""),
            "stems_dir": str(stems_dir),
            "dataset_dir": str(dataset_dir),
            "model_dir": str(model_dir),
            "output_dir": str(output_dir),
            "rvc_root": str(self.config.rvc_root or "third_party/Retrieval-based-Voice-Conversion-WebUI"),
            "final_vocal": str(output_dir / "converted_vocal.wav"),
            "final_mix": str(output_dir / "final_mix.wav"),
        }

        commands = self._build_commands(context)
        for label, command in commands:
            line = f"{label}: {command}"
            log_lines.append(line)
            if not self.config.dry_run:
                self._run_shell(command, cwd=self.workspace, log_lines=log_lines)

        final_vocal = output_dir / "converted_vocal.wav"
        final_mix = output_dir / "final_mix.wav"
        if self.config.dry_run:
            final_vocal.write_text("dry-run placeholder for converted vocal\n")
            final_mix.write_text("dry-run placeholder for final mix\n")
        elif not final_mix.exists() and final_vocal.exists():
            shutil.copyfile(final_vocal, final_mix)

        log = "\n".join(log_lines)
        (output_dir / "pipeline.log").write_text(log)
        return PipelineResult(final_vocal=final_vocal, final_mix=final_mix, model_dir=model_dir, log=log)

    def _run_mock(
        self,
        sample_song: Path,
        guide_vocal: Path,
        instrumental: Path | None,
        dataset_dir: Path,
        model_dir: Path,
        output_dir: Path,
    ) -> PipelineResult:
        target_vocal = dataset_dir / "target_voice_sample.wav"
        shutil.copyfile(sample_song, target_vocal)
        final_vocal = output_dir / "converted_vocal.wav"
        shutil.copyfile(guide_vocal, final_vocal)
        final_mix = output_dir / "final_mix.wav"
        if instrumental:
            final_mix.write_bytes(instrumental.read_bytes() + b"\n" + final_vocal.read_bytes())
        else:
            shutil.copyfile(final_vocal, final_mix)
        (model_dir / "README.txt").write_text("Mock RVC model placeholder. Replace mock mode with real RVC training for production.\n")
        log = "Mock mode: copied sample as target dataset, copied guide vocal as converted vocal."
        (output_dir / "pipeline.log").write_text(log)
        return PipelineResult(final_vocal=final_vocal, final_mix=final_mix, model_dir=model_dir, log=log)

    def _build_commands(self, context: dict[str, str]) -> list[tuple[str, str]]:
        demucs = self.config.demucs_cmd or "demucs --two-stems=vocals -o {stems_dir} {sample_song}"
        train = self.config.rvc_train_cmd or (
            "cd {rvc_root} && "
            "python infer/modules/train/train.py --experiment_name {job_id} --dataset {dataset_dir} --save_dir {model_dir}"
        )
        infer = self.config.rvc_infer_cmd or (
            "cd {rvc_root} && "
            "python tools/infer_cli.py --model {model_dir} --input {guide_vocal} --output {final_vocal}"
        )
        mix = "ffmpeg -y -i {final_vocal} {final_mix}"
        if context.get("instrumental"):
            mix = "ffmpeg -y -i {instrumental} -i {final_vocal} -filter_complex amix=inputs=2:duration=longest {final_mix}"
        return [
            ("DEMUCS_CMD", demucs.format(**context)),
            ("RVC_TRAIN_CMD", train.format(**context)),
            ("RVC_INFER_CMD", infer.format(**context)),
            ("MIX_CMD", mix.format(**context)),
        ]

    @staticmethod
    def _run_shell(command: str, cwd: Path, log_lines: list[str]) -> None:
        proc = subprocess.run(command, shell=True, cwd=cwd, text=True, capture_output=True)
        if proc.stdout:
            log_lines.append(proc.stdout)
        if proc.stderr:
            log_lines.append(proc.stderr)
        if proc.returncode != 0:
            raise RuntimeError(f"Pipeline command failed with exit code {proc.returncode}: {command}")
