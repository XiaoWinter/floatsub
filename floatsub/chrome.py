"""深色工具栏。单独一个不透明窗口，磨砂不会把深色吃掉。"""

import tkinter as tk

import customtkinter as ctk

from floatsub.languages import INPUT_LANGUAGES, OUTPUT_LANGUAGES
from floatsub.quiet import QUIET_CHOICES

LISTEN_GREEN = "#1f8f4e"
LISTEN_GREEN_HOVER = "#187843"
LISTEN_RED = "#c23b3b"
LISTEN_RED_HOVER = "#a32f2f"

FONT = "Noto Sans SC"
GLASS = "#000000"
INK = "#f8f1e7"
MUTED = "#e2d0c0"
BAR = "#2c211c"
ACCENT = "#d4894a"
ACCENT_HOVER = "#b87438"
CHIP = "#4a382e"
MENU = "#3c2c24"
BAR_H = 56
EDGE = 40
_EDGE_GAP = 6
_EDGE_PAD = 10
_SPEED_GAP = 8


def _menu_colors() -> dict:
    return {
        "fg_color": MENU,
        "button_color": ACCENT,
        "button_hover_color": ACCENT_HOVER,
        "text_color": INK,
        "dropdown_fg_color": BAR,
        "dropdown_hover_color": CHIP,
        "dropdown_text_color": INK,
    }


def fold_corner(width: int) -> tuple[int, int]:
    """收起按钮左上角，相对工具栏。气泡中心和这个按钮中心对齐。"""
    close_x = width - _EDGE_PAD - EDGE
    return close_x - _EDGE_GAP - EDGE, (BAR_H - EDGE) // 2


class Toolbar:
    def __init__(self, root, *, app_label, provider, heard, written, speed, on_speed, quiet, on_provider, on_languages, on_quiet, on_listen, on_refresh, on_collapse, on_close, bind_drag):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BAR)

        frame = ctk.CTkFrame(self.win, fg_color=BAR, corner_radius=0)
        frame.pack(fill="both", expand=True)
        bind_drag(frame)
        self.frame = frame

        text = ctk.CTkFont(family=FONT, size=14)
        small = ctk.CTkFont(family=FONT, size=13)
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(side="left", fill="y", padx=(12, 8))
        self._row = row
        bind_drag(row)

        ctk.CTkLabel(row, text="选择应用", font=small, text_color=MUTED).pack(side="left", padx=(0, 6))
        self.app_menu = ctk.CTkOptionMenu(
            row,
            values=[app_label.get() or "选择正在出声的应用"],
            variable=app_label,
            font=small,
            width=200,
            height=32,
            dynamic_resizing=False,
            **_menu_colors(),
        )
        self.app_menu.pack(side="left")
        ctk.CTkButton(
            row, text="⟳", command=on_refresh, font=text, width=36, height=32, fg_color=CHIP, hover_color=ACCENT
        ).pack(side="left", padx=(4, 12))
        ctk.CTkOptionMenu(
            row,
            values=["Gemini", "千问"],
            variable=provider,
            command=on_provider,
            font=small,
            width=96,
            height=32,
            dynamic_resizing=False,
            **_menu_colors(),
        ).pack(side="left", padx=(0, 12))
        ctk.CTkOptionMenu(
            row,
            values=[item.label for item in INPUT_LANGUAGES],
            variable=heard,
            command=on_languages,
            font=small,
            width=96,
            height=32,
            dynamic_resizing=False,
            **_menu_colors(),
        ).pack(side="left")
        arrow = ctk.CTkLabel(row, text="→", font=ctk.CTkFont(family=FONT, size=18), text_color=INK)
        arrow.pack(side="left", padx=8)
        bind_drag(arrow)
        ctk.CTkOptionMenu(
            row,
            values=[item.label for item in OUTPUT_LANGUAGES],
            variable=written,
            command=on_languages,
            font=small,
            width=96,
            height=32,
            dynamic_resizing=False,
            **_menu_colors(),
        ).pack(side="left", padx=(0, 12))
        self.listen = ctk.CTkButton(
            row,
            text="开始听",
            command=on_listen,
            font=text,
            width=84,
            height=32,
            fg_color=LISTEN_GREEN,
            hover_color=LISTEN_GREEN_HOVER,
            text_color="#ffffff",
        )
        self.listen.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(row, text="自动停止", font=small, text_color=MUTED).pack(side="left", padx=(12, 6))
        ctk.CTkOptionMenu(
            row,
            values=[label for label, _seconds in QUIET_CHOICES],
            variable=quiet,
            command=on_quiet,
            font=small,
            width=88,
            height=32,
            dynamic_resizing=False,
            **_menu_colors(),
        ).pack(side="left")
        self.speed_box = ctk.CTkFrame(frame, fg_color="transparent")
        ctk.CTkLabel(self.speed_box, text="速度", font=small, text_color=MUTED).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            self.speed_box,
            text="−",
            command=lambda: on_speed(-1),
            font=text,
            width=28,
            height=28,
            fg_color=CHIP,
            hover_color=ACCENT,
        ).pack(side="left")
        ctk.CTkLabel(self.speed_box, textvariable=speed, font=small, text_color=INK, width=42).pack(side="left", padx=4)
        ctk.CTkButton(
            self.speed_box,
            text="+",
            command=lambda: on_speed(1),
            font=text,
            width=28,
            height=28,
            fg_color=CHIP,
            hover_color=ACCENT,
        ).pack(side="left")

        self.fold = ctk.CTkButton(
            frame, text="−", command=on_collapse, font=text, width=EDGE, height=EDGE, fg_color=CHIP, hover_color=ACCENT
        )
        self.close = ctk.CTkButton(
            frame, text="×", command=on_close, font=text, width=EDGE, height=EDGE, fg_color=CHIP, hover_color=ACCENT
        )

    def set_apps(self, labels: list[str]) -> None:
        if not labels:
            labels = ["现在没有应用在出声"]
        self.app_menu.configure(values=labels)
        if self.app_menu.get() not in labels:
            self.app_menu.set(labels[0])

    def layout_edges(self, width: int) -> None:
        fold_x, y = fold_corner(width)
        close_x = width - _EDGE_PAD - EDGE
        self.fold.place(x=fold_x, y=y)
        self.close.place(x=close_x, y=y)
        self.win.update_idletasks()
        speed_w = self.speed_box.winfo_reqwidth()
        speed_x = fold_x - _SPEED_GAP - speed_w
        self.speed_box.place(x=speed_x, y=(BAR_H - self.speed_box.winfo_reqheight()) // 2)
        self._row.pack_configure(padx=(12, width - speed_x + 8))

    def show(self, x: int, y: int, width: int) -> None:
        self.layout_edges(width)
        self.win.geometry(f"{width}x{BAR_H}+{int(x)}+{int(y)}")
        self.win.deiconify()
        self.win.lift()

    def hide(self) -> None:
        self.win.withdraw()
