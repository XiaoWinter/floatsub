import array
import io
import struct
import wave


def pcm_rms(raw: bytes, sample_width: int) -> float:
    if not raw or sample_width not in (2, 4):
        return 0.0
    if sample_width == 4:
        samples = array.array("f")
        usable = len(raw) - (len(raw) % 4)
        samples.frombytes(raw[:usable])
        if not samples:
            return 0.0
        total = 0.0
        for value in samples:
            total += value * value
        return (total / len(samples)) ** 0.5
    samples = array.array("h")
    usable = len(raw) - (len(raw) % 2)
    samples.frombytes(raw[:usable])
    if not samples:
        return 0.0
    total = 0.0
    for value in samples:
        scaled = value / 32768.0
        total += scaled * scaled
    return (total / len(samples)) ** 0.5


def pcm_to_wav(raw: bytes, sample_rate: int, channels: int, sample_width: int) -> bytes:
    """把采集到的 PCM 收成单声道 16 kHz 16-bit WAV，方便送给转写接口。"""
    mono = _mono_int16(raw, channels, sample_width)
    rate_in = sample_rate if sample_rate > 0 else 48000
    step = max(1, round(rate_in / 16000))
    down = mono[::step] if step > 1 else mono
    if not down:
        down = array.array("h", [0])
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000 if step > 1 or rate_in == 16000 else rate_in)
        handle.writeframes(down.tobytes())
    return buffer.getvalue()


class Pcm16kStream:
    """把采集到的 PCM 收成 16 kHz 单声道 16-bit，每 100 毫秒一块。"""

    FRAME = 3200

    def __init__(self):
        self._held = array.array("h")
        self._phase = 0
        self._step = 1
        self._out = bytearray()

    def feed(self, raw: bytes, sample_rate: int, channels: int, sample_width: int) -> list[bytes]:
        mono = _mono_int16(raw, channels, sample_width)
        if not mono:
            return []
        rate = sample_rate if sample_rate > 0 else 48000
        step = max(1, round(rate / 16000))
        if step != self._step:
            self._step = step
            self._phase = 0
            self._held = array.array("h")
        self._held.extend(mono)
        while self._phase < len(self._held):
            self._out += struct.pack("<h", self._held[self._phase])
            self._phase += self._step
        overshoot = self._phase - len(self._held)
        self._held = array.array("h")
        self._phase = overshoot
        frames = []
        while len(self._out) >= self.FRAME:
            frames.append(bytes(self._out[: self.FRAME]))
            del self._out[: self.FRAME]
        return frames


def _mono_int16(raw: bytes, channels: int, sample_width: int) -> array.array:
    channels = channels if channels > 0 else 1
    if sample_width == 4:
        floats = array.array("f")
        usable = len(raw) - (len(raw) % (4 * channels))
        floats.frombytes(raw[:usable])
        frames = len(floats) // channels
        mono = array.array("h")
        for index in range(frames):
            base = index * channels
            mixed = sum(floats[base + channel] for channel in range(channels)) / channels
            mixed = max(-1.0, min(1.0, mixed))
            mono.append(int(mixed * 32767))
        return mono
    samples = array.array("h")
    usable = len(raw) - (len(raw) % (2 * channels))
    samples.frombytes(raw[:usable])
    if channels == 1:
        return samples
    frames = len(samples) // channels
    mono = array.array("h")
    for index in range(frames):
        base = index * channels
        mixed = sum(samples[base + channel] for channel in range(channels)) // channels
        mono.append(mixed)
    return mono
