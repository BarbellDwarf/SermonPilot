from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from src import auto_edit


def make_config(**keeper: Any) -> dict[str, Any]:
    keeper.setdefault("min_source_gb", 0.001)
    return {"auto_edit": {"keeper": keeper}}


@pytest.fixture(autouse=True)
def reset_encoder_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    auto_edit._keeper_encoder_cache = None
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")


class TestQualityFlagMapping:
    def test_nvenc_uses_cq(self) -> None:
        assert auto_edit._keeper_quality_args("h264_nvenc", 20) == ["-cq", "20"]

    def test_vaapi_uses_qp_plus_two(self) -> None:
        assert auto_edit._keeper_quality_args("h264_vaapi", 20) == ["-qp", "22"]

    def test_libx264_uses_crf(self) -> None:
        assert auto_edit._keeper_quality_args("libx264", 20) == ["-crf", "20"]


class TestDetectChain:
    def test_nvenc_wins_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_edit, "_probe_nvenc", lambda: True)
        encoder, extra = auto_edit.detect_hardware_encoder()
        assert encoder == "h264_nvenc"
        assert extra == []

    def test_vaapi_second_with_device_node(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_edit, "_probe_nvenc", lambda: False)
        monkeypatch.setattr(auto_edit, "_probe_vaapi", lambda: "/dev/dri/renderD128")
        encoder, extra = auto_edit.detect_hardware_encoder()
        assert encoder == "h264_vaapi"
        assert extra == ["-vaapi_device", "/dev/dri/renderD128"]

    def test_libx264_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_edit, "_probe_nvenc", lambda: False)
        monkeypatch.setattr(auto_edit, "_probe_vaapi", lambda: None)
        encoder, _ = auto_edit.detect_hardware_encoder()
        assert encoder == "libx264"

    def test_probes_run_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = []

        def fake_nvenc() -> bool:
            calls.append("probe")
            return True

        monkeypatch.setattr(auto_edit, "_probe_nvenc", fake_nvenc)
        auto_edit.detect_hardware_encoder()
        auto_edit.detect_hardware_encoder()
        auto_edit.detect_hardware_encoder()
        assert len(calls) == 1

    def test_probes_never_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(cmd: object, **kw: object) -> subprocess.CompletedProcess:
            raise OSError("no such file")

        monkeypatch.setattr(auto_edit.subprocess, "run", boom)
        assert auto_edit._probe_nvenc() is False
        assert auto_edit._probe_vaapi() is None

    def test_ffmpeg_missing_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("shutil.which", lambda name: None)
        auto_edit._keeper_encoder_cache = None
        encoder, extra = auto_edit.detect_hardware_encoder()
        assert encoder == "libx264"
        auto_edit._keeper_encoder_cache = None


class TestTranscodeGates:
    def test_skips_no_subprocess_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a: object, **kw: object) -> object:
            raise AssertionError("subprocess must not be called")

        monkeypatch.setattr(auto_edit.subprocess, "run", boom)
        src = tmp_path / "big.mp4"
        src.write_bytes(b"x" * 100)
        assert (
            auto_edit.transcode_to_keeper(src, tmp_path / "k.mp4", make_config(enabled=False))
            == src
        )

    def test_skips_no_subprocess_below_min_gb(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a: object, **kw: object) -> object:
            raise AssertionError("subprocess must not be called")

        monkeypatch.setattr(auto_edit.subprocess, "run", boom)
        src = tmp_path / "small.mp4"
        src.write_bytes(b"x" * 100)
        assert (
            auto_edit.transcode_to_keeper(src, tmp_path / "k.mp4", make_config(min_source_gb=2.0))
            == src
        )


class TestTranscodeFailure:
    def test_failure_returns_source_unchanged(self, tmp_path: Path) -> None:
        src = tmp_path / "big.mp4"
        src.write_bytes(b"x" * 1024)
        cfg = make_config(min_source_gb=0.001, crf=20)
        result = auto_edit.transcode_to_keeper(src, tmp_path / "k.mp4", cfg)
        assert result == src

    def test_failure_never_deletes_source(self, tmp_path: Path) -> None:
        src = tmp_path / "big.mp4"
        src.write_bytes(b"x" * 1024)
        auto_edit.transcode_to_keeper(src, tmp_path / "k.mp4", make_config(min_source_gb=0.0))
        assert src.exists()


