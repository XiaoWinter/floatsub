import array
import unittest
import wave
import io

from floatsub.pcm import Pcm16kStream, pcm_rms, pcm_to_wav


class PcmTests(unittest.TestCase):
    def test_silence_rms_is_near_zero(self):
        raw = array.array("f", [0.0] * 400).tobytes()
        self.assertLess(pcm_rms(raw, 4), 0.001)

    def test_tone_rms_is_audible(self):
        raw = array.array("f", [0.2, -0.2] * 200).tobytes()
        self.assertGreater(pcm_rms(raw, 4), 0.1)

    def test_wav_is_mono_16k(self):
        raw = array.array("f", [0.1, -0.1] * 4800).tobytes()
        wav = pcm_to_wav(raw, 48000, 2, 4)
        with wave.open(io.BytesIO(wav), "rb") as handle:
            self.assertEqual(handle.getnchannels(), 1)
            self.assertEqual(handle.getsampwidth(), 2)
            self.assertEqual(handle.getframerate(), 16000)
            self.assertGreater(handle.getnframes(), 100)

    def test_stream_emits_100ms_frames(self):
        raw = array.array("f", [0.2, -0.2] * 48000).tobytes()
        frames = Pcm16kStream().feed(raw, 48000, 2, 4)
        self.assertEqual(len(frames), 10)
        self.assertTrue(all(len(frame) == 3200 for frame in frames))


if __name__ == "__main__":
    unittest.main()
