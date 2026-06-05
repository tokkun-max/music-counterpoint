# 64要素リスト間で指定度数に一致するステップインデックスを返すモジュール

from music21 import pitch as m21pitch
from chord_analyzer import semitones_to_degree


def _name_to_midi(name: str) -> int | None:
    """音名→MIDI番号。'blank' や不正値は None を返す。"""
    if not name or name.strip().lower() == "blank":
        return None
    try:
        p = m21pitch.Pitch(name.strip())
        return p.midi
    except Exception:
        return None


def find_interval_indices(
    voice_a: list[str],
    voice_b: list[str],
    target_degree: int,
) -> list[int]:
    """
    同一ステップ位置で両リストとも音があり、かつ度数が target_degree に一致する
    ステップインデックスのリストを返す。
    """
    results: list[int] = []
    for i in range(min(len(voice_a), len(voice_b))):
        midi_a = _name_to_midi(voice_a[i])
        midi_b = _name_to_midi(voice_b[i])
        if midi_a is None or midi_b is None:
            continue
        degree = semitones_to_degree(abs(midi_a - midi_b))
        if degree == target_degree:
            results.append(i)
    return results
