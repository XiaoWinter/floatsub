"""听到的语言和译出的语言。上海话、粤语只能作为输入。"""

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
    Language("wuu", "上海话", "", "", "上海话", ""),
    Language("yue", "粤语", "yue-HK", "yue", "粤语", ""),
)

OUTPUT_LANGUAGES = tuple(lang for lang in INPUT_LANGUAGES if lang.id in {"ja", "en", "ko", "zh"})


def find_language(choices: tuple[Language, ...], key: str) -> Language | None:
    wanted = (key or "").strip()
    if not wanted:
        return None
    for lang in choices:
        if lang.id == wanted or lang.label == wanted:
            return lang
    return None


def transcribe_hint(language: Language) -> str:
    if language.id == "yue":
        return "只转写听到的粤语，用汉字。不要译成普通话，不要解释。"
    if language.id == "wuu":
        return "只转写听到的上海话，用汉字。不要译成普通话，不要解释。"
    return ""


def translate_prompt(text: str, source: Language, target: Language) -> str:
    note = ""
    if source.id in {"yue", "wuu"}:
        note = f"原文是{source.label}，不要按普通话理解。"
    return (
        f"把下面这段{source.label}译成自然的{target.written}。"
        f"{note}"
        "只输出译文，不要解释，也不要加引号。\n\n"
        f"{text}"
    )
