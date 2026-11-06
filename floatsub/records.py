"""把一次收听里有译文的录音落盘。静音段不写。"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from floatsub.config import DATA

RECORDS = DATA / "records"

_INVALID = set('\\/:*?"<>|')


def _safe_name(name: str) -> str:
    cleaned = []
    for char in name or "":
        if char in _INVALID or ord(char) < 32:
            cleaned.append("_")
        else:
            cleaned.append(char)
    text = "".join(cleaned).strip(" .")
    return text[:40] or "app"


@dataclass
class RecordSession:
    directory: Path
    index: int = 0

    @classmethod
    def open(
        cls,
        app_name: str,
        provider: str,
        *,
        pid: int | None = None,
        source_lang: str = "",
        target_lang: str = "",
        root: Path | None = None,
    ) -> "RecordSession":
        base = root or RECORDS
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = _safe_name(app_name)
        folder = base / f"{stamp}-{safe}"
        suffix = 2
        while folder.exists():
            folder = base / f"{stamp}-{safe}-{suffix}"
            suffix += 1
        folder.mkdir()
        meta = {
            "app": app_name,
            "provider": provider,
            "started": datetime.now().isoformat(timespec="seconds"),
        }
        if pid is not None:
            meta["pid"] = pid
        if source_lang:
            meta["source_lang"] = source_lang
        if target_lang:
            meta["target_lang"] = target_lang
        (folder / "session.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return cls(folder)

    def add(self, wav: bytes, source: str, zh: str, *, source_lang: str = "", target_lang: str = "") -> str:
        self.index += 1
        name = f"{self.index:04d}.wav"
        (self.directory / name).write_bytes(wav)
        record = {
            "n": self.index,
            "wav": name,
            "source": source,
            "zh": zh,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        if source_lang:
            record["source_lang"] = source_lang
        if target_lang:
            record["target_lang"] = target_lang
        with (self.directory / "captions.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        with (self.directory / "captions.txt").open("a", encoding="utf-8") as handle:
            handle.write(f"{name}\n原文：{source}\n译文：{zh}\n\n")
        return name
