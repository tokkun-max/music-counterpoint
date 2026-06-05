# Tkinter Canvas で五線譜を描画するモジュール（複数選択・ドラッグ・休符・ヘ音記号対応）

import tkinter as tk
from music21 import pitch as m21pitch
from note_utils import STEPS, dur_label

# ---- レイアウト定数 ----
LINE_COUNT = 5
LINE_SP    = 11
STAFF_H    = LINE_SP * (LINE_COUNT - 1)   # 44px
CANVAS_H   = 104
MARGIN_TOP = 22
CLEF_W     = 52
PAD_R      = 12

BG         = "#ffffff"
STAFF_C    = "#444444"
BAR_C      = "#666666"
NOTE_FILL  = "#111111"
NOTE_OPEN  = "#ffffff"
STEM_C     = "#111111"
HL_FILL    = "#ffe066"
HL_BORDER  = "#f0a500"
SEL_BORDER = "#3498db"      # 選択中（仕様書準拠：青）
SEL_MULTI  = "#74b9ff"      # 複数選択（薄い青）
SEL_FILL   = "#ebf5fb"      # 選択範囲の背景（薄い青）
REST_C     = "#555555"
PLAY_C     = "#27ae60"      # 再生カーソル（緑）
DRAG_C     = "#3498db"      # ドラッグ矩形（青破線）

_SYMBOL_FONTS = ["Segoe UI Symbol", "MS Gothic", "Arial Unicode MS", "Arial"]
_STEP_MAP     = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}


def _abs_dia(pitch_name: str) -> int:
    p = m21pitch.Pitch(pitch_name)
    return (p.octave or 4) * 7 + _STEP_MAP.get(p.step, 0)


CLEF_REF = {"treble": _abs_dia("E4"), "bass": _abs_dia("G2")}


def _pitch_to_y(pitch_name: str, clef: str) -> float:
    ref   = CLEF_REF[clef]
    abs_d = _abs_dia(pitch_name)
    bot_y = MARGIN_TOP + STAFF_H
    return bot_y - (abs_d - ref) * (LINE_SP / 2)


