"""按进程抓取它正在播放的声音。

Windows 10 的进程环回只包含这个进程和它的子进程，不会把整台电脑的声音混进来。
"""

import ctypes
import queue
import threading
import time
from ctypes import (
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_uint32,
    c_uint64,
    c_void_p,
    cast,
    sizeof,
    string_at,
)
from ctypes.wintypes import BYTE, DWORD, ULONG, WORD

from comtypes import COMMETHOD, COMObject, GUID, HRESULT, IUnknown

from pycaw.api.audioclient import IAudioClient
from pycaw.api.audioclient.depend import WAVEFORMATEX

from floatsub.pcm import Pcm16kStream, pcm_rms, pcm_to_wav
from floatsub.quiet import QUIET_CHOICES, quiet_message

VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_PCM = 1
VT_BLOB = 65
_SOUND_RMS = 0.012


class AudioCaptureError(RuntimeError):
    pass


class AUDIOCLIENT_ACTIVATION_PARAMS(Structure):
    _fields_ = [
        ("ActivationType", DWORD),
        ("TargetProcessId", DWORD),
        ("ProcessLoopbackMode", DWORD),
    ]


class PROPVARIANT(Structure):
    _fields_ = [
        ("vt", WORD),
        ("wReserved1", WORD),
        ("wReserved2", WORD),
        ("wReserved3", WORD),
        ("blobSize", ULONG),
        ("blobData", c_void_p),
    ]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
    _methods_ = (
        COMMETHOD(
            [],
            HRESULT,
            "GetBuffer",
            (["out"], POINTER(POINTER(BYTE)), "ppData"),
            (["out"], POINTER(c_uint32), "pNumFramesToRead"),
            (["out"], POINTER(DWORD), "pdwFlags"),
            (["out"], POINTER(c_uint64), "pu64DevicePosition"),
            (["out"], POINTER(c_uint64), "pu64QPCPosition"),
        ),
        COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint32, "NumFramesRead")),
        COMMETHOD(
            [],
            HRESULT,
            "GetNextPacketSize",
            (["out"], POINTER(c_uint32), "pNumFramesInNextPacket"),
        ),
    )


class IActivateAudioInterfaceAsyncOperation(IUnknown):
    _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
    _methods_ = (
        COMMETHOD(
            [],
            HRESULT,
            "GetActivateResult",
            (["out"], POINTER(HRESULT), "activateResult"),
            (["out"], POINTER(POINTER(IUnknown)), "activatedInterface"),
        ),
    )


class IActivateAudioInterfaceCompletionHandler(IUnknown):
    _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
    _methods_ = (
        COMMETHOD(
            [],
            HRESULT,
            "ActivateCompleted",
            (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "activateOperation"),
        ),
    )


class IAgileObject(IUnknown):
    _iid_ = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
    _methods_ = ()


class _ActivationHandler(COMObject):
    _com_interfaces_ = (IActivateAudioInterfaceCompletionHandler, IAgileObject)

    def __init__(self):
        super().__init__()
        self.done = threading.Event()
        self.client = None
        self.error = ""

    def ActivateCompleted(self, operation):
        try:
            activate_result, unknown = operation.GetActivateResult()
            code = int(activate_result)
            if code < 0 or unknown is None:
                self.error = f"打开这个应用的声音失败（{code & 0xFFFFFFFF:08X}）。"
            else:
                self.client = unknown.QueryInterface(IAudioClient)
        except Exception as exc:
            self.error = f"打开这个应用的声音失败。{exc}"
        self.done.set()
        return 0


_activate = WinDLL("mmdevapi").ActivateAudioInterfaceAsync
_activate.restype = HRESULT
_activate.argtypes = [
    ctypes.c_wchar_p,
    POINTER(GUID),
    POINTER(PROPVARIANT),
    POINTER(IActivateAudioInterfaceCompletionHandler),
    POINTER(POINTER(IActivateAudioInterfaceAsyncOperation)),
]


def _pcm_format(tag: int, rate: int, channels: int, bits: int) -> WAVEFORMATEX:
    fmt = WAVEFORMATEX()
    fmt.wFormatTag = tag
    fmt.nChannels = channels
    fmt.nSamplesPerSec = rate
    fmt.wBitsPerSample = bits
    fmt.nBlockAlign = channels * bits // 8
    fmt.nAvgBytesPerSec = rate * fmt.nBlockAlign
    fmt.cbSize = 0
    return fmt


