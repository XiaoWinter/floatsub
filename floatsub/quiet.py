"""没有声音时自动停止。选项和提示共用这一处。"""

QUIET_CHOICES = (("30秒", 30), ("1分钟", 60), ("2分钟", 120))


def quiet_label(seconds: int) -> str:
    for label, value in QUIET_CHOICES:
        if int(seconds) == value:
            return label
    return QUIET_CHOICES[0][0]


def quiet_seconds(label: str) -> float:
    for item, value in QUIET_CHOICES:
        if item == label:
            return float(value)
    return float(QUIET_CHOICES[0][1])


def quiet_message(seconds: float) -> str:
    whole = int(seconds)
    if whole >= 60 and whole % 60 == 0:
        return f"{whole // 60} 分钟没有声音，已停止。"
    return f"{whole} 秒没有声音，已停止。"
