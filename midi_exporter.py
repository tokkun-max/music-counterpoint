# 4声部64要素リストを4トラックMIDIファイルに変換・保存するモジュール

from midiutil import MIDIFile
from music21 import pitch as m21pitch

TRACK_NAMES   = ["Melody", "Mid", "Bass High", "Bass Low"]
TRACK_CHANNELS = [0, 1, 2, 3]
DEFAULT_VELOCITY = 80
STEPS = 64
STEP_BEATS = 0.25   # 1ステップ=16分音符=0.25拍


def _name_to_midi(name: str) -> int | None:
    if not name or name.strip().lower() == "blank":
        return None
    try:
        return m21pitch.Pitch(name.strip()).midi
    except Exception:
        return None


def _steps_to_notes(steps: list[str]) -> list[tuple[int, float, float]]:
    """
    64要素リストを (midi, start_beat, duration_beat) タプルのリストに変換する。
    連続する blank は直前の音の音価として扱う。
    """
    notes: list[tuple[int, float, float]] = []
    current_midi: int | None = None
    current_start: float = 0.0
    current_len: int = 0

    for i, name in enumerate(steps):
        midi = _name_to_midi(name)
        if midi is not None:
            # 前の音を確定
            if current_midi is not None:
                notes.append((current_midi,
                               current_start * STEP_BEATS,
                               current_len * STEP_BEATS))
            current_midi = midi
            current_start = i
            current_len = 1
        elif current_midi is not None:
            current_len += 1

    if current_midi is not None:
        notes.append((current_midi,
                      current_start * STEP_BEATS,
                      current_len * STEP_BEATS))
    return notes


def export_midi(
    voices: dict[str, list[str]],
    filepath: str | None = None,
    tempo: int = 120,
) -> str:
    """
    voices: {"melody":[], "mid":[], "bass_high":[], "bass_low":[]} (各64要素)
    filepath が None の場合は保存ダイアログを開く。保存したパスを返す。
    """
    if filepath is None:
        import tkinter.filedialog as fd
        filepath = fd.asksaveasfilename(
            title="MIDIファイルを保存",
            defaultextension=".mid",
            filetypes=[("MIDI files", "*.mid"), ("All files", "*.*")],
        )
    if not filepath:
        return ""

    voice_order = ["melody", "mid", "bass_high", "bass_low"]
    midi_file = MIDIFile(numTracks=4)

    for track_idx, voice_key in enumerate(voice_order):
        midi_file.addTrackName(track_idx, 0, TRACK_NAMES[track_idx])
        midi_file.addTempo(track_idx, 0, tempo)
        notes = _steps_to_notes(voices.get(voice_key, ["blank"] * STEPS))
        channel = TRACK_CHANNELS[track_idx]
        for midi_pitch, start_beat, dur_beat in notes:
            if dur_beat > 0:
                midi_file.addNote(track_idx, channel,
                                  midi_pitch, start_beat, dur_beat,
                                  DEFAULT_VELOCITY)

    with open(filepath, "wb") as f:
        midi_file.writeFile(f)
    return filepath
