"""字幕按上滚显示。字只往当前行末尾加，满一行或一句结束就整行上移。"""

_BREAKS = ("。", "！", "？", "!", "?", "\n", ". ")
_LIMIT = 120


def merge_text(current: str, piece: str) -> str:
    """增量往后接。如果新内容已经包含旧内容，就换成新的整段。"""
    current = current or ""
    piece = piece or ""
    if not piece or piece == current:
        return current
    if not current or piece.startswith(current):
        return piece
    if current.startswith(piece):
        return current
    return current + piece


def latest_line(text: str) -> str:
    """已经说完的句子拿掉，屏幕上只留正在说的这一句。"""
    text = (text or "").replace("\r", "").strip()
    if not text:
        return ""
    end = _break_end(text)
    if end >= len(text):
        end = _break_end(text[: end - 1].rstrip())
    line = text[end:].strip()
    if len(line) > _LIMIT:
        line = line[-_LIMIT:].lstrip()
    return line


def _break_end(text: str) -> int:
    end = 0
    for mark in _BREAKS:
        found = text.rfind(mark)
        if found != -1:
            end = max(end, found + len(mark))
    return end


def _unit(char: str) -> float:
    if char.isspace():
        return 0.0
    return 1.0 if ord(char) > 127 else 0.5


def _weight(text: str) -> float:
    return sum(_unit(char) for char in text)


def _ends_sentence(text: str) -> bool:
    if not text:
        return False
    if text[-1] in "。！？!?\n":
        return True
    return text.endswith(". ")


def _common_prefix(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _take(text: str, room: float) -> tuple[str, str]:
    """取这一行还能放下的字。碰到句末就停，剩下的留给下一行。"""
    weight = 0.0
    index = 0
    size = len(text)
    while index < size:
        char = text[index]
        gain = _unit(char)
        if weight > 0 and (weight >= room or weight + gain > room):
            break
        index += 1
        weight += gain
        if char in "。！？!?\n":
            break
        if char == "." and index < size and text[index] == " ":
            index += 1
            break
    if index == 0 and size:
        index = 1
    return text[:index], text[index:]


class CaptionPager:
    """两行上滚。上面那一行只在下面一行结束时整行消失。"""

    def __init__(self):
        self.upper = ""
        self.lower = ""
        self.tracked = ""
        self.committed = 0

    def reset(self) -> None:
        self.upper = ""
        self.lower = ""
        self.tracked = ""
        self.committed = 0

    def push(self, text: str, line: int, now: float | None = None) -> str:
        del now
        line = max(4, int(line))
        cleaned = (text or "").replace("\r", "").strip()
        if cleaned:
            extra = self._delta(cleaned)
            if extra:
                self._append(extra, line)
        return self._render()

    def tick(self, line: int, now: float) -> str:
        return self.push("", line, now)

    def next_clear_in(self, line: int, now: float) -> float | None:
        del line, now
        return None

    def _delta(self, text: str) -> str:
        if not self.tracked:
            return text
        if text == self.tracked:
            return ""
        if text.startswith(self.tracked):
            return text[len(self.tracked) :]
        if self.tracked.startswith(text):
            return self._shrink(text)
        prefix = self.tracked[: self.committed]
        if self.committed and prefix and text.startswith(prefix):
            self.lower = ""
            self.tracked = prefix
            return text[self.committed :]
        if self.committed == 0 and self.upper and text.startswith(self.upper):
            return self._after_upper(text)
        if self.committed == 0:
            self.lower = ""
            self.tracked = ""
            return text
        resumed = self._resume(text)
        if resumed is not None:
            return resumed
        return self._start_new(text)

    def _shrink(self, text: str) -> str:
        prefix = self.tracked[: self.committed]
        if prefix and not text.startswith(prefix):
            return ""
        self.tracked = text
        self.lower = text[len(prefix) :]
        return ""

    def _after_upper(self, text: str) -> str:
        joined = self.upper + self.lower
        if text.startswith(joined):
            self.tracked = joined
            self.committed = len(self.upper)
            return text[len(joined) :]
        self.lower = ""
        self.tracked = self.upper
        self.committed = len(self.upper)
        return text[len(self.upper) :]

    def _resume(self, text: str) -> str | None:
        """锁定的字被改了一点时，不要把整段再画一遍，只接上新的尾巴。"""
        shared = _common_prefix(self.tracked, text)
        if shared < 4:
            return None
        if self.lower and len(self.lower) >= 2:
            at = text.rfind(self.lower)
            expected = len(self.tracked) - len(self.lower)
            if at >= 0 and (abs(at - expected) <= 4 or text[:at].endswith(self.upper)):
                extra = text[at + len(self.lower) :]
                self.tracked = text[: at + len(self.lower)]
                self.committed = at
                return extra
        if not self.lower and self.upper and text.endswith(self.upper):
            self.tracked = text
            self.committed = len(text)
            return ""
        return None

    def _start_new(self, text: str) -> str:
        if self.lower.strip():
            self._roll()
        else:
            self.lower = ""
        self.tracked = ""
        self.committed = 0
        return text

    def _append(self, delta: str, line: int) -> None:
        rest = delta
        while rest:
            room = line - _weight(self.lower)
            if room <= 0:
                if not self.lower:
                    break
                self._roll()
                continue
            head, rest = _take(rest, room)
            if not head:
                break
            self.lower += head
            self.tracked += head
            if rest or _ends_sentence(self.lower):
                self._roll()

    def _roll(self) -> None:
        shown = self.lower.strip()
        if not shown:
            self.lower = ""
            return
        self.upper = shown
        self.lower = ""
        self.committed = len(self.tracked)

    def _render(self) -> str:
        rows = [row.strip() for row in (self.upper, self.lower) if row.strip()]
        return "\n".join(rows)