# =====================================================================
class ScoreCanvas(tk.Frame):
    """1声部の五線譜キャンバス（複数選択・ドラッグ対応）。"""

    NOTE_RX, NOTE_RY = 6, 4

    def __init__(self, master, label: str, clef: str = "treble",
                 on_select=None, on_drag_select=None, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self.clef           = clef
        self._events: list[dict] = []
        self._hl:     set[int]   = set()      # 度数ハイライト対象 step
        self._sel:    set[int]   = set()      # 選択中 step（複数可）
        self._play_step: int | None = None
        self._hit_boxes: list[tuple] = []     # (step, pitch, dur, cx, cy, rx, ry)
        self._on_select      = on_select      # (step, pitch, dur)
        self._on_drag_select = on_drag_select # (list[(step,pitch,dur)])
        self._drag_start: tuple | None = None
        self._drag_rect_id   = None
        self._drag_threshold = 6              # ドラッグ判定ピクセル

        lbl = tk.Label(self, text=label, font=("Arial", 9, "bold"),
                       bg="#eeeeee", fg="#333", width=9, anchor="e", padx=4)
        lbl.pack(side="left", fill="y")

        self.canvas = tk.Canvas(self, height=CANVAS_H, bg=BG,
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>",        lambda e: self._render())
        self.canvas.bind("<Button-1>",         self._on_btn_down)
        self.canvas.bind("<B1-Motion>",        self._on_btn_drag)
        self.canvas.bind("<ButtonRelease-1>",  self._on_btn_up)
        self._draw_staff()

    # ---------------------------------------------------------------- API

    def set_events(self, events: list[dict], hl_steps: list[int] | None = None):
        self._events = events or []
        self._hl     = set(hl_steps or [])
        self._render()

    def set_selected_steps(self, steps: set[int]):
        self._sel = steps
        self._render()

    def set_play_cursor(self, step: int | None):
        self._play_step = step
        self._render()

    def clear(self):
        self._events = []
        self._hl     = set()
        self._sel    = set()
        self._draw_staff()

    def get_step_at_x(self, x: float) -> int:
        """ピクセル X 座標からステップ番号を返す。"""
        cw     = self._cw()
        x0     = CLEF_W + 4
        aw     = cw - x0 - PAD_R
        step_w = aw / STEPS
        return max(0, min(63, int((x - x0) / step_w)))

    # ---------------------------------------------------------------- マウス

    def _on_btn_down(self, event):
        self._drag_start = (event.x, event.y)

    def _on_btn_drag(self, event):
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        dx = abs(event.x - x0)
        if dx < self._drag_threshold:
            return
        # ラバーバンド矩形を描画
        if self._drag_rect_id:
            self.canvas.delete(self._drag_rect_id)
        self._drag_rect_id = self.canvas.create_rectangle(
            min(x0, event.x), MARGIN_TOP,
            max(x0, event.x), MARGIN_TOP + STAFF_H,
            outline=DRAG_C, dash=(4, 3), width=1, fill="",
        )

    def _on_btn_up(self, event):
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        if self._drag_rect_id:
            self.canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None
        dx = abs(event.x - x0)
        self._drag_start = None

        if dx < self._drag_threshold:
            self._handle_click(event.x, event.y)
        else:
            self._handle_drag_select(min(x0, event.x), max(x0, event.x))

    def _handle_click(self, x: float, y: float):
        hit = None
        for box in self._hit_boxes:
            step, pitch, dur, cx, cy, rx, ry = box
            if abs(x - cx) <= rx + 4 and abs(y - cy) <= ry + 6:
                hit = box
                break
        if hit:
            step, pitch, dur = hit[0], hit[1], hit[2]
            self._sel = {step}
            self._render()
            if self._on_select:
                self._on_select(step, pitch, dur)
        else:
            step_i = self.get_step_at_x(x)
            self._sel = set()
            self._render()
            if self._on_select:
                self._on_select(step_i, "blank", 0)

    def _handle_drag_select(self, x_min: float, x_max: float):
        selected = []
        for box in self._hit_boxes:
            step, pitch, dur, cx, cy, rx, ry = box
            if x_min <= cx <= x_max:
                selected.append((step, pitch, dur))
        self._sel = {s[0] for s in selected}
        self._render()
        if self._on_drag_select and selected:
            self._on_drag_select(selected)

    # ---------------------------------------------------------------- 描画

    def _cw(self) -> int:
        w = self.canvas.winfo_width()
        return w if w > 80 else 900

    def _render(self):
        self.canvas.delete("all")
        self._hit_boxes.clear()
        self._draw_staff()

        cw     = self._cw()
        x0     = CLEF_W + 4
        aw     = cw - x0 - PAD_R
        step_w = aw / STEPS

        # 小節線
        for m in range(5):
            x = x0 + m * 16 * step_w
            self.canvas.create_line(x, MARGIN_TOP, x, MARGIN_TOP + STAFF_H,
                                    fill=BAR_C, width=1)
        # 再生カーソル
        if self._play_step is not None:
            px = x0 + self._play_step * step_w
            self.canvas.create_line(px, MARGIN_TOP, px, MARGIN_TOP + STAFF_H,
                                    fill=PLAY_C, width=2)
        # イベント描画
        for ev in self._events:
            s     = ev["step"]
            pitch = ev["pitch"]
            dur   = ev["dur"]
            if pitch == "R":
                self._draw_rest(s, dur, step_w, x0)
            else:
                self._draw_note(s, dur, pitch, step_w, x0)

    def _draw_staff(self):
        cw = self._cw()
        for ln in range(LINE_COUNT):
            y = MARGIN_TOP + ln * LINE_SP
            self.canvas.create_line(CLEF_W, y, cw - PAD_R, y,
                                    fill=STAFF_C, width=1)
        self._draw_clef_sym()

    def _draw_clef_sym(self):
        mid_x = CLEF_W // 2
        if self.clef == "treble":
            char, size, y_ref, anch = "\U0001D11E", 52, MARGIN_TOP + STAFF_H + 8, "s"
        else:
            char, size, y_ref, anch = "\U0001D122", 28, MARGIN_TOP + LINE_SP + 2, "nw"
            mid_x = 4
        for fname in _SYMBOL_FONTS:
            try:
                self.canvas.create_text(mid_x, y_ref, text=char,
                                        font=(fname, size), anchor=anch,
                                        fill=STAFF_C)
                return
            except Exception:
                continue

    def _draw_note(self, step_i: int, dur: int, pitch: str,
                   step_w: float, x0: float):
        try:
            cy = _pitch_to_y(pitch, self.clef)
        except Exception:
            return

        cw_note  = max(step_w * dur, 14)
        cx       = x0 + step_i * step_w + cw_note / 2
        rx, ry   = self.NOTE_RX, self.NOTE_RY
        is_half  = dur >= 8
        is_whole = dur >= 16
        is_hl    = bool(self._hl & set(range(step_i, step_i + dur)))
        is_sel   = step_i in self._sel

        # ハイライト背景
        if is_hl:
            self.canvas.create_rectangle(
                x0 + step_i * step_w, MARGIN_TOP,
                x0 + (step_i + dur) * step_w, MARGIN_TOP + STAFF_H,
                fill=HL_FILL, outline=HL_BORDER,
            )

        # 加線
        self._draw_ledger(cx, pitch, rx + 5)

        # 音符楕円
        fill    = NOTE_OPEN if is_half else NOTE_FILL
        outline = NOTE_FILL
        self.canvas.create_oval(cx - rx, cy - ry, cx + rx, cy + ry,
                                fill=fill, outline=outline, width=2 if is_half else 1)

        # 選択枠（青：仕様書準拠）
        if is_sel:
            w = 3 if len(self._sel) == 1 else 2
            c = SEL_BORDER if len(self._sel) == 1 else SEL_MULTI
            # 選択範囲の薄い青背景
            if not is_hl:   # ハイライトと重複しないとき
                self.canvas.create_rectangle(
                    x0 + step_i * step_w, MARGIN_TOP,
                    x0 + (step_i + dur) * step_w, MARGIN_TOP + STAFF_H,
                    fill=SEL_FILL, outline="",
                )
            self.canvas.create_oval(cx - rx - 3, cy - ry - 3,
                                    cx + rx + 3, cy + ry + 3,
                                    outline=c, width=w, fill="")

        # 符幹
        if not is_whole:
            stem_len = LINE_SP * 3
            if cy > MARGIN_TOP + STAFF_H / 2:
                self.canvas.create_line(cx + rx - 1, cy, cx + rx - 1, cy - stem_len,
                                        fill=STEM_C, width=1)
            else:
                self.canvas.create_line(cx - rx + 1, cy, cx - rx + 1, cy + stem_len,
                                        fill=STEM_C, width=1)

        # 付点
        if dur in (12, 6, 3):
            self.canvas.create_oval(cx + rx + 3, cy - 2, cx + rx + 7, cy + 2,
                                    fill=NOTE_FILL, outline=NOTE_FILL)

        # 音名ラベル
        self.canvas.create_text(cx, cy - ry - 9, text=pitch,
                                font=("Arial", 6), fill="#666")

        self._hit_boxes.append((step_i, pitch, dur, cx, cy, rx + 4, ry + 6))

    def _draw_rest(self, step_i: int, dur: int, step_w: float, x0: float):
        cw_rest = max(step_w * dur, 8)
        cx      = x0 + step_i * step_w + cw_rest / 2
        is_sel  = step_i in self._sel
        mid_y   = MARGIN_TOP + LINE_SP * 2
        top2_y  = MARGIN_TOP + LINE_SP

        if is_sel:
            c = SEL_BORDER if len(self._sel) == 1 else SEL_MULTI
            self.canvas.create_rectangle(
                x0 + step_i * step_w, MARGIN_TOP,
                x0 + (step_i + dur) * step_w, MARGIN_TOP + STAFF_H,
                fill=HL_FILL, outline=c, width=2 if len(self._sel)==1 else 1,
            )

        # 音価に応じた休符記号
        if dur >= 16:
            self.canvas.create_rectangle(cx - 8, top2_y, cx + 8, top2_y + 4,
                                         fill=REST_C, outline=REST_C)
        elif dur >= 8:
            self.canvas.create_rectangle(cx - 8, mid_y - 4, cx + 8, mid_y,
                                         fill=REST_C, outline=REST_C)
        elif dur >= 4:
            y0 = mid_y - 6
            self.canvas.create_line(cx + 5, y0, cx - 5, y0 + 4, fill=REST_C, width=2)
            self.canvas.create_line(cx - 5, y0 + 4, cx + 5, y0 + 8, fill=REST_C, width=2)
            self.canvas.create_line(cx + 5, y0 + 8, cx - 5, y0 + 12, fill=REST_C, width=2)
        elif dur >= 2:
            self.canvas.create_line(cx - 2, mid_y - 4, cx + 4, mid_y + 4, fill=REST_C, width=2)
            self.canvas.create_oval(cx + 2, mid_y + 2, cx + 6, mid_y + 6,
                                    fill=REST_C, outline=REST_C)
        else:
            self.canvas.create_line(cx, mid_y - 3, cx, mid_y + 3, fill=REST_C, width=2)

        if dur in (12, 6, 3):
            self.canvas.create_oval(cx + 9, mid_y - 2, cx + 13, mid_y + 2,
                                    fill=REST_C, outline=REST_C)

        self._hit_boxes.append((step_i, "R", dur, cx, mid_y, cw_rest / 2, 12))

    def _draw_ledger(self, cx: float, pitch_name: str, hw: float):
        ref = CLEF_REF[self.clef]
        try:
            abs_d = _abs_dia(pitch_name)
        except Exception:
            return
        rel   = abs_d - ref
        bot_y = MARGIN_TOP + STAFF_H
        if rel < 0:
            s = -2
            while s >= rel:
                y = bot_y - s * (LINE_SP / 2)
                self.canvas.create_line(cx - hw, y, cx + hw, y, fill=STAFF_C)
                s -= 2
        if rel > 8:
            s = 10
            while s <= rel:
                y = bot_y - s * (LINE_SP / 2)
                self.canvas.create_line(cx - hw, y, cx + hw, y, fill=STAFF_C)
                s += 2


# =====================================================================
class MultiScorePanel(tk.Frame):
    """4声部の五線譜パネル（主旋律=ト音、他=ヘ音）。"""

    VOICE_META = {
        "melody":    ("主旋律",   "treble"),
        "mid":       ("中音域",   "bass"),
        "bass_high": ("低音域",   "bass"),
        "bass_low":  ("超低音域", "bass"),
    }
    VOICE_ORDER = ["melody", "mid", "bass_high", "bass_low"]

    def __init__(self, master, on_note_select=None, on_drag_select=None, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self._canvases: dict[str, ScoreCanvas] = {}
        self._on_note_select = on_note_select   # (voice, step, pitch, dur)
        self._on_drag_select = on_drag_select   # (voice, list[(step,pitch,dur)])

        for voice in self.VOICE_ORDER:
            label, clef = self.VOICE_META[voice]
            tk.Frame(self, height=1, bg="#cccccc").pack(fill="x")
            sc = ScoreCanvas(
                self, label=label, clef=clef,
                on_select=self._make_select_cb(voice),
                on_drag_select=self._make_drag_cb(voice),
            )
            sc.pack(fill="x", pady=2)
            self._canvases[voice] = sc

    def _make_select_cb(self, voice: str):
        def cb(step, pitch, dur):
            for v, sc in self._canvases.items():
                if v != voice:
                    sc.set_selected_steps(set())
            if self._on_note_select:
                self._on_note_select(voice, step, pitch, dur)
        return cb

    def _make_drag_cb(self, voice: str):
        def cb(selections):
            for v, sc in self._canvases.items():
                if v != voice:
                    sc.set_selected_steps(set())
            if self._on_drag_select:
                self._on_drag_select(voice, selections)
        return cb

    def update_voice(self, voice: str, events: list[dict],
                     hl_steps: list[int] | None = None):
        if voice in self._canvases:
            self._canvases[voice].set_events(events, hl_steps)

    def set_selected(self, voice: str, steps: set[int]):
        for v, sc in self._canvases.items():
            sc.set_selected_steps(steps if v == voice else set())

    def set_play_cursor(self, step: int | None):
        for sc in self._canvases.values():
            sc.set_play_cursor(step)

    def clear_voice(self, voice: str):
        if voice in self._canvases:
            self._canvases[voice].clear()
