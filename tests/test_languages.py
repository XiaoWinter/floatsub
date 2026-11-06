import unittest

from floatsub.languages import (
    INPUT_LANGUAGES,
    OUTPUT_LANGUAGES,
    find_language,
    transcribe_hint,
    translate_prompt,
)


class LanguageTests(unittest.TestCase):
    def test_dialects_are_input_only(self):
        self.assertEqual(
            [item.label for item in INPUT_LANGUAGES],
            ["日语", "英语", "韩语", "中文", "上海话", "粤语"],
        )
        self.assertEqual(
            [item.label for item in OUTPUT_LANGUAGES],
            ["日语", "英语", "韩语", "中文"],
        )
        self.assertIsNone(find_language(OUTPUT_LANGUAGES, "yue"))
        self.assertIsNone(find_language(OUTPUT_LANGUAGES, "上海话"))
        self.assertEqual(find_language(OUTPUT_LANGUAGES, "zh").live, "zh-Hans")
        self.assertEqual(find_language(INPUT_LANGUAGES, "en").live, "en")
        self.assertEqual(find_language(INPUT_LANGUAGES, "yue").live, "")
        self.assertEqual(find_language(INPUT_LANGUAGES, "wuu").live, "")

    def test_shanghai_has_no_api_code(self):
        wuu = find_language(INPUT_LANGUAGES, "wuu")
        self.assertIsNotNone(wuu)
        self.assertEqual(wuu.gemini, "")
        self.assertEqual(wuu.qwen, "")
        self.assertIn("上海话", transcribe_hint(wuu))
        self.assertIn("粤语", transcribe_hint(find_language(INPUT_LANGUAGES, "yue")))
        self.assertEqual(transcribe_hint(find_language(INPUT_LANGUAGES, "en")), "")

    def test_translate_prompt_uses_the_chosen_output(self):
        english = find_language(INPUT_LANGUAGES, "en")
        japanese = find_language(INPUT_LANGUAGES, "ja")
        cantonese = find_language(INPUT_LANGUAGES, "yue")
        prompt = translate_prompt("hello", english, japanese)
        self.assertIn("译成自然的日语", prompt)
        self.assertNotIn("简体中文", prompt)
        dialect = translate_prompt("食咗未", cantonese, english)
        self.assertIn("不要按普通话理解", dialect)
        self.assertIn("译成自然的英语", dialect)


if __name__ == "__main__":
    unittest.main()
