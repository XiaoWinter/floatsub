import ctypes
from dataclasses import dataclass

import psutil
from pycaw.constants import AudioSessionState
from pycaw.utils import AudioUtilities

_SKIP = {"audiodg.exe", "system", "idle", "registry"}


@dataclass(frozen=True)
class AppTarget:
    pid: int
    name: str
    title: str

    @property
    def label(self) -> str:
        title = self.title.strip()
        if title:
            short = title if len(title) <= 42 else title[:41] + "…"
            return f"{self.name} — {short}"
        return f"{self.name} ({self.pid})"


def _titles() -> dict[int, str]:
    user32 = ctypes.windll.user32
    found: dict[int, str] = {}

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        current = found.get(pid.value, "")
        if len(title) > len(current):
            found[pid.value] = title
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(visit)
    user32.EnumWindows(enum_proc, 0)
    return found


def _root(process: psutil.Process) -> psutil.Process:
    current = process
    seen = {current.pid}
    try:
        name = current.name().lower()
    except psutil.Error:
        return current
    while True:
        try:
            parent = current.parent()
        except psutil.Error:
            return current
        if parent is None or parent.pid in seen:
            return current
        try:
            parent_name = parent.name().lower()
        except psutil.Error:
            return current
        if parent_name != name:
            return current
        seen.add(parent.pid)
        current = parent


def _title_for(root: psutil.Process, titles: dict[int, str]) -> str:
    own = titles.get(root.pid, "")
    if own:
        return own
    try:
        children = root.children(recursive=True)
    except psutil.Error:
        return ""
    best = ""
    for child in children:
        title = titles.get(child.pid, "")
        if len(title) > len(best):
            best = title
    return best


def playing_apps() -> list[AppTarget]:
    titles = _titles()
    found: dict[int, AppTarget] = {}
    for session in AudioUtilities.GetAllSessions():
        if session.State == AudioSessionState.Expired:
            continue
        process = session.Process
        if process is None:
            continue
        try:
            if process.name().lower() in _SKIP:
                continue
            root = _root(process)
            name = root.name()
        except psutil.Error:
            continue
        if root.pid in found:
            continue
        found[root.pid] = AppTarget(root.pid, name, _title_for(root, titles))
    return sorted(found.values(), key=lambda item: item.label.lower())
