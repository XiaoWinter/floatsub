import json
import tempfile
import unittest
from pathlib import Path

from floatsub.records import RecordSession


class RecordTests(unittest.TestCase):
    def test_writes_wav_and_captions(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = RecordSession.open("msedge.exe", "gemini", pid=12, root=Path(tmp))
            name = session.add(b"RIFFdemo", "hello", "你好")
            self.assertEqual(name, "0001.wav")
            self.assertEqual((session.directory / name).read_bytes(), b"RIFFdemo")
            meta = json.loads((session.directory / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["app"], "msedge.exe")
            self.assertEqual(meta["provider"], "gemini")
            self.assertEqual(meta["pid"], 12)
            line = json.loads((session.directory / "captions.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(line["source"], "hello")
            self.assertEqual(line["zh"], "你好")
            text = (session.directory / "captions.txt").read_text(encoding="utf-8")
            self.assertIn("原文：hello", text)
            self.assertIn("译文：你好", text)

    def test_app_name_cannot_escape_records_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = RecordSession.open('bad/name:app', "qwen", root=Path(tmp))
            self.assertEqual(session.directory.parent, Path(tmp))
            self.assertNotIn("/", session.directory.name)
            self.assertNotIn(":", session.directory.name)


if __name__ == "__main__":
    unittest.main()
