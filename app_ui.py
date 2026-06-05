# メインUIファイル：再生・キーボード編集・アンドゥ・複数選択・MIDI/CSV出力を統合する

import os
import sys
import copy

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import tkinter as tk
from tkinter import ttk, messagebox
from music21 import pitch as m21pitch

from chord_analyzer import get_pitch_names
from voice_generator import generate_all_voices
from interval_highlighter import find_interval_indices
from midi_exporter import export_midi
from csv_exporter import export_csv, chord_names_to_steps
from csv_importer import import_csv
from score_renderer import MultiScorePanel
from player import Player
from note_utils import (
    STEPS, DURATION_STEPS, dur_label,
    steps_to_events, events_to_steps, events_to_export_steps,
    insert_or_replace_event, remove_event_at, find_event_at,
)

# ---- 定数 ----
VOICES = ["melody", "mid", "bass_high", "bass_low"]
VOICE_LABELS = {
    "melody":    "主旋律",
    "mid":       "中音域",
    "bass_high": "低音域",
    "bass_low":  "超低音域",
}
ROOTS     = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
QUALITIES = ["", "m", "7", "maj7", "m7", "dim", "aug", "sus4"]
QUALITY_LABELS = {
    "": "maj", "m": "m", "7": "7", "maj7": "maj7",
    "m7": "m7", "dim": "dim", "aug": "aug", "sus4": "sus4",
}

# 音価ステップ順（+ / - キーで循環）
DUR_ORDER = [1, 2, 3, 4, 6, 8, 12, 16]

MAX_UNDO = 50

# ダミーデータ（Cメジャースケール4小節・四分音符）
_SCALE = ["C4","D4","E4","F4","G4","A4","B4","C5",
          "D5","E5","F5","G5","A5","B5","C6","C5"]
DUMMY_MELODY: list[str] = []
for _n in _SCALE:
    DUMMY_MELODY.extend([_n, "blank", "blank", "blank"])
DUMMY_CHORDS = ["C", "F", "G", "C"]


class ChordSelector(tk.Frame):
    def __init__(self, master, measure_no: int, default: str = "C", **kwargs):
        super().__init__(master, bg="#f0f0f0", **kwargs)
        tk.Label(self, text=f"{measure_no}小節", bg="#f0f0f0",
                 font=("Arial", 8)).pack()
        self._root_var = tk.StringVar(value=default)
        self._qual_var = tk.StringVar(value="maj")
        ttk.Combobox(self, textvariable=self._root_var,
                     values=ROOTS, state="readonly", width=4).pack()
        ttk.Combobox(self, textvariable=self._qual_var,
                     values=list(QUALITY_LABELS.values()),
                     state="readonly", width=6).pack()

    def get_chord(self) -> str:
        inv = {v: k for k, v in QUALITY_LABELS.items()}
        return self._root_var.get() + inv.get(self._qual_var.get(), "")

    def set_chord(self, name: str):
        if not name:
            return
        root = name[0].upper()
        i = 1
        if i < len(name) and name[i] in ("#", "b"):
            root += name[i]; i += 1
        qual_key = name[i:]
        self._root_var.set(root if root in ROOTS else "C")
        self._qual_var.set(QUALITY_LABELS.get(qual_key, "maj"))


