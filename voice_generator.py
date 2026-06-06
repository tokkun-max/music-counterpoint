# 4声部の64要素リスト（音名 or "blank"）を自動生成するモジュール

from music21 import pitch as m21pitch
from range_manager import VOICE_RANGES, clamp_to_range
from chord_analyzer import get_pitch_midis, get_root_midi
from voice_leading import choose_closest_in_range

STEPS = 64             # 4小節×16ステップ
STEPS_PER_SLOT = 8    # 8スロット×8ステップ（各スロット＝半小節）
STEPS_PER_MEASURE = 16
HALF_STEPS = 8
EIGHTH_STEPS = 2


def _midi_to_name(midi: int) -> str:
    p = m21pitch.Pitch()
    p.midi = midi
    return p.nameWithOctave


def _make_blank_list() -> list[str]:
    return ["blank"] * STEPS


def generate_bass_low(chord_names: list[str]) -> list[str]:
    """超低音：各スロット（8ステップ）の先頭にルート音を配置する。"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["bass_low"]
    for slot, chord in enumerate(chord_names):
        root_semi = get_root_midi(chord)
        midi = clamp_to_range((lo // 12) * 12 + root_semi, "bass_low")
        if midi < lo:
            midi += 12
        name = _midi_to_name(midi)
        result[slot * STEPS_PER_SLOT] = name
    return result


def generate_bass_high(chord_names: list[str]) -> list[str]:
    """低音：各スロット（8ステップ）に 八分休符+八分3rd+八分7th+八分3rd を配置する。"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["bass_high"]
    for slot, chord in enumerate(chord_names):
        midis = get_pitch_midis(chord, base_midi=lo)
        third_semi  = midis[1] % 12 if len(midis) > 1 else midis[0] % 12
        if len(midis) > 3:
            seventh_semi = midis[3] % 12
        elif len(midis) > 2:
            seventh_semi = midis[2] % 12
        else:
            seventh_semi = midis[0] % 12

        def _clamped(semi: int) -> int:
            m = (lo // 12) * 12 + semi
            if m < lo:
                m += 12
            if m > hi:
                m -= 12
            return m

        t = _midi_to_name(_clamped(third_semi))
        s = _midi_to_name(_clamped(seventh_semi))

        base = slot * STEPS_PER_SLOT
        # 8ステップパターン: R R 3rd _ 7th _ 3rd _
        result[base + 0] = "R"
        result[base + 1] = "R"
        result[base + 2] = t     # 八分音符 3rd
        result[base + 4] = s     # 八分音符 7th
        result[base + 6] = t     # 八分音符 3rd
    return result


def generate_mid(chord_names: list[str]) -> list[str]:
    """中音：各スロット（8ステップ）の先頭に最短移動ボイスリーディングで二分音符を配置する。"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["mid"]
    prev_midi = None
    for slot, chord in enumerate(chord_names):
        chord_midis = get_pitch_midis(chord, base_midi=lo)
        midi = choose_closest_in_range(prev_midi, chord_midis, lo, hi)
        result[slot * STEPS_PER_SLOT] = _midi_to_name(midi)
        prev_midi = midi
    return result


def generate_melody(chord_names: list[str]) -> list[str]:
    """主旋律：各スロット（8ステップ）に四分音符×2（4ステップ間隔）で配置する（プレースホルダ）。"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["melody"]
    prev_midi = None
    for slot, chord in enumerate(chord_names):
        chord_midis = get_pitch_midis(chord, base_midi=lo)
        base = slot * STEPS_PER_SLOT
        for q in range(2):   # 2 quarter notes per slot
            step = base + q * 4
            midi = choose_closest_in_range(prev_midi, chord_midis, lo, hi)
            result[step] = _midi_to_name(midi)
            prev_midi = midi
    return result


def generate_all_voices(chord_names: list[str]) -> dict[str, list[str]]:
    """4声部すべての64要素リストを辞書で返す。"""
    return {
        "bass_low":  generate_bass_low(chord_names),
        "bass_high": generate_bass_high(chord_names),
        "mid":       generate_mid(chord_names),
        "melody":    generate_melody(chord_names),
    }
