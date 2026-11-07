import unittest

from floatsub.languages import INPUT_LANGUAGES, OUTPUT_LANGUAGES, find_language


class LanguageTests(unittest.TestCase):
    def test_heard_and_written_use_the_same_languages(self):
        labels = ["日语", "英语", "韩语", "中文"]
        self.assertEqual([item.label for item in INPUT_LANGUAGES], labels)
        self.assertEqual([item.label for item in OUTPUT_LANGUAGES], labels)
        self.assertEqual(find_language(OUTPUT_LANGUAGES, "zh").live, "zh-Hans")
        self.assertEqual(find_language(INPUT_LANGUAGES, "en").live, "en")


if __name__ == "__main__":
    unittest.main()
