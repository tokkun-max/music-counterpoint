# 4声部の64要素リスト（音名 or "blank"）を自動生成するモジュール

from music21 import pitch as m21pitch
from range_manager import VOICE_RANGES, clamp_to_range
from chord_analyzer import get_pitch_midis, get_root_midi
from voice_leading import choose_closest_in_range

STEPS = 64           # 4小節×16ステップ
STEPS_PER_MEASURE = 16
HALF_STEPS = 8       # 二分音符
EIGHTH_STEPS = 2     # 八分音符


def _midi_to_name(midi: int) -> str:
    p = m21pitch.Pitch()
    p.midi = midi
    return p.nameWithOctave


def _make_blank_list() -> list[str]:
    return ["blank"] * STEPS


def generate_bass_low(chord_names: list[str]) -> list[str]:
    """超低音：各コードのルート音を二分音符（8ステップ）で配置する。"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["bass_low"]
    for measure, chord in enumerate(chord_names):
        root_semi = get_root_midi(chord)
        midi = clamp_to_range((lo // 12) * 12 + root_semi, "bass_low")
        if midi < lo:
            midi += 12
        name = _midi_to_name(midi)
        base = measure * STEPS_PER_MEASURE
        # 二分音符×2 per measure
        for half_idx in range(2):
            step = base + half_idx * HALF_STEPS
            result[step] = name
    return result


def generate_bass_high(chord_names: list[str]) -> list[str]:
    """低音：八分休符+八分3rd+八分7th+四分3rd+八分7th+八分3rd+八分7th（per measure）"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["bass_high"]
    for measure, chord in enumerate(chord_names):
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

        base = measure * STEPS_PER_MEASURE
        # 八分休符(2) 八分3rd(2) 八分7th(2) 四分3rd(4) 八分7th(2) 八分3rd(2) 八分7th(2)
        result[base + 0]  = "R"   # 八分休符 step1
        result[base + 1]  = "R"   # 八分休符 step2
        result[base + 2]  = t     # 八分音符 3rd
        result[base + 4]  = s     # 八分音符 7th
        result[base + 6]  = t     # 四分音符 3rd（4step: 6,7,8,9はblank）
        result[base + 10] = s     # 八分音符 7th
        result[base + 12] = t     # 八分音符 3rd
        result[base + 14] = s     # 八分音符 7th
    return result


def generate_mid(chord_names: list[str]) -> list[str]:
    """中音：最短移動ボイスリーディングで二分音符（8ステップ）配置する。"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["mid"]
    prev_midi = None
    for measure, chord in enumerate(chord_names):
        chord_midis = get_pitch_midis(chord, base_midi=lo)
        base = measure * STEPS_PER_MEASURE
        for half_idx in range(2):
            step = base + half_idx * HALF_STEPS
            midi = choose_closest_in_range(prev_midi, chord_midis, lo, hi)
            result[step] = _midi_to_name(midi)
            prev_midi = midi
    return result


def generate_melody(chord_names: list[str]) -> list[str]:
    """主旋律：コード最上声部音を四分音符（4ステップ）で配置する（プレースホルダ）。"""
    result = _make_blank_list()
    lo, hi = VOICE_RANGES["melody"]
    prev_midi = None
    for measure, chord in enumerate(chord_names):
        chord_midis = get_pitch_midis(chord, base_midi=lo)
        base = measure * STEPS_PER_MEASURE
        for q in range(4):   # 4 quarter notes per measure
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
