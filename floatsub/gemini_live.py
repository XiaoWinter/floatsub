"""把声音流送进 Gemini 实时翻译，原文和译文都用它返回的转写。"""

import asyncio
import queue
import threading

from floatsub.caption_text import merge_text
from floatsub.config import settings
from floatsub.engines import CaptionError
from floatsub.pcm import pcm_to_wav
from floatsub.records import RecordSession

_AUDIO_CAP = 16000 * 2 * 30


class LiveCaptions:
    """拼一段正在说的话。译文结束，或这一轮结束时，交出一整句。"""

    def __init__(self):
        self.source = ""
        self.target = ""
        self.interim = ""

    def add_interim(self, text: str) -> None:
        self.interim = (text or "").strip()

    def add_source(self, text: str) -> None:
        if text:
            self.interim = ""
            self.source = merge_text(self.source, text)

    def add_target(self, text: str, finished: bool) -> tuple[str, str] | None:
        if text:
            self.target = merge_text(self.target, text)
        if not finished:
            return None
        return self._commit()

    def end_turn(self) -> tuple[str, str] | None:
        if not (self.source.strip() or self.target.strip()):
            return None
        return self._commit()

    def visible(self) -> tuple[str, str]:
        source = self.source.strip() or self.interim
        return source, self.target.strip()

    def _commit(self) -> tuple[str, str] | None:
        pair = (self.source.strip(), self.target.strip())
        self.source = ""
        self.target = ""
        self.interim = ""
        if not any(pair):
            return None
        return pair


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
        raise CaptionError(_live_message(exc)) from exc


async def _session(
    pcm_queue,
    stop,
    inbox,
    target_code,
    *,
    problem,
    save_enabled,
    app_name,
    pid,
) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise CaptionError("没有安装 google-genai。") from exc

    code = target_code() or "zh-Hans"
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(api_version="v1beta"),
    )
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        translation_config=types.TranslationConfig(
            target_language_code=code,
            echo_target_language=True,
        ),
    )
    captions = LiveCaptions()
    audio = bytearray()
    audio_lock = threading.Lock()
    recorder = None
    save_broken = False
    reason = "stop"

    async with client.aio.live.connect(model=settings.gemini_live_model, config=config) as session:
        sender = asyncio.create_task(
            _send(session, pcm_queue, stop, target_code, code, problem, audio, audio_lock)
        )
        try:
            while not stop.is_set():
                if problem():
                    inbox.put(("error", problem()))
                    break
                if target_code() != code:
                    reason = "retarget"
                    break
                saw_message = False
                try:
                    async for message in session.receive():
                        saw_message = True
                        if getattr(message, "go_away", None):
                            reason = "reconnect"
                            break
                        pair = _apply(captions, message)
                        source, target = captions.visible()
                        if source or target:
                            inbox.put(("live", target, source))
                        if pair is not None:
                            recorder, save_broken = _store(
                                pair,
                                audio,
                                audio_lock,
                                inbox,
                                save_enabled,
                                app_name,
                                pid,
                                recorder,
                                save_broken,
                            )
                        if target_code() != code:
                            reason = "retarget"
                            break
                except Exception:
                    if stop.is_set():
                        break
                    if target_code() != code:
                        reason = "retarget"
                        break
                    raise
                if reason in {"retarget", "reconnect"} or not saw_message:
                    break
                if stop.is_set() or target_code() != code:
                    if target_code() != code:
                        reason = "retarget"
                    break
        finally:
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
    return reason


async def _send(session, pcm_queue, stop, target_code, code, problem, audio, audio_lock):
    from google.genai import types

    try:
        while not stop.is_set():
            if problem() or target_code() != code:
                return
            try:
                frame = await asyncio.to_thread(pcm_queue.get, True, 0.2)
            except queue.Empty:
                continue
            with audio_lock:
                if len(audio) < _AUDIO_CAP:
                    audio.extend(frame)
                else:
                    del audio[: len(frame)]
                    audio.extend(frame)
            await session.send_realtime_input(
                audio=types.Blob(data=frame, mime_type="audio/pcm;rate=16000")
            )
        try:
            await session.send_realtime_input(audio_stream_end=True)
        except Exception:
            pass
    finally:
        try:
            await session.close()
        except Exception:
            pass


def _apply(captions: LiveCaptions, message) -> tuple[str, str] | None:
    content = getattr(message, "server_content", None)
    if content is None:
        return None
    interim = getattr(content, "interim_input_transcription", None)
    if interim is not None and getattr(interim, "text", None):
        captions.add_interim(interim.text)
    incoming = getattr(content, "input_transcription", None)
    if incoming is not None and getattr(incoming, "text", None):
        captions.add_source(incoming.text)
    outgoing = getattr(content, "output_transcription", None)
    pair = None
    if outgoing is not None:
        pair = captions.add_target(getattr(outgoing, "text", None) or "", bool(getattr(outgoing, "finished", False)))
    if pair is None and getattr(content, "turn_complete", False):
        pair = captions.end_turn()
    return pair


def _store(pair, audio, audio_lock, inbox, save_enabled, app_name, pid, recorder, save_broken):
    source, target = pair
    inbox.put(("caption", target, source))
    if not save_enabled() or save_broken:
        with audio_lock:
            audio.clear()
        return recorder, save_broken
    with audio_lock:
        raw = bytes(audio)
        audio.clear()
    if not raw:
        return recorder, save_broken
    try:
        if recorder is None:
            recorder = RecordSession.open(app_name, "gemini", pid=pid)
            inbox.put(("recording", recorder.directory.name))
        recorder.add(pcm_to_wav(raw, 16000, 1, 2), source, target)
    except OSError as exc:
        save_broken = True
        inbox.put(("error", f"没能保存录音。{exc}"))
    return recorder, save_broken


def _live_message(exc: Exception) -> str:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in (401, 403):
        return "Gemini Key 不可用。检查 .env 里的 GEMINI_API_KEY。"
    if status == 429:
        return "Gemini 这会儿请求太多，稍等几秒。"
    if status == 503:
        return "Gemini 这会儿忙，稍等几秒。"
    text = str(exc).strip()
    if text:
        return f"Gemini 实时翻译中断了。{text}"
    return "Gemini 实时翻译中断了。"