class TestVerifyKeeper:
    def test_passes_on_matching_durations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_ffprobe(cmd: list[str], **kw: object) -> subprocess.CompletedProcess:
            out = subprocess.CompletedProcess(cmd, 0)
            if "format=duration" in cmd:
                out.stdout = "600.5\n"
            else:
                out.stdout = "video\naudio\n"
            return out

        monkeypatch.setattr(auto_edit.subprocess, "run", fake_ffprobe)
        src = tmp_path / "s.mp4"
        keep = tmp_path / "k.mp4"
        keep.write_bytes(b"x" * 2_000_000)
        assert auto_edit.verify_keeper(src, keep) is True

    def test_fails_on_duration_drift(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lengths = iter(["600.5\n", "610.0\n"])

        def fake_ffprobe(cmd: list[str], **kw: object) -> subprocess.CompletedProcess:
            out = subprocess.CompletedProcess(cmd, 0)
            out.stdout = next(lengths)
            return out

        monkeypatch.setattr(auto_edit.subprocess, "run", fake_ffprobe)
        src = tmp_path / "s.mp4"
        keep = tmp_path / "k.mp4"
        keep.write_bytes(b"x" * 2_000_000)
        assert auto_edit.verify_keeper(src, keep) is False

    def test_fails_on_missing_streams(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_ffprobe(cmd: list[str], **kw: object) -> subprocess.CompletedProcess:
            out = subprocess.CompletedProcess(cmd, 0)
            if "format=duration" in cmd:
                out.stdout = "600.0\n"
            else:
                out.stdout = "video\n"
            return out

        monkeypatch.setattr(auto_edit.subprocess, "run", fake_ffprobe)
        src = tmp_path / "s.mp4"
        keep = tmp_path / "k.mp4"
        keep.write_bytes(b"x" * 2_000_000)
        assert auto_edit.verify_keeper(src, keep) is False

    def test_fails_on_tiny_file(self, tmp_path: Path) -> None:
        src = tmp_path / "s.mp4"
        keep = tmp_path / "k.mp4"
        keep.write_bytes(b"x" * 10)
        assert auto_edit.verify_keeper(src, keep) is False

    def test_fails_when_keeper_missing(self, tmp_path: Path) -> None:
        assert auto_edit.verify_keeper(tmp_path / "s.mp4", tmp_path / "k.mp4") is False


class TestShouldDeleteOriginal:
    def setup_keeper(self, tmp_path: Path) -> tuple[Path, Path]:
        src = tmp_path / "s.mp4"
        keep = tmp_path / "k.mp4"
        src.write_bytes(b"x" * 2_000_000)
        keep.write_bytes(b"x" * 1_500_000)
        return src, keep

    def test_delete_false_never_deletes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auto_edit, "verify_keeper", lambda s, k: True)
        src, keep = self.setup_keeper(tmp_path)
        assert (
            auto_edit.should_delete_original(src, keep, make_config(delete_original=False), True)
            is False
        )

    def test_requires_applied_plan(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_edit, "verify_keeper", lambda s, k: True)
        src, keep = self.setup_keeper(tmp_path)
        assert (
            auto_edit.should_delete_original(src, keep, make_config(delete_original=True), False)
            is False
        )

    def test_requires_verify_pass(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_edit, "verify_keeper", lambda s, k: False)
        src, keep = self.setup_keeper(tmp_path)
        assert (
            auto_edit.should_delete_original(src, keep, make_config(delete_original=True), True)
            is False
        )

    def test_requires_min_source_gb(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_edit, "verify_keeper", lambda s, k: True)
        src = tmp_path / "s.mp4"
        src.write_bytes(b"x" * 100)
        keep = tmp_path / "k.mp4"
        keep.write_bytes(b"x" * 2_000_000)
        assert (
            auto_edit.should_delete_original(src, keep, make_config(delete_original=True), True)
            is False
        )

    def test_all_gates_pass(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auto_edit, "verify_keeper", lambda s, k: True)
        src, keep = self.setup_keeper(tmp_path)
        assert (
            auto_edit.should_delete_original(src, keep, make_config(delete_original=True), True)
            is True
        )

    def test_trash_original_moves_instead_of_unlinking(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
        monkeypatch.setattr(auto_edit, "verify_keeper", lambda s, k: True)
        src, keep = self.setup_keeper(tmp_path)

        record = auto_edit.trash_original_after_edit(
            src,
            keep,
            make_config(delete_original=True),
            True,
            sermon_id="sermon-1",
            stage="post_publish",
        )

        assert record is not None
        assert record.reason == "auto_edit_keeper_replaced_original"
        assert not src.exists()
        moved = Path(record.destination)
        assert moved.is_file()
        assert moved.read_bytes() == b"x" * 2_000_000

    def test_trash_original_keeps_source_when_gates_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SERMONPILOT_TRASH_DIR", str(tmp_path / "trash"))
        monkeypatch.setattr(auto_edit, "verify_keeper", lambda s, k: True)
        src, keep = self.setup_keeper(tmp_path)

        record = auto_edit.trash_original_after_edit(
            src, keep, make_config(delete_original=False), True
        )

        assert record is None
        assert src.is_file()


@pytest.mark.heavy
class TestRealTranscode:
    def test_real_transcode_libx264(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import shutil as shutil_mod

        if shutil_mod.which("ffmpeg") is None or shutil_mod.which("ffprobe") is None:
            pytest.skip("ffmpeg not available")

        monkeypatch.setattr(auto_edit, "detect_hardware_encoder", lambda: ("libx264", []))
        src = tmp_path / "src.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-t",
                "20",
                "-i",
                "testsrc2=size=640x480:rate=25",
                "-f",
                "lavfi",
                "-t",
                "20",
                "-i",
                "sine=frequency=440",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                str(src),
            ],
            check=True,
        )
        out = tmp_path / "keeper.mp4"
        result = auto_edit.transcode_to_keeper(src, out, make_config(min_source_gb=0.0, crf=20))
        assert result == out
        assert out.exists()
        assert auto_edit.verify_keeper(src, out) is True
