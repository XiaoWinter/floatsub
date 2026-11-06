import unittest

from floatsub.debug_feed import TimedInbox, format_event


class DebugFeedTests(unittest.TestCase):
    def test_gap_is_the_time_between_arrivals(self):
        first, shown = format_event(1_700_000_000.1, 10.0, None, "live", ("你好", "hello"))
        second, _shown = format_event(1_700_000_000.45, 10.35, 10.0, "live", ("", "侬好"), shown)
        self.assertIn("live", first)
        self.assertIn("译 你好", first)
        self.assertIn("原 hello", first)
        self.assertIn("+350ms", second)
        self.assertIn("译 （空）", second)
        self.assertIn("原 侬好", second)

    def test_a_longer_snapshot_only_keeps_the_new_tail(self):
        _first, shown = format_event(1.0, 1.0, None, "live", ("让我们", "Let's"))
        grown, shown = format_event(1.1, 1.1, 1.0, "live", ("让我们想象一下", "Let's"), shown)
        same, _shown = format_event(1.2, 1.2, 1.1, "live", ("让我们想象一下", "Let's"), shown)
        self.assertIn("译 +想象一下", grown)
        self.assertNotIn("让我们想象", grown)
        self.assertNotIn("原", grown)
        self.assertIsNone(same)

    def test_inbox_stamps_the_moment_it_is_put(self):
        inbox = TimedInbox()
        inbox.put(("caption", "译文", "原文"))
        wall, mono, item = inbox.get_nowait()
        self.assertEqual(item, ("caption", "译文", "原文"))
        self.assertGreater(wall, 1_000_000_000)
        self.assertGreater(mono, 0)


if __name__ == "__main__":
    unittest.main()
