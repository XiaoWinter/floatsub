import unittest

from floatsub.gemini_live import LiveCaptions


class LiveCaptionTests(unittest.TestCase):
    def test_interim_shows_until_source_text_arrives(self):
        captions = LiveCaptions()
        captions.add_interim("hel")
        self.assertEqual(captions.visible(), ("hel", ""))
        captions.add_source("hello")
        self.assertEqual(captions.visible(), ("hello", ""))

    def test_finished_target_commits_the_pair(self):
        captions = LiveCaptions()
        captions.add_source("hello")
        self.assertIsNone(captions.add_target("你", False))
        pair = captions.add_target("好", True)
        self.assertEqual(pair, ("hello", "你好"))
        self.assertEqual(captions.visible(), ("", ""))

    def test_turn_end_commits_leftover_text(self):
        captions = LiveCaptions()
        captions.add_source("hello")
        captions.add_target("你好", False)
        self.assertEqual(captions.end_turn(), ("hello", "你好"))
        self.assertIsNone(captions.end_turn())


if __name__ == "__main__":
    unittest.main()
