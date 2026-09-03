from __future__ import annotations

from pathlib import Path
import sys
import unittest
import unittest.mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_take_files  # noqa: E402


class AuditTakeFilesTests(unittest.TestCase):
    def test_media_facts_detects_audio(self):
        value = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 496,
                    "height": 864,
                    "avg_frame_rate": "24/1",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 2,
                },
            ],
            "format": {"duration": "10.5"},
        }
        facts = audit_take_files.media_facts(value)
        self.assertEqual(facts["width"], 496)
        self.assertEqual(facts["fps"], 24.0)
        self.assertTrue(facts["hasAudio"])
        self.assertEqual(facts["audioChannels"], 2)

    def test_media_facts_detects_silent_take(self):
        value = {
            "streams": [{
                "codec_type": "video",
                "codec_name": "h264",
                "width": 496,
                "height": 864,
                "avg_frame_rate": "24/1",
            }],
            "format": {"duration": "6"},
        }
        self.assertFalse(audit_take_files.media_facts(value)["hasAudio"])


class SignalGateTests(unittest.TestCase):
    """末帧冻结 / 静音覆盖 / 响度三条闸的解析与判定。

    夹具用真实 ffmpeg 输出格式（freezedetect 走 lavfi.* 元数据行，
    silencedetect 与 ebur128 走普通日志行），不是臆造字符串。
    三条闸均为 ffmpeg 内置滤镜，不引入任何新依赖。
    """

    def _probe(self, stderr: str, duration: float) -> dict:
        class _Result:
            def __init__(self, err: str) -> None:
                self.stderr = err
                self.stdout = ""

        with unittest.mock.patch.object(
            audit_take_files.subprocess, "run", return_value=_Result(stderr)
        ):
            return audit_take_files.signal_probe(Path("take.mp4"), duration, "ffmpeg")

    def test_detects_tail_freeze_when_freeze_never_closes(self):
        stderr = (
            "[Parsed_freezedetect_0 @ 0x1] lavfi.freezedetect.freeze_start: 3.022969\n"
            "    I:         -21.8 LUFS\n"
            "    Peak:      -17.7 dBFS\n"
        )
        row = {"hasAudio": True, **self._probe(stderr, 5.02)}
        self.assertAlmostEqual(row["tailFreezeFrom"], 3.022969, places=5)
        self.assertEqual(row["loudnessLufs"], -21.8)
        self.assertEqual(row["truePeakDb"], -17.7)
        findings = audit_take_files.signal_findings(row)
        self.assertTrue(any("末帧动作悬空" in f for f in findings))

    def test_mid_clip_freeze_that_recovers_is_not_flagged(self):
        # 片中冻结后恢复运动、且距片尾足够远 —— 不是「末帧悬空」，不该报
        stderr = (
            "lavfi.freezedetect.freeze_start: 1.000000\n"
            "lavfi.freezedetect.freeze_end: 1.800000\n"
            "    I:         -20.0 LUFS\n"
        )
        row = {"hasAudio": True, **self._probe(stderr, 10.0)}
        self.assertIsNone(row["tailFreezeFrom"])
        self.assertEqual(audit_take_files.signal_findings(row), [])

    def test_flags_track_that_exists_but_is_almost_entirely_silent(self):
        stderr = (
            "[silencedetect @ 0x1] silence_start: 0.1\n"
            "[silencedetect @ 0x1] silence_end: 9.8 | silence_duration: 9.7\n"
            "    I:         -70.0 LUFS\n"
        )
        row = {"hasAudio": True, **self._probe(stderr, 10.0)}
        self.assertGreaterEqual(row["silenceCoverage"], 0.9)
        findings = audit_take_files.signal_findings(row)
        self.assertTrue(any("缺少应有音轨" in f for f in findings))

    def test_tail_silence_alone_does_not_trip_the_audio_gate(self):
        # 尾部留白收尾是合法声学设计（万物生 craft 有「音效峰值后骤停留白」），不能误判成缺音轨
        stderr = (
            "silence_start: 8.0\n"
            "silence_end: 10.0 | silence_duration: 2.0\n"
            "    I:         -19.5 LUFS\n"
        )
        row = {"hasAudio": True, **self._probe(stderr, 10.0)}
        self.assertLess(row["silenceCoverage"], audit_take_files.SILENCE_COVERAGE_LIMIT)
        self.assertEqual(audit_take_files.signal_findings(row), [])

    def test_node_without_audio_track_is_not_flagged_as_missing_audio(self):
        # 无音轨节点（纯空镜）本就不该走对白音轨闸
        stderr = "silence_start: 0\nsilence_end: 8 | silence_duration: 8\n"
        row = {"hasAudio": False, **self._probe(stderr, 8.0)}
        self.assertEqual(audit_take_files.signal_findings(row), [])


if __name__ == "__main__":
    unittest.main()

