"""把声音流送进千问实时翻译。只收文字，不收译出的声音。"""

import asyncio
import base64
import json
import queue
import threading

from floatsub.caption_text import merge_text
from floatsub.config import settings
from floatsub.engines import CaptionError
from floatsub.pcm import pcm_to_wav
from floatsub.records import RecordSession

_AUDIO_CAP = 16000 * 2 * 30


class QwenCaptions:
    """按事件把原文和译文拼成一句。"""

    def __init__(self):
        self.sources: dict[str, str] = {}
        self.source_id = ""
        self.targets: dict[str, str] = {}
        self.target_id = ""
        self.saw_text = False

    def apply(self, event: dict) -> tuple[str, str] | None:
        kind = event.get("type") or ""
        if kind == "conversation.item.input_audio_transcription.delta":
            item = str(event.get("item_id") or "")
            self.source_id = item or self.source_id
            piece = event.get("delta") or event.get("text") or ""
            if piece:
                self.sources[item] = merge_text(self.sources.get(item, ""), str(piece))
            return None
        if kind == "conversation.item.input_audio_transcription.completed":
            item = str(event.get("item_id") or "")
            self.source_id = item or self.source_id
            transcript = event.get("transcript") or event.get("text") or ""
            if transcript:
                self.sources[item] = str(transcript)
            return None
        if kind in {"response.text.delta", "response.text.text"}:
            self.saw_text = True
            self._grow_target(event)
            return None
        if kind == "response.audio_transcript.delta":
            if self.saw_text:
                return None
            self._grow_target(event)
            return None
        if kind == "response.text.done":
            full = event.get("text") or ""
            item = str(event.get("item_id") or self.target_id)
            if full:
                self.target_id = item or self.target_id
                self.targets[self.target_id] = str(full)
            return self._commit()
        if kind in {"response.done", "response.audio_transcript.done"}:
            return self._commit()
        return None

    def _grow_target(self, event: dict) -> None:
        item = str(event.get("item_id") or "")
        if item:
            self.target_id = item
        piece = event.get("delta") or event.get("text") or ""
        if not piece:
            return
        key = self.target_id
        self.targets[key] = merge_text(self.targets.get(key, ""), str(piece))

    def visible(self) -> tuple[str, str]:
        return self.sources.get(self.source_id, "").strip(), self.targets.get(self.target_id, "").strip()

    def _commit(self) -> tuple[str, str] | None:
        pair = self.visible()
        self.targets.pop(self.target_id, None)
        self.target_id = ""
        if self.source_id:
            self.sources.pop(self.source_id, None)
            self.source_id = ""
        if not any(pair):
            return None
        return pair


def session_update(language: str) -> dict:
    """只要文字。这个模型不认旧的默认音色 Chelsie，显式换成 Tina。"""
    return {
        "type": "session.update",
        "session": {
            "output_modalities": ["text"],
            "voice": "Tina",
            "translation": {"language": language or "zh"},
        },
    }


def realtime_url(base_url: str, model: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    if root.endswith("/api/v1"):
        root = root[: -len("/api/v1")]
    root = root.replace("https://", "wss://").replace("http://", "ws://")
    return f"{root}/api-ws/v1/realtime?model={model}"


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
    url = realtime_url(settings.qwen_base_url, settings.qwen_live_model)
    captions = QwenCaptions()
    audio = bytearray()
    audio_lock = threading.Lock()
    recorder = None
    save_broken = False
    reason = "stop"
    headers = {"Authorization": f"Bearer {settings.qwen_api_key}"}
    async with websockets.connect(url, additional_headers=headers, open_timeout=20) as ws:
        await _expect(ws, "session.created")
        await ws.send(json.dumps(session_update(code)))
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
                pair = captions.apply(event)
                source, target = captions.visible()
                if source or target:
                    inbox.put(("live", target, source))
                if pair is not None:
                    recorder, save_broken = _store(
                        pair, audio, audio_lock, inbox, save_enabled, app_name, pid, recorder, save_broken
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
    raise CaptionError("千问实时翻译没有准备好。")


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
                if len(audio) < _AUDIO_CAP:
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
            recorder = RecordSession.open(app_name, "qwen", pid=pid)
            inbox.put(("recording", recorder.directory.name))
        recorder.add(pcm_to_wav(raw, 16000, 1, 2), source, target)
    except OSError as exc:
        save_broken = True
        inbox.put(("error", f"没能保存录音。{exc}"))
    return recorder, save_broken


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
    return f"千问实时翻译中断了。{text}" if text else "千问实时翻译中断了。"


def _failure(exc: Exception) -> str:
    text = str(exc).strip()
    if "InvalidApiKey" in text or "401" in text or "403" in text:
        return "千问 Key 不可用。检查 .env 里的 DASHSCOPE_API_KEY。"
    if text:
        return f"千问实时翻译中断了。{text}"
    return "千问实时翻译中断了。"
