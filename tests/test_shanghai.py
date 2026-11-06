import unittest

from floatsub.shanghai import ASR_MODEL, ShanghaiTranscript, asr_session, translate_text, translation_prompt
from floatsub.qwen_live import realtime_url


class ShanghaiTests(unittest.TestCase):
    def test_recognition_asks_for_wu_chinese(self):
        session = asr_session()["session"]
        heard = session["input_audio_transcription"]
        self.assertEqual(heard["language"], "zh")
        self.assertIn("上海话", heard["corpus"]["text"])
        self.assertNotIn("translation", session)

    def test_asr_uses_the_realtime_socket(self):
        url = realtime_url("https://dashscope.aliyuncs.com/api/v1", ASR_MODEL)
        self.assertIn("qwen3-asr-flash-realtime", url)
        self.assertTrue(url.startswith("wss://"))

    def test_a_finished_sentence_is_marked_for_translation(self):
        heard = ShanghaiTranscript()
        partial = heard.apply(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "item_id": "s",
                "delta": "侬好",
            }
        )
        self.assertEqual(partial, ("侬好", False))
        finished = heard.apply(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "s",
                "transcript": "侬好呀",
            }
        )
        self.assertEqual(finished, ("侬好呀", True))

    def test_prompt_tells_the_translator_this_is_shanghainese(self):
        prompt = translation_prompt("侬饭吃过伐", "zh-Hans")
        self.assertIn("上海话", prompt)
        self.assertIn("不要按普通话理解", prompt)
        self.assertIn("简体中文", prompt)
        self.assertIn("侬饭吃过伐", prompt)

    def test_a_busy_model_falls_through_to_the_next(self):
        tried = []

        def generate(model, _prompt):
            tried.append(model)
            if model == "gemini-3.5-flash-lite":
                raise RuntimeError("503 UNAVAILABLE. high demand")
            return "吃过了"

        self.assertEqual(translate_text("侬饭吃过伐", "zh", generate=generate), "吃过了")
        self.assertEqual(tried, ["gemini-3.5-flash-lite", "gemini-3.8-flash"])


if __name__ == "__main__":
    unittest.main()
