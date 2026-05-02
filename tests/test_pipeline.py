from pathlib import Path

from voice_cover_mvp.pipeline import PipelineConfig, VoiceCoverPipeline


def test_mock_pipeline_creates_expected_artifacts(tmp_path: Path):
    sample = tmp_path / "sample.wav"
    guide = tmp_path / "guide.wav"
    sample.write_bytes(b"sample-audio")
    guide.write_bytes(b"guide-audio")

    pipeline = VoiceCoverPipeline(PipelineConfig(workspace=tmp_path, mode="mock"))
    result = pipeline.run(job_id="job123", sample_song=sample, guide_vocal=guide)

    assert result.final_vocal.exists()
    assert result.final_mix.exists()
    assert result.model_dir.exists()
    assert "mock mode" in result.log.lower()


def test_real_pipeline_builds_demucs_and_rvc_commands_without_running(tmp_path: Path):
    sample = tmp_path / "sample.wav"
    guide = tmp_path / "guide.wav"
    sample.write_bytes(b"sample-audio")
    guide.write_bytes(b"guide-audio")

    config = PipelineConfig(
        workspace=tmp_path,
        mode="real",
        dry_run=True,
        rvc_root=tmp_path / "third_party" / "Retrieval-based-Voice-Conversion-WebUI",
    )
    pipeline = VoiceCoverPipeline(config)
    result = pipeline.run(job_id="job456", sample_song=sample, guide_vocal=guide)

    assert result.final_vocal.exists()
    assert "demucs" in result.log
    assert "RVC_TRAIN_CMD" in result.log
    assert "RVC_INFER_CMD" in result.log
    assert str(sample) in result.log
    assert str(guide) in result.log
