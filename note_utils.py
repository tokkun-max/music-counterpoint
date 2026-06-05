# NoteEvent←→64ステップ列の相互変換ユーティリティ

STEPS = 64

# 音価名 → ステップ数
DURATION_STEPS: dict[str, int] = {
    "全音符":       16,
    "付点二分":     12,
    "二分音符":      8,
    "付点四分":      6,
    "四分音符":      4,
    "付点八分":      3,
    "八分音符":      2,
    "十六分音符":    1,
}

STEPS_TO_NAME: dict[int, str] = {v: k for k, v in DURATION_STEPS.items()}


def dur_label(steps: int) -> str:
    return STEPS_TO_NAME.get(steps, f"{steps}ステップ")


def steps_to_events(steps: list[str]) -> list[dict]:
    """
    64要素リスト → NoteEventリスト。
    blank は直前の音符の継続として扱う（pitch="R" は休符として保持）。
    """
    events: list[dict] = []
    i = 0
    n = len(steps)
    while i < n:
        p = steps[i]
        if not p or p == "blank":
            i += 1
            continue
        if p == "R":
            # 連続する R をまとめて 1 つの休符イベントに
            dur = 0
            j = i
            while j < n and steps[j] == "R":
                dur += 1
                j += 1
            events.append({"step": i, "pitch": "R", "dur": dur})
            i = j
        else:
            # 音名：後続 blank が継続
            dur = 1
            j = i + 1
            while j < n and steps[j] == "blank":
                dur += 1
                j += 1
            events.append({"step": i, "pitch": p, "dur": dur})
            i = j
    return events


def events_to_steps(events: list[dict]) -> list[str]:
    """
    NoteEventリスト → 64要素リスト。
    音符: 先頭ステップに音名、残りを blank。
    休符: 該当ステップをすべて "R"（export 時に blank に変換）。
    """
    steps = ["blank"] * STEPS
    for ev in sorted(events, key=lambda e: e["step"]):
        s   = ev["step"]
        p   = ev["pitch"]
        dur = ev["dur"]
        if not (0 <= s < STEPS):
            continue
        if p == "R":
            for k in range(dur):
                if s + k < STEPS:
                    steps[s + k] = "R"
        else:
            steps[s] = p
            # blank は継続として残す（初期値が blank なので上書き不要）
    return steps


def events_to_export_steps(events: list[dict]) -> list[str]:
    """MIDI / CSV 出力用：R も blank に変換した 64 要素リストを返す。"""
    steps = events_to_steps(events)
    return ["blank" if s == "R" else s for s in steps]


def insert_or_replace_event(
    events: list[dict],
    step: int,
    pitch: str,
    dur: int,
) -> list[dict]:
    """
    step 位置に新しいイベントを挿入（重複する既存イベントを除去して）。
    他のイベントに重なる部分を切り詰める。
    """
    new_end = step + dur
    result = []
    for ev in events:
        es = ev["step"]
        ee = es + ev["dur"]
        if ee <= step or es >= new_end:
            result.append(ev)
        elif es < step:
            result.append({"step": es, "pitch": ev["pitch"], "dur": step - es})
        elif ee > new_end:
            result.append({"step": new_end, "pitch": ev["pitch"], "dur": ee - new_end})
    result.append({"step": step, "pitch": pitch, "dur": dur})
    result.sort(key=lambda e: e["step"])
    return result


def remove_event_at(events: list[dict], step: int) -> list[dict]:
    """step を含むイベントを削除する。"""
    return [ev for ev in events
            if not (ev["step"] <= step < ev["step"] + ev["dur"])]


def find_event_at(events: list[dict], step: int) -> dict | None:
    """step を含むイベントを返す（なければ None）。"""
    for ev in events:
        if ev["step"] <= step < ev["step"] + ev["dur"]:
            return ev
    return None
