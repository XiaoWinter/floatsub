"""上海话不走实时同传。同传会把吴语听成普通话。先按吴语识别，再按意思翻译。"""

import asyncio
import base64
import json
import queue
import threading

from floatsub.caption_text import merge_text
from floatsub.config import settings
from floatsub.engines import CaptionError
from floatsub.languages import INPUT_LANGUAGES, OUTPUT_LANGUAGES, find_language, translate_prompt
from floatsub.qwen_live import _store, realtime_url

ASR_MODEL = "qwen3-asr-flash-realtime"
TEXT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash")
_CORPUS = "上海话。侬好，阿拉，晓得，勿要，覅，今朝，明朝，哪能，谢谢侬。"


def ready() -> str:
    if not settings.qwen_api_key:
        return "上海话要用千问来听。把 DASHSCOPE_API_KEY 填进 .env。"
    if not settings.gemini_api_key:
        return "上海话译成文字要用 Gemini。把 GEMINI_API_KEY 填进 .env。"
    return ""


def asr_session() -> dict:
    """千问识别里，zh 包含吴语。语料用来把声音往上海话上靠。"""
    return {
        "type": "session.update",
        "session": {
            "modalities": ["text"],
            "input_audio_format": "pcm",
            "sample_rate": 16000,
            "input_audio_transcription": {
                "language": "zh",
                "corpus": {"text": _CORPUS},
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.2,
                "silence_duration_ms": 800,
            },
        },
    }


def translation_prompt(text: str, target_code: str) -> str:
    source = find_language(INPUT_LANGUAGES, "wuu")
    target = _output_language(target_code)
    return translate_prompt(text, source, target)


def _output_language(target_code: str):
    code = (target_code or "").lower()
    if code.startswith("en"):
        key = "en"
    elif code.startswith("ja"):
        key = "ja"
    elif code.startswith("ko"):
        key = "ko"
    else:
        key = "zh"
    return find_language(OUTPUT_LANGUAGES, key)


class ShanghaiTranscript:
    """一句上海话的识别结果。说完才交给翻译。"""

    def __init__(self):
        self.text = ""
        self.item = ""

    def apply(self, event: dict) -> tuple[str, bool] | None:
        kind = str(event.get("type") or "")
        if "input_audio_transcription" not in kind:
            return None
        item = str(event.get("item_id") or self.item)
        if item and item != self.item:
            self.item = item
            self.text = ""
        piece = str(event.get("transcript") or event.get("text") or event.get("delta") or event.get("stash") or "")
        if not piece:
            return None
        finished = kind.endswith("completed") or kind.endswith("done")
        if finished or piece.startswith(self.text):
            self.text = piece
        else:
            self.text = merge_text(self.text, piece)
        shown = self.text.strip()
        if not shown:
            return None
        return shown, finished


def translate_text(text: str, target_code: str, generate=None) -> str:
    """一个模型忙就换下一个。3.6 高峰时会直接 503。"""
    prompt = translation_prompt(text, target_code)
    if generate is None:
        generate = _generate
    last = None
    for model in TEXT_MODELS:
        try:
            written = (generate(model, prompt) or "").strip()
        except Exception as exc:
            last = exc
            if _busy(exc):
                continue
            raise
        if written:
            return written
    if last is not None:
        raise last
    return ""


def _generate(model: str, prompt: str) -> str:
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    return getattr(response, "text", None) or ""


def _busy(exc: Exception) -> bool:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in (429, 503):
        return True
    text = str(exc).lower()
    return "503" in text or "unavailable" in text or "429" in text or "high demand" in text


def run_live(
    pcm_queue: queue.Queue,
    stop,
    inbox: queue.Queue,
    target_code,
    *,
    problem,
    save_enabled,
    app_name: str,
    pid: int,
) -> str:
    try:
        return asyncio.run(
            _session(
                pcm_queue,
                stop,
                inbox,
                target_code,
                problem=problem,
                save_enabled=save_enabled,
                app_name=app_name,
                pid=pid,
            )
        )
    except CaptionError:
        raise
    except Exception as exc:
        raise CaptionError(_failure(exc)) from exc


