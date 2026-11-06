"""把一段声音转成字幕。Gemini 和千问都走实时翻译。"""

from floatsub.config import settings


class CaptionError(RuntimeError):
    pass


def make_engine(provider: str):
    name = (provider or settings.provider or "gemini").strip().lower()
    if name == "qwen":
        return QwenEngine()
    return GeminiEngine()


class GeminiEngine:
    label = "Gemini"

    def __init__(self):
        self.api_key = settings.gemini_api_key

    def ready(self) -> str:
        if not self.api_key:
            return "还没有 Gemini Key。把 GEMINI_API_KEY 填进 .env。"
        return ""

    def run_live(self, pcm_queue, stop, inbox, target_code, **kwargs) -> str:
        from floatsub.gemini_live import run_live

        return run_live(pcm_queue, stop, inbox, target_code, **kwargs)


class QwenEngine:
    label = "千问"

    def __init__(self):
        self.api_key = settings.qwen_api_key

    def ready(self) -> str:
        if not self.api_key:
            return "还没有千问 Key。把 DASHSCOPE_API_KEY 填进 .env。"
        return ""

    def run_live(self, pcm_queue, stop, inbox, target_code, **kwargs) -> str:
        from floatsub.qwen_live import run_live

        return run_live(pcm_queue, stop, inbox, target_code, **kwargs)
