# 声部ごとの音域（MIDI番号）定義とオクターブ補正を提供するモジュール

# 各声部の MIDI 音域（lo 以上 hi 以下）
VOICE_RANGES: dict[str, tuple[int, int]] = {
    "bass_low":  (36, 48),  # C2〜C3  超低音
    "bass_high": (48, 60),  # C3〜C4  低音
    "mid":       (60, 67),  # C4〜G4  中音
    "melody":    (60, 84),  # C4〜C6  主旋律
}


def clamp_to_range(midi: int, voice: str) -> int:
    """MIDI番号を指定声部の音域内に収めてオクターブ補正して返す。"""
    lo, hi = VOICE_RANGES[voice]
    while midi < lo:
        midi += 12
    while midi > hi:
        midi -= 12
    # 補正後も範囲外なら lo に固定（起こりにくいが安全策）
    if not (lo <= midi <= hi):
        midi = lo
    return midi


def in_range(midi: int, voice: str) -> bool:
    """MIDI番号が声部の音域内かどうかを返す。"""
    lo, hi = VOICE_RANGES[voice]
    return lo <= midi <= hi