async def _session(pcm_queue, stop, inbox, target_code, *, problem, save_enabled, app_name, pid) -> str:
    import websockets

    code = target_code() or "zh"
    url = realtime_url(settings.qwen_base_url, ASR_MODEL)
    heard = ShanghaiTranscript()
    translated = ""
    audio = bytearray()
    audio_lock = threading.Lock()
    recorder = None
    save_broken = False
    reason = "stop"
    headers = {"Authorization": f"Bearer {settings.qwen_api_key}"}
    async with websockets.connect(url, additional_headers=headers, open_timeout=20) as ws:
        await _expect(ws, "session.created")
        await ws.send(json.dumps(asr_session()))
        await _expect(ws, "session.updated")
        sender = asyncio.create_task(
            _send(ws, pcm_queue, stop, target_code, code, problem, audio, audio_lock)
        )
        try:
            while not stop.is_set():
                if problem():
                    inbox.put(("error", problem()))
                    break
                if target_code() != code:
                    reason = "retarget"
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    if stop.is_set():
                        break
                    if target_code() != code:
                        reason = "retarget"
                        break
                    raise
                event = json.loads(raw)
                trouble = _event_error(event)
                if trouble:
                    raise CaptionError(trouble)
                if event.get("type") == "session.finished":
                    break
                heard_text = heard.apply(event)
                if heard_text is None:
                    continue
                text, finished = heard_text
                inbox.put(("live", "", text))
                if not finished or text == translated:
                    continue
                translated = text
                try:
                    written = await asyncio.to_thread(translate_text, text, code)
                except Exception as exc:
                    inbox.put(("error", _translation_failure(exc)))
                    continue
                if written:
                    recorder, save_broken = _store(
                        (text, written),
                        audio,
                        audio_lock,
                        inbox,
                        save_enabled,
                        app_name,
                        pid,
                        recorder,
                        save_broken,
                    )
        finally:
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            try:
                await ws.send(json.dumps({"type": "session.finish"}))
            except Exception:
                pass
    return reason


async def _expect(ws, kind: str) -> None:
    for _ in range(20):
        raw = await asyncio.wait_for(ws.recv(), timeout=20)
        event = json.loads(raw)
        trouble = _event_error(event)
        if trouble:
            raise CaptionError(trouble)
        if event.get("type") == kind:
            return
    raise CaptionError("上海话识别没有准备好。")


async def _send(ws, pcm_queue, stop, target_code, code, problem, audio, audio_lock):
    try:
        while not stop.is_set():
            if problem() or target_code() != code:
                return
            try:
                frame = await asyncio.to_thread(pcm_queue.get, True, 0.2)
            except queue.Empty:
                continue
            with audio_lock:
                if len(audio) < 16000 * 2 * 30:
                    audio.extend(frame)
                else:
                    del audio[: len(frame)]
                    audio.extend(frame)
            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(frame).decode("ascii"),
                    }
                )
            )
    except Exception:
        if stop.is_set() or target_code() != code:
            return
        raise


def _event_error(event: dict) -> str:
    if event.get("type") != "error" and not event.get("error"):
        return ""
    error = event.get("error")
    if isinstance(error, dict):
        text = str(error.get("message") or error.get("code") or "")
    else:
        text = str(event.get("message") or error or "")
    return _failure_text(text)


def _failure_text(text: str) -> str:
    if "InvalidApiKey" in text or "invalid_api_key" in text.lower():
        return "千问 Key 不可用。检查 .env 里的 DASHSCOPE_API_KEY。"
    if "Throttl" in text or "429" in text:
        return "千问这会儿请求太多，稍等几秒。"
    return f"上海话识别中断了。{text}" if text else "上海话识别中断了。"


def _translation_failure(exc: Exception) -> str:
    if _busy(exc):
        return "Gemini 这会儿忙，这一句没译成。后面的话会继续试。"
    return _failure(exc)


def _failure(exc: Exception) -> str:
    text = str(exc).strip()
    if "401" in text or "403" in text or "API key" in text or "API_KEY" in text:
        return "翻译用的 Gemini Key 不可用。检查 .env 里的 GEMINI_API_KEY。"
    if text:
        return f"上海话翻译中断了。{text}"
    return "上海话翻译中断了。"
