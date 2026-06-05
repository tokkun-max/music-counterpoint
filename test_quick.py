"""新仕様でのクイックテスト（実行: python test_quick.py）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("1. range_manager ...", end=" ", flush=True)
from range_manager import clamp_to_range, in_range
assert clamp_to_range(60, "bass_low") == 48   # C4 → C3
assert clamp_to_range(36, "bass_low") == 36   # C2 → C2
assert clamp_to_range(84, "mid") == 60        # C6 → C4
print("OK")

print("2. chord_analyzer ...", end=" ", flush=True)
from chord_analyzer import get_pitch_names, get_pitch_midis, semitones_to_degree
assert get_pitch_names("C")    == ["C", "E", "G"]
assert get_pitch_names("Am7")  == ["A", "C", "E", "G"]
cdim_midis = get_pitch_midis("Cdim", base_midi=60)
assert cdim_midis == [60, 63, 66], f"Cdim midis={cdim_midis}"
assert semitones_to_degree(4) == 3
assert semitones_to_degree(7) == 5
print("OK  C:", get_pitch_names("C"), "Am7:", get_pitch_names("Am7"))

print("3. voice_leading ...", end=" ", flush=True)
from voice_leading import choose_closest, choose_closest_in_range
assert choose_closest(60, [59, 62, 64]) == 59       # 最近 B3
assert choose_closest(60, [57, 63]) == 63            # 同距離→高い方
assert choose_closest_in_range(60, [0, 4, 7], 60, 67) in range(60, 68)
print("OK")

print("4. voice_generator ...", end=" ", flush=True)
from voice_generator import generate_all_voices
v = generate_all_voices(["C", "F", "G", "C"])
assert len(v["bass_low"])  == 64
assert len(v["bass_high"]) == 64
assert len(v["mid"])       == 64
assert len(v["melody"])    == 64
# bass_low の先頭音は C2〜C3 の C であるはず
assert v["bass_low"][0] != "blank", f"bass_low[0] = {v['bass_low'][0]}"
print("OK  bass_low:", v["bass_low"][:4], "mid:", v["mid"][:4])

print("5. interval_highlighter ...", end=" ", flush=True)
from interval_highlighter import find_interval_indices
idxs = find_interval_indices(v["melody"], v["mid"], 3)
print(f"OK  {len(idxs)} indices at degree 3")

print("6. midi_exporter (dry) ...", end=" ", flush=True)
from midi_exporter import _steps_to_notes
notes = _steps_to_notes(v["bass_low"])
assert len(notes) > 0
print(f"OK  {len(notes)} notes")

print("7. csv_exporter (dry) ...", end=" ", flush=True)
from csv_exporter import chord_names_to_steps
cs = chord_names_to_steps(["C", "F", "G", "C"])
assert len(cs) == 64
print("OK")

print("8. csv_importer (import only) ...", end=" ", flush=True)
from csv_importer import _normalize
assert _normalize("C4") == "C4"
assert _normalize("") == "blank"
print("OK")

print("9. score_renderer (import only) ...", end=" ", flush=True)
from score_renderer import ScoreCanvas, MultiScorePanel, _pitch_to_y, _abs_dia
assert _abs_dia("E4") == 30
assert _abs_dia("G2") == 18
y_treble_E4 = _pitch_to_y("E4", "treble")
y_treble_G4 = _pitch_to_y("G4", "treble")
assert y_treble_G4 < y_treble_E4, "G4 は E4 より上（Y 小）"
print("OK")

print("10. note_utils ...", end=" ", flush=True)
from note_utils import steps_to_events, events_to_steps, events_to_export_steps
from note_utils import insert_or_replace_event, find_event_at, dur_label
steps = ["C4","blank","blank","blank","E4","blank","blank","blank"]
evs   = steps_to_events(steps)
assert len(evs) == 2, f"got {len(evs)} events"
assert evs[0]["pitch"] == "C4" and evs[0]["dur"] == 4
assert evs[1]["pitch"] == "E4" and evs[1]["dur"] == 4
back = events_to_steps(evs)
assert back[0] == "C4" and back[4] == "E4"
evs2 = insert_or_replace_event(evs, 0, "C4", 8)
assert len([e for e in evs2 if e["pitch"]=="E4"]) == 0, "E4 overwritten by longer C4"
print("OK")

print("11. player (import only) ...", end=" ", flush=True)
from player import Player
p = Player()
print(f"OK  available={p.available}")

print("\n=== All tests passed ===")