# =====================================================================
class CounterpointApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("対旋律作成ツール")
        self.geometry("1100x920")
        self.resizable(True, True)
        self.configure(bg="#f0f0f0")

        # ---- データ ----
        self._events:     dict[str, list[dict]] = {v: [] for v in VOICES}
        self._sel_voice:  str | None = None
        self._sel_steps:  set[int]   = set()       # 選択中ステップ集合
        self._sel_ev:     dict | None = None        # キー操作の基準イベント
        self._undo_stack: list[dict]  = []
        self._player = Player()
        self._player.set_step_callback(self._on_play_step)
        self._is_playing = False

        self._build_ui()
        self._bind_keys()
        self._load_dummy()

    # ================================================================ UI 構築

    def _build_ui(self):
        # ---- トップバー ----
        top = tk.Frame(self, bg="#2c3e50", pady=6)
        top.pack(fill="x")
        tk.Label(top, text="対旋律作成ツール", font=("Arial", 13, "bold"),
                 fg="white", bg="#2c3e50").pack(side="left", padx=12)

        def mkbtn(parent, text, cmd, color="#3498db"):
            return tk.Button(parent, text=text, command=cmd, bg=color, fg="white",
                             relief="flat", padx=9, pady=4, cursor="hand2",
                             font=("Arial", 9))

        mkbtn(top, "CSVインポート",  self._on_import_csv).pack(side="left", padx=3)
        mkbtn(top, "新規作成",       self._on_new).pack(side="left", padx=3)
        mkbtn(top, "対旋律を自動生成", self._on_generate, "#27ae60").pack(side="left", padx=3)
        mkbtn(top, "MIDI出力",      self._on_export_midi, "#8e44ad").pack(side="left", padx=3)
        mkbtn(top, "CSV出力",       self._on_export_csv,  "#e67e22").pack(side="left", padx=3)

        self._play_btn = mkbtn(top, "▶ 再生", self._on_play_stop, "#16a085")
        self._play_btn.pack(side="left", padx=8)
        if not self._player.available:
            self._play_btn.config(state="disabled", text="▶ (unavailable)")

        # ---- コード進行 ----
        cf = tk.LabelFrame(self, text="コード進行（小節ごと）",
                           bg="#f0f0f0", font=("Arial", 9))
        cf.pack(fill="x", padx=10, pady=(5, 2))
        self._chord_sel: list[ChordSelector] = []
        for i, ch in enumerate(DUMMY_CHORDS):
            cs = ChordSelector(cf, i + 1, default=ch)
            cs.pack(side="left", padx=14, pady=4)
            self._chord_sel.append(cs)

        # ---- 主旋律入力 ----
        mf = tk.LabelFrame(self, text="主旋律テキスト（音名スペース区切り）",
                           bg="#f0f0f0", font=("Arial", 9))
        mf.pack(fill="x", padx=10, pady=2)
        self._mel_entry = tk.Entry(mf, width=110, font=("Courier", 9))
        self._mel_entry.pack(fill="x", padx=6, pady=4)
        self._mel_entry.bind("<Return>", lambda e: self._on_generate())

        # ---- 音符エディタ ----
        self._build_editor_panel()

        # ---- 度数ハイライト ----
        self._build_hl_panel()

        # ---- 五線譜 ----
        sf = tk.Frame(self, bg="#f0f0f0")
        sf.pack(fill="both", expand=True, padx=10, pady=4)

        vbar = ttk.Scrollbar(sf, orient="vertical")
        vbar.pack(side="right", fill="y")
        sc_canvas = tk.Canvas(sf, bg="#f0f0f0", highlightthickness=0,
                              yscrollcommand=vbar.set)
        sc_canvas.pack(side="left", fill="both", expand=True)
        vbar.config(command=sc_canvas.yview)

        inner = tk.Frame(sc_canvas, bg="#ffffff")
        win_id = sc_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: sc_canvas.configure(
            scrollregion=sc_canvas.bbox("all")))
        sc_canvas.bind("<Configure>",
                       lambda e: sc_canvas.itemconfig(win_id, width=e.width))

        self._score = MultiScorePanel(inner,
                                      on_note_select=self._on_note_selected,
                                      on_drag_select=self._on_drag_selected)
        self._score.pack(fill="both", expand=True)

        # ---- ステータスバー ----
        self._sv = tk.StringVar(value="起動しました。")
        tk.Label(self, textvariable=self._sv, anchor="w", relief="sunken",
                 bg="#dde", font=("Arial", 9)).pack(fill="x", side="bottom")

    def _build_editor_panel(self):
        ep = tk.LabelFrame(self, text="音符エディタ  [↑↓]音高  [←→]移動  [+/-]音価  [0]休符切替  [Del]削除  [Ctrl+Z]戻る",
                           bg="#f0f0f0", font=("Arial", 8))
        ep.pack(fill="x", padx=10, pady=2)

        # 選択情報
        info_fr = tk.Frame(ep, bg="#f0f0f0")
        info_fr.pack(fill="x", padx=6, pady=(2, 0))
        tk.Label(info_fr, text="選択中:", bg="#f0f0f0").pack(side="left")
        self._info_var = tk.StringVar(value="（音符をクリックまたはドラッグで選択）")
        tk.Label(info_fr, textvariable=self._info_var, bg="#f0f0f0",
                 font=("Arial", 9, "bold"), fg="#c0392b").pack(side="left", padx=4)

        # 操作ボタン（視覚的補助；主操作はキーボード）
        btn_fr = tk.Frame(ep, bg="#f0f0f0")
        btn_fr.pack(fill="x", padx=6, pady=(0, 4))

        def eb(text, cmd, color="#dfe6e9", w=5):
            return tk.Button(btn_fr, text=text, command=cmd, width=w,
                             bg=color, font=("Arial", 8), relief="flat")

        eb("▲半音", lambda: self._shift_pitch(+1)).pack(side="left", padx=1)
        eb("▼半音", lambda: self._shift_pitch(-1)).pack(side="left", padx=1)
        tk.Label(btn_fr, text=" | ", bg="#f0f0f0").pack(side="left")

        # 音価ボタン
        dur_labels = [("全", 16),("付二",12),("二",8),("付四",6),
                      ("四",4),("付八",3),("八",2),("十六",1)]
        for lbl, st in dur_labels:
            eb(lbl, lambda s=st: self._set_dur(s), w=4).pack(side="left", padx=1)

        tk.Label(btn_fr, text=" | ", bg="#f0f0f0").pack(side="left")
        eb("休符[0]", self._toggle_rest, "#fab1a0", 6).pack(side="left", padx=1)
        eb("削除[Del]", self._delete_sel, "#d63031", 7).pack(side="left", padx=1)
        eb("戻る[Ctrl+Z]", self._undo, "#95a5a6", 8).pack(side="left", padx=2)

    def _build_hl_panel(self):
        hl = tk.LabelFrame(self, text="度数ハイライト",
                           bg="#f0f0f0", font=("Arial", 9))
        hl.pack(fill="x", padx=10, pady=2)

        # HL ON/OFF トグルボタン（仕様書準拠）
        self._hl_active = False
        self._hl_btn = tk.Button(
            hl, text="HL: OFF", width=7,
            command=self._toggle_hl,
            bg="#95a5a6", fg="white", relief="flat", font=("Arial", 9, "bold"),
        )
        self._hl_btn.grid(row=0, column=0, padx=(6, 2), pady=3)

        tk.Label(hl, text="声部A:", bg="#f0f0f0").grid(row=0, column=1, padx=4)
        self._va = tk.StringVar(value="melody")
        va_cb = ttk.Combobox(hl, textvariable=self._va, state="readonly",
                             values=VOICES, width=11)
        va_cb.grid(row=0, column=2)

        tk.Label(hl, text="声部B:", bg="#f0f0f0").grid(row=0, column=3, padx=4)
        self._vb = tk.StringVar(value="mid")
        vb_cb = ttk.Combobox(hl, textvariable=self._vb, state="readonly",
                              values=VOICES, width=11)
        vb_cb.grid(row=0, column=4)

        tk.Label(hl, text="度数:", bg="#f0f0f0").grid(row=0, column=5, padx=4)
        self._deg = tk.IntVar(value=3)
        self._deg_cb = ttk.Combobox(hl, textvariable=self._deg, state="readonly",
                                    values=list(range(1, 8)), width=4)
        self._deg_cb.grid(row=0, column=6)

        tk.Button(hl, text="ハイライト", command=self._on_highlight,
                  bg="#2980b9", fg="white", relief="flat",
                  padx=8).grid(row=0, column=7, padx=5)
        tk.Button(hl, text="クリア", command=self._on_clear_hl,
                  relief="flat", padx=6).grid(row=0, column=8)

        # HL パネル内の全 Combobox に↑↓インターセプトを設定
        # HL OFF のとき → 音高調整、HL ON のとき → Combobox デフォルト動作
        for cb in (va_cb, vb_cb, self._deg_cb):
            cb.bind("<Up>",   self._cb_up)
            cb.bind("<Down>", self._cb_down)

    # ================================================================ キーバインド

    def _bind_keys(self):
        # 汎用キーハンドラ（テキスト入力中はスキップ）
        self.bind_all("<Key>",         self._on_key)
        # 直接バインド（仕様書準拠・Japanese キーボード対応）
        self.bind_all("<Control-z>",   lambda e: self._guard(self._undo))
        self.bind_all("<Control-Z>",   lambda e: self._guard(self._undo))
        self.bind_all("<Delete>",      lambda e: self._guard(self._delete_sel))
        self.bind_all("<Up>",          lambda e: self._guard(lambda: self._shift_pitch(+1)))
        self.bind_all("<Down>",        lambda e: self._guard(lambda: self._shift_pitch(-1)))
        self.bind_all("<Left>",        lambda e: self._guard(lambda: self._nav(-1)))
        self.bind_all("<Right>",       lambda e: self._guard(lambda: self._nav(+1)))
        # + / - : keysym が環境依存のため複数バインド
        for seq in ("<plus>", "<KP_Add>", "<equal>"):
            self.bind_all(seq, lambda e: self._guard(lambda: self._cycle_dur(+1)))
        for seq in ("<minus>", "<KP_Subtract>"):
            self.bind_all(seq, lambda e: self._guard(lambda: self._cycle_dur(-1)))
        self.bind_all("<Key-0>",       lambda e: self._guard(self._toggle_rest))

    # ---- HL ON/OFF トグル ----

    def _toggle_hl(self):
        """HL ON/OFF を切り替える。ON: 度数 Combobox 操作モード、OFF: 音高編集モード。"""
        self._hl_active = not self._hl_active
        if self._hl_active:
            self._hl_btn.config(text="HL: ON", bg="#e74c3c")
            self._deg_cb.focus_set()   # ON のとき Combobox にフォーカス
            self._sv.set("HL ON：↑↓ で度数を変更、「ハイライト」ボタンで反映")
        else:
            self._hl_btn.config(text="HL: OFF", bg="#95a5a6")
            self.focus_set()           # OFF のとき root にフォーカス（音高編集用）
            self._sv.set("HL OFF：音符を選択して ↑↓ で音高調整")

    def _cb_up(self, event):
        """HL パネル Combobox の ↑ キーインターセプト。"""
        if not self._hl_active:
            self._shift_pitch(+1)
            return "break"   # Combobox のデフォルト動作を止める

    def _cb_down(self, event):
        """HL パネル Combobox の ↓ キーインターセプト。"""
        if not self._hl_active:
            self._shift_pitch(-1)
            return "break"

    # ---- ガード ----

    def _guard(self, fn):
        """テキスト入力中はショートカットをスキップする。"""
        if not self._is_text_focused():
            fn()

    def _is_text_focused(self) -> bool:
        try:
            return isinstance(self.focus_get(), (tk.Entry, tk.Text))
        except Exception:
            return False

    def _on_key(self, event):
        if self._is_text_focused():
            return
        k = event.keysym
        # 個別バインドで処理済みのキーは重複しないようスキップ
        if k in ("Up", "Down", "Left", "Right", "Delete",
                 "plus", "minus", "KP_Add", "KP_Subtract", "equal", "0"):
            return
        # その他（将来拡張用）

    # ================================================================ アンドゥ

    def _push_undo(self):
        state = {v: copy.deepcopy(self._events[v]) for v in VOICES}
        self._undo_stack.append(state)
        if len(self._undo_stack) > MAX_UNDO:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            self._sv.set("これ以上戻れません。")
            return
        state = self._undo_stack.pop()
        self._events = state
        for v in VOICES:
            self._score.update_voice(v, self._events[v])
        self._sel_ev    = None
        self._sel_steps = set()
        self._update_info()
        self._sv.set("元に戻しました。")

    # ================================================================ 選択

    def _on_note_selected(self, voice: str, step: int, pitch: str, dur: int):
        self._sel_voice = voice
        if pitch and pitch not in ("blank",):
            ev = find_event_at(self._events.get(voice, []), step)
            if ev:
                self._sel_ev    = ev
                self._sel_steps = {ev["step"]}
            else:
                self._sel_ev    = None
                self._sel_steps = set()
        else:
            self._sel_ev    = None
            self._sel_steps = set()
        # HL OFF のとき root にフォーカスを移して Combobox の ↑↓ 干渉を防ぐ
        if not self._hl_active:
            self.focus_set()
        self._score.set_selected(voice, self._sel_steps)
        self._update_info()

    def _on_drag_selected(self, voice: str, selections: list[tuple]):
        self._sel_voice = voice
        self._sel_steps = {s[0] for s in selections}
        # 一番小さいステップをキー操作の基準にする
        if self._sel_steps:
            first = min(self._sel_steps)
            self._sel_ev = find_event_at(self._events.get(voice, []), first)
        else:
            self._sel_ev = None
        if not self._hl_active:
            self.focus_set()
        self._score.set_selected(voice, self._sel_steps)
        self._update_info()
        self._sv.set(f"{VOICE_LABELS.get(voice,'?')} で {len(self._sel_steps)} 音符を選択")

    def _update_info(self):
        if self._sel_ev:
            p   = self._sel_ev["pitch"]
            d   = self._sel_ev["dur"]
            vl  = VOICE_LABELS.get(self._sel_voice, "?")
            n   = len(self._sel_steps)
            sel_str = f"{n}音選択中" if n > 1 else ""
            self._info_var.set(
                f"{vl} | Step {self._sel_ev['step']} | "
                f"{'休符' if p=='R' else p} | {dur_label(d)}（{d}step）{sel_str}"
            )
        else:
            self._info_var.set("（音符をクリックまたはドラッグで選択）")

    # ================================================================ 音符編集

    def _shift_pitch(self, semitones: int):
        if not self._sel_voice or not self._sel_steps:
            return
        self._push_undo()
        changed = False
        for ev in self._events.get(self._sel_voice, []):
            if ev["step"] in self._sel_steps and ev["pitch"] != "R":
                try:
                    p = m21pitch.Pitch(ev["pitch"])
                    p.midi += semitones
                    ev["pitch"] = p.nameWithOctave
                    changed = True
                except Exception:
                    pass
        if changed:
            self._refresh_voice(self._sel_voice)
            self._update_info()

    def _nav(self, direction: int):
        """←→キーで隣の音符/休符へ移動（仕様書準拠：イベント単位ジャンプ）。"""
        if self._sel_voice is None:
            # 声部未選択なら melody の先頭から
            self._sel_voice = "melody"

        events = sorted(self._events.get(self._sel_voice, []),
                        key=lambda e: e["step"])
        if not events:
            return

        if self._sel_ev is not None:
            cur_step = self._sel_ev["step"]
            cur_idx  = next((i for i, e in enumerate(events)
                             if e["step"] == cur_step), 0)
        else:
            cur_idx = 0 if direction > 0 else len(events) - 1

        new_idx = max(0, min(len(events) - 1, cur_idx + direction))
        new_ev  = events[new_idx]
        self._sel_ev    = new_ev
        self._sel_steps = {new_ev["step"]}
        self._score.set_selected(self._sel_voice, self._sel_steps)
        self._update_info()
        # 情報欄に音価も表示
        p = new_ev["pitch"]
        d = new_ev["dur"]
        self._sv.set(
            f"[{VOICE_LABELS.get(self._sel_voice,'?')}] "
            f"Step {new_ev['step']} : {'休符' if p=='R' else p} / {dur_label(d)}（{d}step）"
        )

    def _cycle_dur(self, direction: int):
        """+ / - キーで音価を 1ステップずつ変更。"""
        if self._sel_ev is None:
            return
        cur = self._sel_ev["dur"]
        if cur in DUR_ORDER:
            idx = DUR_ORDER.index(cur)
        else:
            idx = min(range(len(DUR_ORDER)), key=lambda i: abs(DUR_ORDER[i] - cur))
        new_idx = max(0, min(len(DUR_ORDER) - 1, idx + direction))
        new_dur = DUR_ORDER[new_idx]
        if new_dur != cur:
            self._set_dur(new_dur)

    def _set_dur(self, new_dur: int):
        if self._sel_ev is None or self._sel_voice is None:
            return
        self._push_undo()
        old_step = self._sel_ev["step"]
        pitch    = self._sel_ev["pitch"]
        events   = insert_or_replace_event(
            self._events[self._sel_voice], old_step, pitch, new_dur)
        self._events[self._sel_voice] = events
        self._sel_ev = find_event_at(events, old_step)
        if self._sel_ev:
            self._sel_steps = {self._sel_ev["step"]}
        self._refresh_voice(self._sel_voice)
        self._update_info()

    def _toggle_rest(self):
        """0 キー：選択音符を休符 ↔ 音符（C4）に切り替える。"""
        if not self._sel_voice or not self._sel_steps:
            return
        self._push_undo()
        for ev in self._events.get(self._sel_voice, []):
            if ev["step"] in self._sel_steps:
                if ev["pitch"] == "R":
                    # 直前の音符のピッチを参照して復元
                    ev["pitch"] = self._nearest_pitch(self._sel_voice, ev["step"])
                else:
                    ev["pitch"] = "R"
        self._refresh_voice(self._sel_voice)
        if self._sel_ev:
            self._sel_ev = find_event_at(
                self._events[self._sel_voice], self._sel_ev["step"])
        self._update_info()

    def _nearest_pitch(self, voice: str, step: int) -> str:
        """指定ステップ直前の音符ピッチを返す（なければ C4）。"""
        events = sorted(
            [ev for ev in self._events.get(voice, [])
             if ev["step"] < step and ev["pitch"] != "R"],
            key=lambda e: e["step"],
        )
        return events[-1]["pitch"] if events else "C4"

    def _delete_sel(self):
        """仕様書準拠：Delete は選択範囲を削除（イベントをリストから除去）。"""
        if not self._sel_voice or not self._sel_steps:
            return
        self._push_undo()
        events = [ev for ev in self._events[self._sel_voice]
                  if ev["step"] not in self._sel_steps]
        self._events[self._sel_voice] = events
        self._sel_ev    = None
        self._sel_steps = set()
        self._refresh_voice(self._sel_voice)
        self._update_info()
        n = len(self._sel_steps) if self._sel_steps else 0
        self._sv.set(f"削除しました。Ctrl+Z で元に戻せます。")

    def _refresh_voice(self, voice: str | None):
        if voice:
            self._score.update_voice(voice, self._events[voice])
            self._score.set_selected(voice, self._sel_steps)

    # ================================================================ 再生

    def _on_play_stop(self):
        if self._is_playing:
            self._player.stop()
            self._is_playing = False
            self._play_btn.config(text="▶ 再生", bg="#16a085")
            self._score.set_play_cursor(None)
            self._sv.set("再生停止。")
        else:
            if not self._player.available:
                messagebox.showwarning("再生不可",
                    "MIDI 出力デバイスが見つかりません。")
                return
            voices_steps = {v: events_to_export_steps(self._events[v])
                            for v in VOICES}
            self._player.start(voices_steps)
            self._is_playing = True
            self._play_btn.config(text="■ 停止", bg="#c0392b")
            self._sv.set("再生中…")
            self.after(200, self._check_play_done)

    def _check_play_done(self):
        if self._is_playing and not self._player.is_playing():
            self._is_playing = False
            self._play_btn.config(text="▶ 再生", bg="#16a085")
            self._score.set_play_cursor(None)
            self._sv.set("再生完了。")
        elif self._is_playing:
            self.after(200, self._check_play_done)

    def _on_play_step(self, step: int):
        self.after(0, lambda: self._score.set_play_cursor(step))

    # ================================================================ 度数HL

    def _on_highlight(self):
        va  = self._va.get(); vb = self._vb.get()
        deg = int(self._deg.get())
        sa  = events_to_export_steps(self._events.get(va, []))
        sb  = events_to_export_steps(self._events.get(vb, []))
        idx = find_interval_indices(sa, sb, deg)
        self._score.update_voice(va, self._events[va], idx)
        self._score.update_voice(vb, self._events[vb], idx)
        self._sv.set(f"{deg}度: {len(idx)} 箇所ハイライト")

    def _on_clear_hl(self):
        for v in VOICES:
            self._score.update_voice(v, self._events[v])

    # ================================================================ ファイル操作

    def _on_new(self):
        for cs in self._chord_sel: cs.set_chord("C")
        self._mel_entry.delete(0, tk.END)
        for v in VOICES:
            self._events[v] = []
            self._score.clear_voice(v)
        self._sel_ev = None; self._sel_steps = set()
        self._update_info()

    def _on_import_csv(self):
        result = import_csv()
        if result is None: return
        for v in ["melody","mid","bass_high","bass_low"]:
            self._events[v] = steps_to_events(result[v])
        for i, cs in enumerate(self._chord_sel):
            if i < len(result["chord_names"]):
                cs.set_chord(result["chord_names"][i])
        for v in VOICES:
            if self._events[v]:
                self._score.update_voice(v, self._events[v])
            else:
                self._score.clear_voice(v)
        self._sv.set(f"CSV読込: {' '.join(result['chord_names'])}")

    def _on_generate(self):
        chord_names = [cs.get_chord() for cs in self._chord_sel]
        try:
            gen = generate_all_voices(chord_names)
        except Exception as e:
            messagebox.showerror("生成エラー", str(e)); return

        mel_text = self._mel_entry.get().strip()
        if mel_text:
            mel_steps = self._parse_melody_text(mel_text)
            self._events["melody"] = steps_to_events(mel_steps)
        else:
            self._events["melody"] = steps_to_events(gen["melody"])

        for v in ["mid","bass_high","bass_low"]:
            self._events[v] = steps_to_events(gen[v])
        for v in VOICES:
            self._score.update_voice(v, self._events[v])
        self._sv.set(f"生成完了: {' '.join(chord_names)}")

    def _on_export_midi(self):
        voices = {v: events_to_export_steps(self._events[v]) for v in VOICES}
        path   = export_midi(voices)
        if path: self._sv.set(f"MIDI出力: {path}")

    def _on_export_csv(self):
        chord_names = [cs.get_chord() for cs in self._chord_sel]
        chord_steps = chord_names_to_steps(chord_names)
        voices      = {v: events_to_export_steps(self._events[v]) for v in VOICES}
        path = export_csv(chord_steps, voices["melody"], voices["mid"],
                          voices["bass_high"], voices["bass_low"])
        if path: self._sv.set(f"CSV出力: {path}")

    # ================================================================ 起動時

    def _load_dummy(self):
        for i, cs in enumerate(self._chord_sel):
            cs.set_chord(DUMMY_CHORDS[i])
        tokens = [DUMMY_MELODY[i] for i in range(0, STEPS, 4)]
        self._mel_entry.insert(0, " ".join(tokens))
        self._events["melody"] = steps_to_events(DUMMY_MELODY)
        self._score.update_voice("melody", self._events["melody"])
        self._sv.set("ダミーデータ読込済み。「対旋律を自動生成」で対旋律を生成できます。")

    # ================================================================ ユーティリティ

    def _parse_melody_text(self, text: str) -> list[str]:
        steps: list[str] = []
        for tok in text.split():
            t = tok.strip()
            if t.lower() in ("blank", "r", "rest"):
                steps.extend(["R","blank","blank","blank"])
            else:
                try:
                    p = m21pitch.Pitch(t)
                    steps.extend([p.nameWithOctave,"blank","blank","blank"])
                except Exception:
                    steps.extend(["blank"]*4)
        steps = steps[:STEPS]
        while len(steps) < STEPS: steps.append("blank")
        return steps


def main():
    app = CounterpointApp()
    app.mainloop()


if __name__ == "__main__":
    main()
