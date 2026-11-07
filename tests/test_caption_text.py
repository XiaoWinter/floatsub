import unittest

from floatsub.caption_text import CaptionPager, CrawlSheet, SentenceLog, latest_line, merge_text, zip_lines
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


class SteadyScrollTests(unittest.TestCase):
    def test_the_first_line_appears_on_the_bottom_row(self):
        sheet = CrawlSheet(3)
        sheet.append_lines(["你好"])
        self.assertEqual(sheet.lines[:2], ["", ""])
        self.assertEqual(sheet.lines[2], "你好")
        self.assertEqual(sheet.scroll, 0)

    def test_movement_equals_the_requested_distance(self):
        sheet = CrawlSheet(3)
        sheet.append_lines(["你好"])
        sheet.tick(0.2)
        sheet.tick(0.2)
        self.assertAlmostEqual(sheet.scroll, 0.4)
        sheet.tick(1.5)
        self.assertAlmostEqual(sheet.scroll, 1.9)

    def test_a_pause_adds_blank_lines_without_speeding_up(self):
        sheet = CrawlSheet(3)
        sheet.append_lines(["你好"])
        sheet.tick(2)
        self.assertAlmostEqual(sheet.scroll, 2)
        self.assertEqual(sheet.lines[-1], "")

    def test_translation_and_source_share_a_row(self):
        self.assertEqual(zip_lines(["你好。", "第二行"], ["hello"]), [("你好。", "hello"), ("第二行", "")])
        sheet = CrawlSheet(3)
        sheet.append_rows(zip_lines(["你好。"], ["hello"]))
        self.assertEqual(sheet.lines[2], ("你好。", "hello"))

    def test_a_burst_waits_below_and_the_speed_stays_put(self):
        sheet = CrawlSheet(3)
        sheet.append_lines(["第一"])
        sheet.tick(0.3)
        sheet.append_lines(["第二", "第三", "第四"])
        self.assertAlmostEqual(sheet.scroll, 0.3)
        self.assertEqual(sheet.lines[-3:], ["第二", "第三", "第四"])


class SentenceLogTests(unittest.TestCase):
    def test_an_open_fragment_stays_off_the_page(self):
        log = SentenceLog()
        self.assertEqual(log.push("你好"), "")
        self.assertEqual(log.push("你好世界"), "")
        self.assertEqual(log.transcript, "")

    def test_a_finished_sentence_stays_and_the_next_one_joins_it(self):
        log = SentenceLog()
        self.assertEqual(log.push("今天天气很好。"), "今天天气很好。")
        self.assertEqual(log.push("今天天气很好。我们出门"), "")
        self.assertEqual(log.push("今天天气很好。我们出门吧。"), "我们出门吧。")
        self.assertEqual(log.transcript, "今天天气很好。我们出门吧。")

    def test_a_closed_utterance_is_appended_without_punctuation(self):
        log = SentenceLog()
        self.assertEqual(log.push("我们出门", closed=True), "我们出门")
        self.assertEqual(log.push("顺便买点东西。"), "顺便买点东西。")
        self.assertEqual(log.transcript, "我们出门顺便买点东西。")

    def test_repeating_the_same_snapshot_does_not_duplicate(self):
        log = SentenceLog()
        log.push("今天天气很好。")
        self.assertEqual(log.push("今天天气很好。"), "")
        self.assertEqual(log.push("今天天气很好。", closed=True), "")
        self.assertEqual(log.transcript, "今天天气很好。")

    def test_a_later_utterance_keeps_the_earlier_text(self):
        log = SentenceLog()
        log.push("第一句。", closed=True)
        log.push("第二句。", closed=True)
        self.assertEqual(log.transcript, "第一句。第二句。")


if __name__ == "__main__":
    unittest.main()
