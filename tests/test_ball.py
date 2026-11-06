import unittest

from floatsub.glass import disc_bgra


def _pixel(raw: bytes, size: int, x: int, y: int) -> tuple[int, int, int, int]:
    offset = (y * size + x) * 4
    blue, green, red, alpha = raw[offset : offset + 4]
    if not alpha:
        return (0, 0, 0, 0)
    return (red * 255 // alpha, green * 255 // alpha, blue * 255 // alpha, alpha)


class BallTests(unittest.TestCase):
    def test_disc_is_a_dark_circle_with_a_character(self):
        size = 52
        raw = disc_bgra(size, False)
        self.assertEqual(_pixel(raw, size, 0, 0)[3], 0)
        side = _pixel(raw, size, 8, 26)
        self.assertGreater(side[0], side[2] + 8)
        self.assertEqual(side[3], 255)
        ink = sum(1 for y in range(size) for x in range(size) if _pixel(raw, size, x, y)[0] > 220)
        self.assertGreater(ink, 12)

    def test_listening_ring_turns_orange(self):
        idle = _pixel(disc_bgra(52, False), 52, 26, 1)
        live = _pixel(disc_bgra(52, True), 52, 26, 1)
        self.assertGreater(idle[0], idle[2])
        self.assertGreater(live[0], live[1] + 20)


if __name__ == "__main__":
    unittest.main()
