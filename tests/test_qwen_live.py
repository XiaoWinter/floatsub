import unittest

from floatsub.qwen_live import QwenCaptions, realtime_url, session_update


class QwenLiveTests(unittest.TestCase):
    def test_session_uses_a_voice_this_model_accepts(self):
        session = session_update("zh")["session"]
        self.assertEqual(session["output_modalities"], ["text"])
        self.assertEqual(session["voice"], "Tina")
        self.assertNotEqual(session["voice"], "Chelsie")

    def test_realtime_url_uses_dashscope_websocket(self):
        url = realtime_url(
            "https://dashscope.aliyuncs.com/api/v1",
            "qwen3.8-livetranslate-flash-realtime",
        )
        self.assertEqual(
            url,
            "wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3.8-livetranslate-flash-realtime",
        )

    def test_deltas_commit_when_the_translation_finishes(self):
        captions = QwenCaptions()
        captions.apply(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "item_id": "src",
                "delta": "hello",
            }
        )
        self.assertIsNone(captions.apply({"type": "response.text.delta", "delta": "你"}))
        self.assertEqual(captions.visible(), ("hello", "你"))
        pair = captions.apply({"type": "response.text.done", "text": "你好"})
        self.assertEqual(pair, ("hello", "你好"))
        self.assertIsNone(captions.apply({"type": "response.done"}))

    def test_snapshot_deltas_do_not_repeat_the_sentence(self):
        captions = QwenCaptions()
        captions.apply({"type": "response.text.delta", "item_id": "t", "delta": "你好"})
        captions.apply({"type": "response.text.delta", "item_id": "t", "delta": "你好世界"})
        self.assertEqual(captions.visible()[1], "你好世界")

    def test_audio_transcript_is_not_appended_after_text(self):
        captions = QwenCaptions()
        captions.apply({"type": "response.text.delta", "item_id": "t", "delta": "你好"})
        captions.apply({"type": "response.audio_transcript.delta", "item_id": "t", "delta": "你好"})
        self.assertEqual(captions.visible()[1], "你好")

    def test_a_new_item_replaces_the_previous_sentence(self):
        captions = QwenCaptions()
        captions.apply({"type": "response.text.delta", "item_id": "a", "delta": "上一句。"})
        captions.apply({"type": "response.text.delta", "item_id": "b", "delta": "下一句"})
        self.assertEqual(captions.visible()[1], "下一句")

    def test_completed_transcript_replaces_the_partial_source(self):
        captions = QwenCaptions()
        captions.apply(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "item_id": "src",
                "delta": "hel",
            }
        )
        captions.apply(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "src",
                "transcript": "hello",
            }
        )
        self.assertEqual(captions.visible()[0], "hello")


if __name__ == "__main__":
    unittest.main()
