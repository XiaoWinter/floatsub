import queue
import threading
import time
import tkinter as tk

from floatsub.caption_text import CaptionPager
from floatsub.debug_feed import DebugPanel, TimedInbox
from floatsub.capture import ProcessCapture
from floatsub.chrome import (
    ACCENT,
    BAR_H,
    EDGE,
    FONT,
    GLASS,
    INK,
    LISTEN_GREEN,
    LISTEN_GREEN_HOVER,
    LISTEN_RED,
    LISTEN_RED_HOVER,
    MUTED,
    Toolbar,
    fold_corner,
)
from floatsub.glass import apply_blur, clear_blur, clear_region, disc_bgra, move_window, place_window, show_layered, window_handle
from floatsub.config import load_state, save_state, settings
from floatsub.engines import CaptionError, make_engine
from floatsub import shanghai
from floatsub.languages import INPUT_LANGUAGES, OUTPUT_LANGUAGES, find_language
from floatsub.quiet import quiet_label, quiet_seconds
from floatsub.sessions import playing_apps

_WIDTH = 1200
_BODY_H = 196
_MIN_W = 1200
_MIN_H = 120
_BALL_SIZE = 52


class Overlay:
    def __init__(self):
        state = load_state()
        self.state = state
        self.targets = []
        self.capture = None
        self.worker = None
        self.stop_listen = threading.Event()
        self.inbox: queue.Queue = TimedInbox()
        self.listening = False
        self.record_dir_name = ""

        self.collapsed = bool(state.get("collapsed"))
        self._x = int(state.get("x", 80) or 80)
        self._y = int(state.get("y", 80) or 80)
        self._width = max(_MIN_W, int(state.get("width") or _WIDTH))
        self._body_h = max(_MIN_H, int(state.get("body_h") or _BODY_H))
        self._moved = False
        self._blur_paused = False
        self._move_job = None
        self._last_flush = 0.0
        self._grabbed = None

        self.root = tk.Tk()
        self.root.title("floatsub")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=GLASS)
        self.root.withdraw()

        self.provider = tk.StringVar(value=_provider_label(state.get("provider") or settings.provider))
        heard = find_language(INPUT_LANGUAGES, state.get("source_lang") or "") or find_language(INPUT_LANGUAGES, "en")
        written = find_language(OUTPUT_LANGUAGES, state.get("target_lang") or "") or find_language(OUTPUT_LANGUAGES, "zh")
        self.languages = (heard, written)
        self.heard_label = tk.StringVar(value=heard.label)
        self.written_label = tk.StringVar(value=written.label)
        self.keep = tk.BooleanVar(value=bool(state.get("save")))
        self.keep_records = bool(self.keep.get())
        self.quiet_label = tk.StringVar(value=quiet_label(int(state.get("quiet") or 30)))
        self.app_label = tk.StringVar(value="选择正在出声的应用")
        self.status = tk.StringVar(value="选一个应用，再开始听。")
        self.translation = tk.StringVar(value="")
        self.source = tk.StringVar(value="")
        self._translation_page = CaptionPager()
        self._source_page = CaptionPager()
        self._caption_job = None

        self.toolbar = Toolbar(
            self.root,
            app_label=self.app_label,
            provider=self.provider,
            heard=self.heard_label,
            written=self.written_label,
            keep=self.keep,
            quiet=self.quiet_label,
            on_keep=self._toggle_keep,
            on_provider=lambda _choice: self._save(),
            on_languages=self._apply_languages,
            on_quiet=self._apply_quiet,
            on_listen=self.toggle,
            on_refresh=self.refresh,
            on_collapse=self._collapse,
            on_close=self.close,
            bind_drag=self._bind_drag,
        )
        self.listen_button = self.toolbar.listen

        self.panel = tk.Frame(self.root, bg=GLASS)
        body = tk.Frame(self.panel, bg=GLASS)
        body.pack(fill="both", expand=True, padx=16, pady=(10, 14))
        self._bind_drag(body)
        self.translation_label = tk.Label(
            body,
            textvariable=self.translation,
            bg=GLASS,
            fg=INK,
            font=(FONT, 22),
            height=2,
            wraplength=self._width - 40,
            justify="left",
            anchor="nw",
        )
        self.translation_label.pack(fill="x")
        self._bind_drag(self.translation_label)
        self.source_label = tk.Label(
            body,
            textvariable=self.source,
            bg=GLASS,
            fg=MUTED,
            font=(FONT, 15),
            height=2,
            wraplength=self._width - 40,
            justify="left",
            anchor="nw",
        )
        self.source_label.pack(fill="x", pady=(18, 0))
        self._bind_drag(self.source_label)
        status_row = tk.Frame(body, bg=GLASS)
        status_row.pack(fill="x", pady=(8, 0))
        self._bind_drag(status_row)
        self.status_label = tk.Label(
            status_row,
            textvariable=self.status,
            bg=GLASS,
            fg=MUTED,
            font=(FONT, 12),
            wraplength=self._width - 88,
            justify="left",
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        self._bind_drag(self.status_label)
        self._copy_status = tk.Label(
            status_row,
            text="复制",
            bg=GLASS,
            fg=INK,
            font=(FONT, 12),
            cursor="hand2",
        )
        self._copy_status.pack(side="right", padx=(8, 0))
        self._copy_status.bind("<Button-1>", self._copy_error)
        self._debug_toggle = tk.Label(
            status_row,
            text="调试",
            bg=GLASS,
            fg=MUTED,
            font=(FONT, 12),
            cursor="hand2",
        )
        self._debug_toggle.pack(side="right", padx=(8, 0))
        self._debug_toggle.bind("<Button-1>", self._toggle_debug)
        self._copy_token = 0
        self._grip = tk.Canvas(self.panel, width=18, height=18, bg=GLASS, highlightthickness=0, bd=0, cursor="size_nw_se")
        self._grip.place(relx=1, rely=1, anchor="se")
        for offset in (4, 8, 12):
            self._grip.create_line(offset, 16, 16, offset, fill=INK, width=1)
        self._grip.bind("<ButtonPress-1>", self._resize_start)
        self._grip.bind("<B1-Motion>", self._resize_move)
        self._grip.bind("<ButtonRelease-1>", self._resize_end)

        self.ball = tk.Toplevel(self.root)
        self.ball.withdraw()
        self.ball.overrideredirect(True)
        self.ball.attributes("-topmost", True)
        self._disc = {}
        self._bind_drag(self.ball, expand_on_click=True)
        self.debug = DebugPanel(self.root)
        self._show_dock(state)

        self.refresh()
        self.root.after(120, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _show_dock(self, state: dict):
        self._place_at(self._x, self._y)

    def _stack_xy(self) -> tuple[int, int]:
        return self._x, self._y

    def _ball_xy(self, x: int, y: int) -> tuple[int, int]:
        fold_x, fold_y = fold_corner(self._width)
        return (
            int(x + fold_x + EDGE / 2 - _BALL_SIZE / 2),
            int(y + fold_y + EDGE / 2 - _BALL_SIZE / 2),
        )

    def _place_at(self, x: int, y: int):
        self._x, self._y = int(x), int(y)
        if self.collapsed:
            self.toolbar.hide()
            self.panel.pack_forget()
            self.root.withdraw()
            bx, by = self._ball_xy(self._x, self._y)
            self._paint_ball(bx, by)
        else:
            self.ball.withdraw()
            self.root.deiconify()
            self.panel.pack(fill="both", expand=True)
            self.toolbar.show(self._x, self._y, self._width)
            self.root.geometry(f"{self._width}x{self._body_h}+{self._x}+{self._y + BAR_H}")
            self._apply_wrap()
            self._glass()
            self._place_debug()

    def _apply_wrap(self):
        width = max(200, self._width - 40)
        self.translation_label.configure(wraplength=width)
        self.source_label.configure(wraplength=width)
        self.status_label.configure(wraplength=max(160, self._width - 88))
        for child in self.translation_label.master.winfo_children():
            if child is self.translation_label:
                continue
            try:
                if child.cget("textvariable"):
                    child.configure(wraplength=width)
            except tk.TclError:
                pass

    def _collapse(self):
        if self.collapsed:
            return
        x, y = self._stack_xy()
        self.collapsed = True
        self._place_at(x, y)
        self._save()

    def _expand(self):
        if not self.collapsed:
            return
        bx, by = self.ball.winfo_x(), self.ball.winfo_y()
        self.collapsed = False
        fold_x, fold_y = fold_corner(self._width)
        x = bx - int(fold_x + EDGE / 2 - _BALL_SIZE / 2)
        y = by - int(fold_y + EDGE / 2 - _BALL_SIZE / 2)
        x, y = self._clamp(x, y, self._width, BAR_H + self._body_h)
        self._place_at(x, y)
        self._save()

    def _glass(self):
        self.root.update_idletasks()
        hwnd = window_handle(self.root)
        apply_blur(hwnd, opacity=32)
        clear_blur(window_handle(self.toolbar.win))
        clear_region(hwnd)

    def _clamp(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = min(max(0, x), max(0, screen_w - width))
        y = min(max(0, y), max(0, screen_h - height))
        return x, y

    def _paint_ball(self, x: int | None = None, y: int | None = None):
        if not self.collapsed and x is None:
            return
        if x is None or y is None:
            x, y = self.ball.winfo_x(), self.ball.winfo_y()
        key = bool(self.listening)
        image = self._disc.get(key)
        if image is None:
            image = disc_bgra(_BALL_SIZE, key)
            self._disc[key] = image
        show_layered(window_handle(self.ball), int(x), int(y), image, _BALL_SIZE)
        self.ball.deiconify()
        self.ball.lift()

    def _bind_drag(self, widget, *, expand_on_click=False):
        widget.bind("<ButtonPress-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)
        if expand_on_click:
            widget.bind("<ButtonRelease-1>", self._ball_release)
        else:
            widget.bind("<ButtonRelease-1>", self._end_drag)

    def _drag_start(self, event):
        origin_x, origin_y = self._stack_xy()
        self._drag_x = event.x_root - origin_x
        self._drag_y = event.y_root - origin_y
        self._press_x = event.x_root
        self._press_y = event.y_root
        self._place_x = origin_x
        self._place_y = origin_y
        self._moved = False
        self._hwnd = window_handle(self.root)
        self._bar_hwnd = window_handle(self.toolbar.win)
        self._ball_hwnd = window_handle(self.ball)
        self._grabbed = event.widget
        event.widget.grab_set()

    def _drag_move(self, event):
        if abs(event.x_root - self._press_x) + abs(event.y_root - self._press_y) <= 6:
            return
        self._moved = True
        self._place_x = event.x_root - self._drag_x
        self._place_y = event.y_root - self._drag_y
        if time.perf_counter() - self._last_flush < 0.008:
            if self._move_job is None:
                self._move_job = self.root.after(8, self._flush_move)
            return
        self._flush_move()

    def _flush_move(self):
        self._move_job = None
        self._last_flush = time.perf_counter()
        x, y = int(self._place_x), int(self._place_y)
        if self.collapsed:
            bx, by = self._ball_xy(x, y)
            move_window(self._ball_hwnd, bx, by)
            return
        if not self._blur_paused:
            clear_blur(self._hwnd)
            self._blur_paused = True
        move_window(self._bar_hwnd, x, y)
        move_window(self._hwnd, x, y + BAR_H)
        self._place_debug(x, y)

    def _end_drag(self, _event=None):
        grabbed = self._grabbed
        if grabbed is not None:
            try:
                grabbed.grab_release()
            except tk.TclError:
                pass
            self._grabbed = None
        if self._move_job is not None:
            self.root.after_cancel(self._move_job)
            self._move_job = None
            self._flush_move()
        if self._moved:
            self._blur_paused = False
            self._place_at(int(self._place_x), int(self._place_y))
        self._save()

    def _resize_start(self, event):
        self._resize_x = event.x_root
        self._resize_y = event.y_root
        self._resize_w = self._width
        self._resize_h = self._body_h
        self._hwnd = window_handle(self.root)
        self._bar_hwnd = window_handle(self.toolbar.win)
        clear_blur(self._hwnd)
        event.widget.grab_set()

    def _resize_move(self, event):
        self._width = max(_MIN_W, self._resize_w + event.x_root - self._resize_x)
        self._body_h = max(_MIN_H, self._resize_h + event.y_root - self._resize_y)
        self.toolbar.layout_edges(self._width)
        place_window(self._bar_hwnd, self._x, self._y, self._width, BAR_H)
        place_window(self._hwnd, self._x, self._y + BAR_H, self._width, self._body_h)

    def _resize_end(self, event):
        try:
            event.widget.grab_release()
        except tk.TclError:
            pass
        self._place_at(self._x, self._y)
        self._save()

    def _ball_release(self, _event):
        self._end_drag()
        if not self._moved:
            self._expand()

    def refresh(self):
        try:
            self.targets = playing_apps()
        except Exception as exc:
            self.status.set(f"读不到正在出声的应用。{exc}")
            return
        labels = [item.label for item in self.targets]
        self.toolbar.set_apps(labels)
        if not labels:
            self.app_label.set("现在没有应用在出声")
            return
        current = self.app_label.get()
        if current not in labels:
            self.app_label.set(labels[0])

    def toggle(self):
        if self.listening:
            self._stop_worker()
            return
        target = self._selected()
        if target is None:
            self.status.set("先让那个应用出声，再点刷新。")
            return
        provider = "qwen" if self.provider.get() == "千问" else "gemini"
        engine = make_engine(provider)
        shanghai_mode = self.languages[0].id == "wuu"
        missing = shanghai.ready() if shanghai_mode else engine.ready()
        if missing:
            self.status.set(missing)
            return
        self._save()
        self.listening = True
        self.record_dir_name = ""
        self._show_listen_button(True)
        self._paint_ball()
        if shanghai_mode:
            self.status.set(f"正在听 {target.name}。按上海话识别，再译成{self.languages[1].label}。")
        elif self.languages[0].id == "yue":
            self.status.set(f"正在听 {target.name}。会自己判断语言，不单独识别粤语。")
        else:
            self.status.set(f"正在听 {target.name}。字幕跟着说话走。")
        self.translation.set("")
        self.source.set("")
        self._translation_page.reset()
        self._source_page.reset()
        self.stop_listen.clear()
        self.worker = threading.Thread(
            target=self._listen_live,
            args=(target.pid, target.name, provider, engine),
            name="floatsub-listen",
            daemon=True,
        )
        self.worker.start()

    def _selected(self):
        label = self.app_label.get()
        for item in self.targets:
            if item.label == label:
                return item
        return None

    def _listen_live(self, pid: int, app_name: str, provider: str, engine):
        capture = ProcessCapture(
            pid,
            settings.chunk_seconds,
            stream=True,
            quiet_after=quiet_seconds(self.quiet_label.get()),
        )
        self.capture = capture
        capture.start()
        try:
            while not self.stop_listen.is_set():
                if capture.error:
                    self.inbox.put(("error", capture.error))
                    break
                try:
                    runner = shanghai.run_live if self.languages[0].id == "wuu" else engine.run_live
                    reason = runner(
                        capture.pcm,
                        self.stop_listen,
                        self.inbox,
                        lambda: self._live_target(provider),
                        problem=lambda: capture.error,
                        save_enabled=lambda: self.keep_records,
                        app_name=app_name,
                        pid=pid,
                    )
                except CaptionError as exc:
                    self.inbox.put(("error", str(exc)))
                    break
                if self.stop_listen.is_set() or reason == "stop":
                    if reason == "stop" and not self.stop_listen.is_set():
                        if self.languages[0].id == "wuu":
                            self.inbox.put(("error", "上海话识别断开了。"))
                        else:
                            name = "Gemini" if provider == "gemini" else "千问"
                            self.inbox.put(("error", f"{name} 实时翻译断开了。"))
                    break
                if reason == "retarget":
                    self.inbox.put(("status", "换成新的字幕语言，重新接上。"))
        finally:
            capture.stop()
            if not self.stop_listen.is_set():
                self.inbox.put(("stopped",))

    def _live_target(self, provider: str) -> str:
        written = self.languages[1]
        if provider == "gemini":
            return written.live or "zh-Hans"
        return written.qwen or "zh"

    def _caption_limit(self, points: int, lines: int) -> int:
        """按实际字宽算两行能放下多少字，避免折成三行。"""
        key = (points, self._width, lines)
        cached = getattr(self, "_caption_limits", None)
        if cached is None:
            cached = {}
            self._caption_limits = cached
        if key in cached:
            return cached[key]
        measure = tk.font.Font(root=self.root, family=FONT, size=points).measure("字")
        px = measure if measure > 0 else int(round(points * 96 / 72))
        per_line = max(8, (self._width - 40) // px)
        cached[key] = per_line * lines
        return cached[key]

    def _show_caption(self, zh: str, source: str) -> None:
        now = time.monotonic()
        shown = self._translation_page.push(zh, self._caption_limit(22, 1), now)
        heard = self._source_page.push(source, self._caption_limit(15, 1), now)
        self._paint_caption(shown, heard)
        self._arm_caption_hold(now)

    def _paint_caption(self, shown: str, heard: str) -> None:
        self.translation.set(shown)
        self.source.set(heard)

    def _arm_caption_hold(self, now: float) -> None:
        waits = []
        for page, points in ((self._translation_page, 22), (self._source_page, 15)):
            delay = page.next_clear_in(self._caption_limit(points, 1), now)
            if delay is not None:
                waits.append(delay)
        if self._caption_job is not None:
            self.root.after_cancel(self._caption_job)
            self._caption_job = None
        if not waits:
            return
        self._caption_job = self.root.after(max(50, int(min(waits) * 1000) + 40), self._release_caption)

    def _release_caption(self) -> None:
        self._caption_job = None
        now = time.monotonic()
        shown = self._translation_page.tick(self._caption_limit(22, 1), now)
        heard = self._source_page.tick(self._caption_limit(15, 1), now)
        self._paint_caption(shown, heard)
        self._arm_caption_hold(now)

    def _stop_worker(self):
        self.stop_listen.set()
        self.listening = False
        self._show_listen_button(False)
        self.status.set("已停止。")
        self._paint_ball()

    def _drain(self):
        try:
            while True:
                wall, mono, item = self.inbox.get_nowait()
                kind, *payload = item
                self.debug.add(wall, mono, kind, tuple(payload))
                if kind == "caption":
                    zh, source = payload
                    self._show_caption(zh, source)
                    if self.keep_records and self.record_dir_name:
                        self.status.set(f"正在听，保存到 {self.record_dir_name}")
                    else:
                        self.status.set("正在听。")
                elif kind == "live":
                    zh, source = payload
                    self._show_caption(zh, source)
                elif kind == "status":
                    self.status.set(payload[0])
                elif kind == "stopped":
                    if self.listening:
                        self.listening = False
                        self._show_listen_button(False)
                        self._paint_ball()
                elif kind == "recording":
                    self.record_dir_name = payload[0]
                elif kind == "error":
                    self.status.set(payload[0])
        except queue.Empty:
            pass
        if self.listening and self.capture is not None and self.capture.error and not self.worker.is_alive():
            self._stop_worker()
        self.root.after(120, self._drain)

    def _toggle_debug(self, _event=None):
        self.debug.toggle()
        self._debug_toggle.configure(fg=ACCENT if self.debug.open else MUTED)
        self._place_debug()
        return "break"

    def _place_debug(self, x: int | None = None, y: int | None = None) -> None:
        left = self._x if x is None else x
        top = self._y if y is None else y
        self.debug.place(left + self._width + 8, top, BAR_H + self._body_h, self.collapsed)

    def _copy_error(self, _event=None):
        text = self.status.get().strip()
        if not text:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._copy_status.configure(text="已复制")
        self._copy_token += 1
        token = self._copy_token
        self.root.after(1200, lambda: self._restore_copy(token))
        return "break"

    def _restore_copy(self, token: int) -> None:
        if token == self._copy_token:
            self._copy_status.configure(text="复制")

    def _show_listen_button(self, listening: bool) -> None:
        if listening:
            self.listen_button.configure(text="停止", fg_color=LISTEN_RED, hover_color=LISTEN_RED_HOVER)
        else:
            self.listen_button.configure(text="开始听", fg_color=LISTEN_GREEN, hover_color=LISTEN_GREEN_HOVER)

    def _apply_quiet(self, _choice=None):
        seconds = quiet_seconds(self.quiet_label.get())
        if self.capture is not None:
            self.capture.quiet_after = seconds
        self._save()

    def _toggle_keep(self):
        self.keep_records = bool(self.keep.get())
        self._save()

    def _apply_languages(self, _choice=None):
        heard = find_language(INPUT_LANGUAGES, self.heard_label.get()) or self.languages[0]
        written = find_language(OUTPUT_LANGUAGES, self.written_label.get()) or self.languages[1]
        self.languages = (heard, written)
        self._save()

    def _save(self):
        heard, written = self.languages
        self.state["provider"] = "qwen" if self.provider.get() == "千问" else "gemini"
        self.state["source_lang"] = heard.id
        self.state["target_lang"] = written.id
        self.state["save"] = self.keep_records
        self.state["quiet"] = int(quiet_seconds(self.quiet_label.get()))
        self.state["collapsed"] = self.collapsed
        self.state["x"] = self._x
        self.state["y"] = self._y
        self.state["width"] = self._width
        self.state["body_h"] = self._body_h
        save_state(self.state)

    def close(self):
        if self._caption_job is not None:
            self.root.after_cancel(self._caption_job)
            self._caption_job = None
        self.stop_listen.set()
        if self.capture is not None:
            self.capture.stop()
        self._save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def _provider_label(name: str) -> str:
    return "千问" if (name or "").lower() == "qwen" else "Gemini"


def main():
    Overlay().run()
