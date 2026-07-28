from __future__ import annotations

from pathlib import Path
import sys
import unittest


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


if __name__ == "__main__":
    unittest.main()

