"""接口返回的侧页。记下每次到达的时间和间隔，用来看是不是接口在卡。"""

import queue
import time
import tkinter as tk

from floatsub.chrome import BAR, FONT, INK, MUTED

_KEEP_LINES = 240


class TimedInbox(queue.Queue):
    """放入队列时记下时间。界面稍后取走，间隔仍按到达时刻算。"""

    def put(self, item, block=True, timeout=None):
        super().put((time.time(), time.monotonic(), item), block=block, timeout=timeout)


def _added(previous: str, current: str) -> str | None:
    """没变就空着。只是接长了，就留下新增的那一截。"""
    if current == previous:
        return None
    if previous and current.startswith(previous):
        return f"+{current[len(previous):]}"
    return current or "（空）"


def format_event(
    wall: float,
    mono: float,
    previous: float | None,
    kind: str,
    payload: tuple,
    shown: tuple[str, str] = ("", ""),
) -> tuple[str | None, tuple[str, str]]:
    clock = time.strftime("%H:%M:%S", time.localtime(wall))
    millis = int(wall * 1000) % 1000
    gap = ""
    if previous is not None:
        gap = f"  +{max(0, round((mono - previous) * 1000))}ms"
    head = f"{clock}.{millis:03d}{gap}  {kind}"
    if kind in {"live", "caption"} and len(payload) >= 2:
        written = payload[0] or ""
        heard = payload[1] or ""
        translated = _added(shown[0], written)
        source = _added(shown[1], heard)
        if translated is None and source is None:
            if kind == "caption":
                return head + "\n", (written, heard)
            return None, shown
        lines = [head]
        if translated is not None:
            lines.append(f"译 {translated}")
        if source is not None:
            lines.append(f"原 {source}")
        return "\n".join(lines) + "\n", (written, heard)
    if payload:
        return f"{head}  {payload[0]}\n", shown
    return head + "\n", shown


class DebugPanel:
    """贴在字幕右边的记录。关掉时仍在记，打开就能看到刚到的返回。"""

    def __init__(self, root):
        self.open = False
        self._last_mono: float | None = None
        self._shown = ("", "")
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BAR)

        bar = tk.Frame(self.win, bg=BAR)
        bar.pack(fill="x")
        tk.Label(bar, text="接口返回", bg=BAR, fg=INK, font=(FONT, 13)).pack(side="left", padx=12, pady=8)
        clear = tk.Label(bar, text="清空", bg=BAR, fg=MUTED, font=(FONT, 12), cursor="hand2")
        clear.pack(side="right", padx=12)
        clear.bind("<Button-1>", self._clear)

        self.text = tk.Text(
            self.win,
            bg=BAR,
            fg=INK,
            insertbackground=INK,
            font=(FONT, 12),
            wrap="word",
            bd=0,
            padx=12,
            pady=8,
            highlightthickness=0,
        )
        self.text.pack(fill="both", expand=True)
        self.text.insert("end", "只记新出现的字。整段没变就不再贴一遍。\n")

    def toggle(self) -> None:
        self.open = not self.open
        if not self.open:
            self.win.withdraw()

    def place(self, x: int, y: int, height: int, collapsed: bool) -> None:
        if not self.open or collapsed:
            self.win.withdraw()
            return
        self.win.geometry(f"420x{max(160, height)}+{int(x)}+{int(y)}")
        self.win.deiconify()
        self.win.lift()

    def add(self, wall: float, mono: float, kind: str, payload: tuple) -> None:
        if kind not in {"live", "caption", "error"}:
            return
        block, self._shown = format_event(wall, mono, self._last_mono, kind, payload, self._shown)
        if not block:
            return
        self._last_mono = mono
        at_bottom = self.text.yview()[1] > 0.98
        self.text.insert("end", block + "\n")
        extra = int(float(self.text.index("end-1c"))) - _KEEP_LINES
        if extra > 0:
            self.text.delete("1.0", f"{extra + 1}.0")
        if at_bottom:
            self.text.see("end")

    def _clear(self, _event=None):
        self._last_mono = None
        self._shown = ("", "")
        self.text.delete("1.0", "end")
        return "break"
