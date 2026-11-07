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


class CrawlSheet:
    """字幕按固定速度上移。停顿补空行，多出来的句子排在下面。"""

    def __init__(self, view_lines: int = 3):
        self.view_lines = view_lines
        self.lines: list[str] = []
        self.scroll = 0.0
        self.ready = False

    def reset(self) -> None:
        self.lines.clear()
        self.scroll = 0.0
        self.ready = False

    def append_rows(self, rows: list[tuple[str, str]]) -> None:
        fresh = [(left, right) for left, right in rows if left or right]
        if not fresh:
            return
        if not self.ready:
            self.lines.extend([""] * max(0, self.view_lines - 1))
            self.ready = True
        self.lines.extend(fresh)

    def append_lines(self, lines: list[str]) -> None:
        fresh = [line for line in lines if line]
        if not fresh:
            return
        if not self.ready:
            self.lines.extend([""] * max(0, self.view_lines - 1))
            self.ready = True
        self.lines.extend(fresh)

    def tick(self, line_delta: float) -> None:
        if not self.ready or line_delta <= 0:
            return
        self.follow(self.scroll + line_delta)

    def follow(self, scroll: float) -> None:
        if not self.ready:
            return
        self.scroll = max(0.0, scroll)
        while self.scroll + self.view_lines > len(self.lines):
            self.lines.append("")


def zip_lines(left: list[str], right: list[str]) -> list[tuple[str, str]]:
    """同一句的译文和原文并成同一行。短的那一边用空行补齐。"""
    count = max(len(left), len(right))
    rows = []
    for index in range(count):
        rows.append((left[index] if index < len(left) else "", right[index] if index < len(right) else ""))
    return rows


def _join_paragraph(left: str, right: str) -> str:
    """新的一句接在最后一段后面。中文直接接上，英文词之间补一个空格。"""
    if not left:
        return right
    if not right:
        return left
    if left[-1].isspace() or right[0].isspace():
        return left + right
    if ord(left[-1]) < 128 and ord(right[0]) < 128:
        return left + " " + right
    return left + right


class SentenceLog:
    """整段译文都留下。没说完的半句先不放出来。"""

    def __init__(self):
        self.transcript = ""
        self.utterance = ""
        self.taken = 0

    def reset(self) -> None:
        self.transcript = ""
        self.utterance = ""
        self.taken = 0

    def push(self, text: str, closed: bool = False) -> str:
        text = (text or "").replace("\r", "").strip()
        if not text:
            return ""
        self._follow(text)
        end = len(self.utterance) if closed else _break_end(self.utterance)
        if end <= self.taken:
            if closed:
                self.utterance = ""
                self.taken = 0
            return ""
        piece = self.utterance[self.taken : end].strip()
        self.taken = end
        if closed:
            self.utterance = ""
            self.taken = 0
        if not piece:
            return ""
        before = self.transcript
        self.transcript = _join_paragraph(before, piece)
        return self.transcript[len(before) :]

    def _follow(self, text: str) -> None:
        if not self.utterance or text.startswith(self.utterance):
            self.utterance = text
            return
        if self.utterance.startswith(text):
            self.utterance = text
            self.taken = min(self.taken, len(text))
            return
        kept = self.utterance[: self.taken]
        if kept and text.startswith(kept):
            self.utterance = text
            return
        self.utterance = text
        self.taken = 0


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
