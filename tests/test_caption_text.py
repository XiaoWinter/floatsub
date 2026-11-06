import unittest

from floatsub.caption_text import CaptionPager, latest_line, merge_text
from floatsub.gemini_live import LiveCaptions


class CaptionTextTests(unittest.TestCase):
    def test_snapshot_replaces_the_shorter_text(self):
        self.assertEqual(merge_text("你好", "你好世界"), "你好世界")

    def test_latest_line_drops_finished_sentences(self):
        self.assertEqual(latest_line("第一句。第二句正在说"), "第二句正在说")
        self.assertEqual(latest_line("第一句。第二句。"), "第二句。")

    def test_growth_appends_without_repeating(self):
        pager = CaptionPager()
        self.assertEqual(pager.push("你好", 20), "你好")
        self.assertEqual(pager.push("你好世界", 20), "你好世界")
        self.assertEqual(pager.push("你好世界", 20), "你好世界")

    def test_a_finished_sentence_stays_while_the_next_one_is_spoken(self):
        pager = CaptionPager()
        self.assertEqual(pager.push("一二三四五。", 10), "一二三四五。")
        shown = pager.push("一二三四五。甲乙丙", 10)
        self.assertEqual(shown, "一二三四五。\n甲乙丙")
        self.assertEqual(pager.push("一二三四五。甲乙丙丁戊。", 10), "甲乙丙丁戊。")

    def test_a_new_sentence_rolls_under_the_previous_line(self):
        pager = CaptionPager()
        pager.push("一二三四五。", 10)
        self.assertEqual(pager.push("甲乙丙", 10), "一二三四五。\n甲乙丙")
        rolled = pager.push("甲乙丙丁戊。", 10)
        self.assertEqual(rolled, "甲乙丙丁戊。")
        self.assertNotIn("一二三四五", rolled)

    def test_a_full_line_moves_up_whole(self):
        pager = CaptionPager()
        self.assertEqual(pager.push("一二三四五六七八", 8), "一二三四五六七八")
        shown = pager.push("一二三四五六七八九", 8)
        self.assertEqual(shown, "一二三四五六七八\n九")
        filled = "一二三四五六七八九十甲乙丙丁戊己"
        self.assertEqual(pager.push(filled, 8), "一二三四五六七八\n九十甲乙丙丁戊己")
        rolled = pager.push(filled + "庚", 8)
        self.assertEqual(rolled, "九十甲乙丙丁戊己\n庚")
        self.assertNotIn("一二三四五六七八", rolled)

    def test_a_small_edit_does_not_replay_the_first_line(self):
        pager = CaptionPager()
        pager.push("一二三四五。", 10)
        pager.push("一二三四五。甲乙丙", 10)
        shown = pager.push("一二三四五！甲乙丙丁", 10)
        self.assertEqual(shown, "一二三四五。\n甲乙丙丁")

    def test_resending_the_transcript_does_not_bring_old_lines_back(self):
        pager = CaptionPager()
        pager.push("一二三四五。", 10)
        pager.push("一二三四五。甲乙丙丁戊。", 10)
        again = pager.push("一二三四五。甲乙丙丁戊。", 10)
        self.assertEqual(again, "甲乙丙丁戊。")
        continued = pager.push("一二三四五。甲乙丙丁戊。子丑", 10)
        self.assertEqual(continued, "甲乙丙丁戊。\n子丑")
        self.assertNotIn("一二三四五", continued)

    def test_rewrite_replaces_the_open_tail(self):
        pager = CaptionPager()
        pager.push("一二三四五。", 10)
        pager.push("一二三四五。甲乙丙", 10)
        self.assertEqual(pager.push("一二三四五。甲乙啊", 10), "一二三四五。\n甲乙啊")

    def test_gemini_snapshot_does_not_pile_up(self):
        captions = LiveCaptions()
        captions.add_target("你好", False)
        captions.add_target("你好世界", False)
        self.assertEqual(captions.visible()[1], "你好世界")


if __name__ == "__main__":
    unittest.main()