def _activate_client(pid: int):
    import comtypes

    comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    params = AUDIOCLIENT_ACTIVATION_PARAMS()
    params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK
    params.TargetProcessId = pid
    params.ProcessLoopbackMode = PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE
    variant = PROPVARIANT()
    variant.vt = VT_BLOB
    variant.blobSize = sizeof(params)
    variant.blobData = cast(byref(params), c_void_p)
    handler = _ActivationHandler()
    operation = POINTER(IActivateAudioInterfaceAsyncOperation)()
    _activate(
        VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
        byref(IAudioClient._iid_),
        byref(variant),
        handler,
        byref(operation),
    )
    if not handler.done.wait(8):
        raise AudioCaptureError("等待系统打开声音超时。")
    if handler.client is None:
        raise AudioCaptureError(handler.error or "打开这个应用的声音失败。")
    # 参数必须活到回调结束。
    handler._kept = (params, variant)
    return handler.client


def _start_client(client):
    flags = (
        AUDCLNT_STREAMFLAGS_LOOPBACK
        | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM
        | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY
    )
    formats = (
        _pcm_format(WAVE_FORMAT_IEEE_FLOAT, 48000, 2, 32),
        _pcm_format(WAVE_FORMAT_PCM, 48000, 2, 16),
    )
    last_error = None
    chosen = None
    for fmt in formats:
        try:
            client.Initialize(0, flags, 10_000_000, 0, byref(fmt), None)
            chosen = fmt
            break
        except Exception as exc:
            last_error = exc
    if chosen is None:
        raise AudioCaptureError(f"这个应用的声音格式打不开。{last_error}")
    service = client.GetService(byref(IAudioCaptureClient._iid_))
    capture = service.QueryInterface(IAudioCaptureClient)
    client.Start()
    return capture, chosen


class ProcessCapture:
    def __init__(
        self,
        pid: int,
        chunk_seconds: float,
        *,
        stream: bool = False,
        quiet_after: float = QUIET_CHOICES[0][1],
    ):
        self.pid = pid
        self.chunk_seconds = chunk_seconds
        self.stream = stream
        self.quiet_after = quiet_after
        self.chunks: queue.Queue[bytes] = queue.Queue(maxsize=2)
        self.pcm: queue.Queue[bytes] = queue.Queue(maxsize=20)
        self.packets = 0
        self.error = ""
        self.heard_at = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="floatsub-capture", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _publish_pcm(self, frame: bytes) -> None:
        if self.pcm.full():
            try:
                self.pcm.get_nowait()
            except queue.Empty:
                pass
        try:
            self.pcm.put_nowait(frame)
        except queue.Full:
            pass

    def hear_or_stop(self, raw: bytes, width: int, now: float | None = None) -> str:
        """有声音就重新计时。安静超过当前选项，就该停。"""
        moment = time.monotonic() if now is None else now
        if raw and width and pcm_rms(raw, width) >= _SOUND_RMS:
            self.heard_at = moment
            return ""
        if self.quiet_after > 0 and self.heard_at and moment - self.heard_at >= self.quiet_after:
            return quiet_message(self.quiet_after)
        return ""

    def _publish(self, wav: bytes) -> None:
        if self.chunks.full():
            try:
                self.chunks.get_nowait()
            except queue.Empty:
                pass
        try:
            self.chunks.put_nowait(wav)
        except queue.Full:
            pass

    def _run(self) -> None:
        client = None
        try:
            client = _activate_client(self.pid)
            capture, fmt = _start_client(client)
            width = fmt.wBitsPerSample // 8
            block = fmt.nBlockAlign
            need = int(fmt.nSamplesPerSec * self.chunk_seconds) * block
            pending = bytearray()
            converter = Pcm16kStream() if self.stream else None
            self.heard_at = time.monotonic()
            while not self._stop.is_set():
                frames = capture.GetNextPacketSize()
                if not frames:
                    self.error = self.hear_or_stop(b"", width)
                    if self.error:
                        break
                    self._stop.wait(0.02)
                    continue
                data, count, flags, _pos, _qpc = capture.GetBuffer()
                self.packets += 1
                nbytes = count * block
                if flags & AUDCLNT_BUFFERFLAGS_SILENT or not data:
                    raw = b"\x00" * nbytes
                else:
                    raw = string_at(data, nbytes)
                capture.ReleaseBuffer(count)
                self.error = self.hear_or_stop(raw, width)
                if self.error:
                    break
                if converter is not None:
                    for frame in converter.feed(raw, fmt.nSamplesPerSec, fmt.nChannels, width):
                        self._publish_pcm(frame)
                    continue
                pending.extend(raw)
                while len(pending) >= need:
                    piece = bytes(pending[:need])
                    del pending[:need]
                    if pcm_rms(piece, width) >= _SOUND_RMS:
                        self._publish(pcm_to_wav(piece, fmt.nSamplesPerSec, fmt.nChannels, width))
        except AudioCaptureError as exc:
            self.error = str(exc)
        except Exception as exc:
            self.error = f"抓取声音中断了。{exc}"
        finally:
            if client is not None:
                try:
                    client.Stop()
                except Exception:
                    pass
