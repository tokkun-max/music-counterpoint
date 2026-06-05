# コード名→構成音MIDIリスト変換・度数計算モジュール（高速スタティックテーブル実装）

from functools import lru_cache
from music21 import pitch as m21pitch

# 音名→半音番号（C=0）
_NOTE_SEMI: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11,
}

# コード種別→ルートからの半音間隔
_CHORD_INTERVALS: dict[str, list[int]] = {
    "":      [0, 4, 7],
    "maj":   [0, 4, 7],
    "M":     [0, 4, 7],
    "m":     [0, 3, 7],
    "min":   [0, 3, 7],
    "7":     [0, 4, 7, 10],
    "maj7":  [0, 4, 7, 11],
    "M7":    [0, 4, 7, 11],
    "m7":    [0, 3, 7, 10],
    "min7":  [0, 3, 7, 10],
    "dim":   [0, 3, 6],
    "dim7":  [0, 3, 6, 9],
    "aug":   [0, 4, 8],
    "+":     [0, 4, 8],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "add9":  [0, 4, 7, 14],
    "6":     [0, 4, 7, 9],
    "m6":    [0, 3, 7, 9],
}

# 半音差→度数（1〜7、長短区別なし）
DEGREE_MAP: dict[int, int] = {
    0: 1, 1: 2, 2: 2, 3: 3, 4: 3, 5: 4,
    6: 4, 7: 5, 8: 6, 9: 6, 10: 7, 11: 7,
}


def _parse(chord_name: str) -> tuple[str, str]:
    """'Am7' → ('A', 'm7')、'F#maj7' → ('F#', 'maj7') に分解する。"""
    s = chord_name.strip()
    if not s:
        raise ValueError("コード名が空です")
    root = s[0].upper()
    i = 1
    if i < len(s) and s[i] in ("#", "b"):
        root += s[i]
        i += 1
    return root, s[i:]


@lru_cache(maxsize=256)
def get_semitones(chord_name: str) -> tuple[int, ...]:
    """コード名→ルートからの半音間隔タプル（キャッシュ済み）。"""
    root, quality = _parse(chord_name)
    if root not in _NOTE_SEMI:
        raise ValueError(f"不明なルート音: '{root}'")
    intervals = _CHORD_INTERVALS.get(quality, _CHORD_INTERVALS[""])
    return tuple(intervals)


@lru_cache(maxsize=256)
def get_root_midi(chord_name: str) -> int:
    """コードのルート音の半音番号（0〜11）を返す。"""
    root, _ = _parse(chord_name)
    return _NOTE_SEMI[root]


def get_pitch_midis(chord_name: str, base_midi: int = 60) -> list[int]:
    """
    コード構成音のMIDIリストを返す。
    base_midi を基準にオクターブを決定する（デフォルト C4=60）。
    """
    root_semi = get_root_midi(chord_name)
    intervals = get_semitones(chord_name)
    root_base = (base_midi // 12) * 12 + root_semi
    if root_base < base_midi:
        root_base += 12
    return [root_base + semi for semi in intervals]


def get_pitch_names(chord_name: str) -> list[str]:
    """構成音の音名リスト（'C', 'E', 'G' 等）を返す。"""
    midis = get_pitch_midis(chord_name)
    result = []
    for m in midis:
        p = m21pitch.Pitch()
        p.midi = m
        result.append(p.name)
    return result


def semitones_to_degree(semitones: int) -> int:
    """半音差（任意整数）を 1〜7 の度数にマッピングする。"""
    return DEGREE_MAP[abs(semitones) % 12]
