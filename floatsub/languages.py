"""听到的语言和译出的语言。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    id: str
    label: str
    gemini: str
    qwen: str
    written: str
    live: str


INPUT_LANGUAGES = (
    Language("ja", "日语", "ja-JP", "ja", "日语", "ja"),
    Language("en", "英语", "en-US", "en", "英语", "en"),
    Language("ko", "韩语", "ko-KR", "ko", "韩语", "ko"),
    Language("zh", "中文", "zh-CN", "zh", "简体中文", "zh-Hans"),
)

OUTPUT_LANGUAGES = INPUT_LANGUAGES


def find_language(choices: tuple[Language, ...], key: str) -> Language | None:
    wanted = (key or "").strip()
    if not wanted:
        return None
    for lang in choices:
        if lang.id == wanted or lang.label == wanted:
            return lang
    return None
