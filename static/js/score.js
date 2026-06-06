// score.js — HTML Canvas 五線譜レンダラー（ト音/ヘ音記号・音符選択・ドラッグ・ズーム対応）

const SCORE = (() => {

// ── レイアウト定数 ──
const LINE_COUNT = 5;
const LINE_SP    = 11;
const STAFF_H    = LINE_SP * (LINE_COUNT - 1);  // 44
const CANVAS_H   = 104;
const MARGIN_TOP = 22;
const CLEF_W     = 52;
const PAD_R      = 12;

// ── 色 ──
const C = {
  bg:          "#ffffff",
  staff:       "#444",
  bar:         "#666",
  noteFill:    "#111",
  noteOpen:    "#ffffff",
  stem:        "#111",
  hlFill:      "#ffe066",
  overlapFill: "rgba(57, 255, 20, 0.28)",
  selBorder:   "#3498db",
  rest:        "#555",
  play:        "#27ae60",
  drag:        "#3498db",
  label:       "#999",
};

// ── 音高→Y座標 ──
const STEP_MAP = { C:0, D:1, E:2, F:3, G:4, A:5, B:6 };
const CLEF_REF = { treble: 30, bass: 18 };  // E4=30, G2=18

function absDia(pitchName) {
  const m = pitchName.match(/^([A-G])[#b]?(\d+)$/);
  if (!m) return 30;
  return parseInt(m[2]) * 7 + (STEP_MAP[m[1]] || 0);
}

function pitchToY(pitchName, clef, marginTop, staffH, lineSP) {
  const ref  = CLEF_REF[clef] || 30;
  const absD = absDia(pitchName);
  const botY = marginTop + staffH;
  return botY - (absD - ref) * (lineSP / 2);
}

// ════════════════════════════════════════════════
class ScoreCanvas {
  constructor(canvasEl, voiceName, clef, callbacks) {
    this.canvas   = canvasEl;
    this.ctx      = canvasEl.getContext("2d");
    this.voice    = voiceName;
    this.clef     = clef;
    this.events   = [];
    this.hlSteps      = new Set();
    this.selSteps     = new Set();
    this.overlapSteps = new Set();
    this.playStep = null;
    this.hitBoxes = [];
    // ズーム
    this.visibleSteps = 64;
    this.viewStart    = 0;

    this.onSelect     = callbacks.onSelect     || null;
    this.onDragSelect = callbacks.onDragSelect || null;
    this.onInsert     = callbacks.onInsert     || null;
    this.onResize     = callbacks.onResize     || null;
    this._lastClickTime = 0;

    this._drag       = null;
    this._dragRect   = null;
    this._resizeDrag = null; // { step, pitch, origDur, startX, curDur }

    this._bindEvents();
    this.render();
  }

  // ── 公開 API ──────────────────────────────────────
  setEvents(events, hlSteps = [], selSteps = new Set(), overlapSteps = new Set()) {
    this.events       = events || [];
    this.hlSteps      = new Set(hlSteps);
    this.selSteps     = selSteps;
    this.overlapSteps = overlapSteps;
    this.render();
  }

  setPlayStep(step) {
    this.playStep = step;
    this.render();
  }

  setView(viewStart, visibleSteps) {
    this.viewStart    = viewStart;
    this.visibleSteps = visibleSteps;
    this.render();
  }

  // ── マウスイベント ───────────────────────────────
  _relPos(e) {
    const r = this.canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  _xToStep(x) {
    return Math.max(0, Math.min(63,
      Math.floor((x - CLEF_W - 4) / this._stepW()) + this.viewStart
    ));
  }

  _findHitBox(x, y) {
    return this.hitBoxes.find(hb =>
      Math.abs(x - hb.cx) <= hb.rx + 4 && Math.abs(y - hb.cy) <= hb.ry + 6
    ) || null;
  }

  _bindEvents() {
    this._pendingClick = null;

    this.canvas.addEventListener("mousedown", e => {
      const p  = this._relPos(e);
      const hb = this._findHitBox(p.x, p.y);
      if (hb) {
        // 音符/休符上 → リサイズドラッグ開始
        this._resizeDrag = { step: hb.step, pitch: hb.pitch, origDur: hb.dur, startX: p.x, curDur: hb.dur };
        document.body.style.cursor = "ew-resize";
      } else {
        this._drag = p;
      }
      this._dragRect = null;
    });

    this.canvas.addEventListener("mousemove", e => {
      if (this._resizeDrag) {
        const p      = this._relPos(e);
        const sw     = this._stepW();
        const delta  = Math.round((p.x - this._resizeDrag.startX) / sw);
        this._resizeDrag.curDur = Math.max(1, this._resizeDrag.origDur + delta);
        this.render();
        return;
      }
      if (!this._drag) return;
      const p  = this._relPos(e);
      const dx = Math.abs(p.x - this._drag.x);
      if (dx > 5) {
        this._dragRect = {
          x1: Math.min(this._drag.x, p.x),
          x2: Math.max(this._drag.x, p.x),
        };
        this.render();
      }
    });

    this.canvas.addEventListener("mouseup", e => {
      // ── リサイズ終了 ──
      if (this._resizeDrag) {
        const rd = this._resizeDrag;
        const p  = this._relPos(e);
        const dx = Math.abs(p.x - rd.startX);
        this._resizeDrag = null;
        document.body.style.cursor = "";

        if (dx < 6) {
          // ほぼ動かなかった → 通常クリック（選択/ダブルクリック）
          const now = Date.now();
          if (this._lastClickTime && now - this._lastClickTime < 300) {
            clearTimeout(this._pendingClick);
            this._pendingClick  = null;
            this._lastClickTime = 0;
            if (this.onInsert) this.onInsert(this.voice, rd.step);
          } else {
            this._lastClickTime = now;
            const { step, pitch, origDur } = rd;
            this._pendingClick = setTimeout(() => {
              this._pendingClick = null;
              if (this.onSelect) this.onSelect(this.voice, step, pitch, origDur, false);
            }, 300);
          }
        } else if (rd.curDur !== rd.origDur) {
          // 長さが変わった → リサイズ確定
          if (this.onResize) this.onResize(this.voice, rd.step, rd.curDur);
        }
        this.render();
        return;
      }

      // ── 既存のクリック/範囲選択 ──
      if (!this._drag) return;
      const p      = this._relPos(e);
      const dx     = Math.abs(p.x - this._drag.x);
      const isCtrl = e.ctrlKey || e.metaKey;
      if (dx < 6) {
        const now = Date.now();
        if (this._lastClickTime && now - this._lastClickTime < 300) {
          clearTimeout(this._pendingClick);
          this._pendingClick  = null;
          this._lastClickTime = 0;
          const stepI = this._xToStep(p.x);
          if (this.onInsert) this.onInsert(this.voice, stepI, p.x, p.y);
        } else {
          this._lastClickTime = now;
          const px = p.x, py = p.y;
          this._pendingClick = setTimeout(() => {
            this._pendingClick = null;
            this._handleClick(px, py, isCtrl);
          }, 300);
        }
      } else {
        const x1 = Math.min(this._drag.x, p.x);
        const x2 = Math.max(this._drag.x, p.x);
        this._handleDrag(x1, x2);
      }
      this._drag = null;
      this._dragRect = null;
      this.render();
    });
  }

  _handleClick(x, y, isCtrl = false) {
    for (const hb of this.hitBoxes) {
      if (Math.abs(x - hb.cx) <= hb.rx + 4 && Math.abs(y - hb.cy) <= hb.ry + 6) {
        if (isCtrl) {
          // 同じ声部内でトグル選択
          if (this.selSteps.has(hb.step)) {
            const next = new Set(this.selSteps);
            next.delete(hb.step);
            this.selSteps = next;
          } else {
            this.selSteps = new Set([...this.selSteps, hb.step]);
          }
        } else {
          this.selSteps = new Set([hb.step]);
        }
        this.render();
        if (this.onSelect) this.onSelect(this.voice, hb.step, hb.pitch, hb.dur, isCtrl);
        return;
      }
    }
    // 空欄クリック: Ctrl なしのときだけ選択解除
    if (!isCtrl) {
      const stepI = this._xToStep(x);
      this.selSteps = new Set();
      this.render();
      if (this.onSelect) this.onSelect(this.voice, stepI, "blank", 0, false);
    }
  }

  _handleDrag(x1, x2) {
    const sel = this.hitBoxes.filter(hb => hb.cx >= x1 && hb.cx <= x2);
    this.selSteps = new Set(sel.map(s => s.step));
    this.render();
    if (this.onDragSelect && sel.length > 0)
      this.onDragSelect(this.voice, sel.map(hb => ({ step: hb.step, pitch: hb.pitch, dur: hb.dur })));
  }

  // ── レンダリング ─────────────────────────────────
  _stepW() {
    return (this.canvas.width - CLEF_W - 4 - PAD_R) / this.visibleSteps;
  }

  render() {
    const ctx  = this.ctx;
    const W    = this.canvas.width;
    const vEnd = this.viewStart + this.visibleSteps;

    ctx.clearRect(0, 0, W, CANVAS_H);
    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, CANVAS_H);

    this.hitBoxes = [];
    this._drawStaff();

    const x0    = CLEF_W + 4;
    const stepW = this._stepW();

    // 再生カーソル
    if (this.playStep !== null && this.playStep >= this.viewStart && this.playStep < vEnd) {
      ctx.strokeStyle = C.play; ctx.lineWidth = 2;
      const px = x0 + (this.playStep - this.viewStart) * stepW;
      ctx.beginPath(); ctx.moveTo(px, MARGIN_TOP); ctx.lineTo(px, MARGIN_TOP + STAFF_H); ctx.stroke();
    }

    // ドラッグ矩形
    if (this._dragRect) {
      ctx.strokeStyle = C.drag; ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.strokeRect(this._dragRect.x1, MARGIN_TOP,
                     this._dragRect.x2 - this._dragRect.x1, STAFF_H);
      ctx.setLineDash([]);
    }

    // イベント描画（表示範囲内のみ）
    for (const ev of this.events) {
      if (ev.step + ev.dur <= this.viewStart) continue;
      if (ev.step >= vEnd) continue;
      // リサイズ中は仮の長さでプレビュー描画
      const renderDur = (this._resizeDrag && ev.step === this._resizeDrag.step)
        ? this._resizeDrag.curDur : ev.dur;
      if (ev.pitch === "R") this._drawRest(ev.step, renderDur, stepW, x0);
      else                  this._drawNote(ev.step, renderDur, ev.pitch, stepW, x0);
    }

  }

  _drawStaff() {
    const ctx = this.ctx;
    const W   = this.canvas.width;
    ctx.strokeStyle = C.staff; ctx.lineWidth = 1;
    for (let ln = 0; ln < LINE_COUNT; ln++) {
      const y = MARGIN_TOP + ln * LINE_SP;
      ctx.beginPath(); ctx.moveTo(CLEF_W, y); ctx.lineTo(W - PAD_R, y); ctx.stroke();
    }
    ctx.fillStyle = C.staff;
    if (this.clef === "treble") {
      ctx.font = `52px "Segoe UI Symbol","Noto Music",serif`;
      ctx.textBaseline = "bottom";
      ctx.fillText("\u{1D11E}", CLEF_W / 2 - 12, MARGIN_TOP + STAFF_H + 10);
    } else {
      ctx.font = `28px "Segoe UI Symbol","Noto Music",serif`;
      ctx.textBaseline = "top";
      ctx.fillText("\u{1D122}", 4, MARGIN_TOP + LINE_SP + 2);
    }
    ctx.textBaseline = "alphabetic";
  }

  _drawNote(stepI, dur, pitch, stepW, x0) {
    const ctx = this.ctx;
    const cx  = x0 + (stepI - this.viewStart) * stepW + 9;
    let cy;
    try { cy = pitchToY(pitch, this.clef, MARGIN_TOP, STAFF_H, LINE_SP); }
    catch { return; }

    const rx       = 6;
    const ry       = 4;
    const isWhole  = dur >= 16;
    const isHalf   = dur >= 8 && !isWhole;  // 2分音符のみ中抜き（全音符は別処理）
    const isHollow = dur >= 8;              // 全音符・2分音符は中抜き
    const isHL     = [...this.hlSteps].some(s => s >= stepI && s < stepI + dur);
    const isSel    = this.selSteps.has(stepI);
    const multiSel = this.selSteps.size > 1;

    // 重複HL背景（緑）
    if (this.overlapSteps.has(stepI)) {
      ctx.fillStyle = C.overlapFill;
      ctx.fillRect(x0 + (stepI - this.viewStart) * stepW, MARGIN_TOP, dur * stepW, STAFF_H);
    }
    // HL 背景（黄）
    if (isHL) {
      ctx.fillStyle = C.hlFill;
      ctx.fillRect(x0 + (stepI - this.viewStart) * stepW, MARGIN_TOP, dur * stepW, STAFF_H);
    }

    // 加線
    this._drawLedger(cx, pitch, rx + 5);

    // ── 音符頭 ──
    ctx.beginPath();
    if (isWhole) {
      // 全音符: やや横長・中抜き楕円
      ctx.ellipse(cx, cy, rx + 3, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle   = C.noteOpen;   ctx.fill();
      ctx.strokeStyle = C.noteFill;   ctx.lineWidth = 2; ctx.stroke();
      // 中央の穴（楕円の内側を白く）
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx - 1, ry - 2, 0.4, 0, Math.PI * 2);
      ctx.fillStyle = C.noteOpen; ctx.fill();
    } else if (isHalf) {
      // 2分音符: 普通サイズ・中抜き
      ctx.ellipse(cx, cy, rx, ry, -0.25, 0, Math.PI * 2);
      ctx.fillStyle   = C.noteOpen; ctx.fill();
      ctx.strokeStyle = C.noteFill; ctx.lineWidth = 2; ctx.stroke();
    } else {
      // 4分・8分・16分音符: 塗りつぶし・やや斜め楕円
      ctx.ellipse(cx, cy, rx, ry, -0.25, 0, Math.PI * 2);
      ctx.fillStyle = C.noteFill; ctx.fill();
    }

    // 選択枠（青○）
    if (isSel) {
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx + 3, ry + 3, 0, 0, Math.PI * 2);
      ctx.strokeStyle = C.selBorder;
      ctx.lineWidth   = multiSel ? 2 : 3;
      ctx.stroke();
    }

    // ── 符幹 + フラグ ──
    if (!isWhole) {
      const sLen     = LINE_SP * 3.2;
      const stemUp   = cy > MARGIN_TOP + STAFF_H / 2;
      const stemX    = stemUp ? cx + rx - 1 : cx - rx + 1;
      const stemTipY = stemUp ? cy - sLen : cy + sLen;

      ctx.strokeStyle = C.stem; ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(stemX, cy);
      ctx.lineTo(stemX, stemTipY);
      ctx.stroke();

      // フラグ: 8分音符=1本、16分音符=2本（2次ベジェでループなし）
      if (dur <= 2) {
        const flagCount = dur <= 1 ? 2 : 1;
        ctx.lineWidth = 1.8;
        for (let f = 0; f < flagCount; f++) {
          const fy = stemTipY + f * (stemUp ? 9 : -9);
          ctx.beginPath();
          ctx.moveTo(stemX, fy);
          if (stemUp) {
            // 制御点を右に、終点を右下へ → 外向きの弧
            ctx.quadraticCurveTo(stemX + 18, fy + 7, stemX + 6, fy + 18);
          } else {
            ctx.quadraticCurveTo(stemX + 18, fy - 7, stemX + 6, fy - 18);
          }
          ctx.stroke();
        }
      }
    }

    // 付点
    if ([12, 6, 3].includes(dur)) {
      ctx.fillStyle = C.noteFill;
      ctx.beginPath(); ctx.arc(cx + rx + 6, cy - 1, 2, 0, Math.PI * 2); ctx.fill();
    }

    // ♯記号（音符の右横）
    if (pitch.includes('#')) {
      ctx.fillStyle = C.noteFill;
      ctx.font = "bold 11px Arial";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText("♯", cx + rx + 10, cy);
      ctx.textBaseline = "alphabetic";
    }

    // 音名ラベル
    ctx.fillStyle = C.label; ctx.font = "9px Arial"; ctx.textAlign = "center";
    ctx.fillText(pitch, cx, cy - ry - 5); ctx.textAlign = "left";

    this.hitBoxes.push({ step: stepI, pitch, dur, cx, cy, rx: rx + 4, ry: ry + 6 });
  }

  _drawRest(stepI, dur, stepW, x0) {
    const ctx   = this.ctx;
    const cw    = Math.max(stepW * dur, 8);
    const cx    = x0 + (stepI - this.viewStart) * stepW + cw / 2;
    const midY  = MARGIN_TOP + LINE_SP * 2;
    const top2Y = MARGIN_TOP + LINE_SP;
    const isSel = this.selSteps.has(stepI);
    const multi = this.selSteps.size > 1;

    if (isSel) {
      ctx.strokeStyle = C.selBorder; ctx.lineWidth = multi ? 1 : 2;
      ctx.strokeRect(x0 + (stepI - this.viewStart) * stepW, MARGIN_TOP, dur * stepW, STAFF_H);
    }

    ctx.fillStyle = C.rest; ctx.strokeStyle = C.rest; ctx.lineWidth = 2;

    if (dur >= 16) {
      // 全休符: 第2線に吊るす黒い長方形
      ctx.fillRect(cx - 8, top2Y, 16, 5);
    } else if (dur >= 8) {
      // 2分休符: 第3線に乗せる黒い長方形
      ctx.fillRect(cx - 8, midY - 5, 16, 5);
    } else if (dur >= 4) {
      // 4分休符: 鍵型
      const y0 = midY - 7;
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(cx + 4, y0);
      ctx.lineTo(cx - 3, y0 + 4);
      ctx.lineTo(cx + 4, y0 + 8);
      ctx.lineTo(cx - 4, y0 + 13);
      ctx.stroke();
      ctx.beginPath(); ctx.arc(cx - 2, y0 + 15, 2.5, 0, Math.PI * 2); ctx.fill();
    } else if (dur >= 2) {
      // 8分休符
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx - 1, midY - 5); ctx.lineTo(cx + 4, midY + 2); ctx.stroke();
      ctx.beginPath(); ctx.arc(cx + 3, midY + 2, 2.5, 0, Math.PI * 2); ctx.fill();
    } else {
      // 16分休符
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(cx, midY - 4); ctx.lineTo(cx, midY + 4); ctx.stroke();
    }

    if ([12, 6, 3].includes(dur)) {
      ctx.beginPath(); ctx.arc(cx + 9, midY, 2, 0, Math.PI * 2); ctx.fill();
    }

    this.hitBoxes.push({ step: stepI, pitch: "R", dur, cx, cy: midY, rx: cw / 2, ry: 12 });
  }

  _drawLedger(cx, pitchName, hw) {
    const ctx  = this.ctx;
    const ref  = CLEF_REF[this.clef] || 30;
    const rel  = absDia(pitchName) - ref;
    const botY = MARGIN_TOP + STAFF_H;
    ctx.strokeStyle = C.staff; ctx.lineWidth = 1;
    if (rel < 0) {
      for (let s = -2; s >= rel; s -= 2) {
        const y = botY - s * (LINE_SP / 2);
        ctx.beginPath(); ctx.moveTo(cx - hw, y); ctx.lineTo(cx + hw, y); ctx.stroke();
      }
    }
    if (rel > 8) {
      for (let s = 10; s <= rel; s += 2) {
        const y = botY - s * (LINE_SP / 2);
        ctx.beginPath(); ctx.moveTo(cx - hw, y); ctx.lineTo(cx + hw, y); ctx.stroke();
      }
    }
  }
}

// ──── 複数 ScoreCanvas 管理 ──────────────────────────────────
const VOICE_META = [
  { voice: "melody",    label: "主旋律",   clef: "treble" },
  { voice: "mid",       label: "中音域",   clef: "treble" },
  { voice: "bass_high", label: "低音域",   clef: "bass"   },
  { voice: "bass_low",  label: "超低音域", clef: "bass"   },
];

function createScorePanel(containerEl, callbacks) {
  const canvases = {};
  containerEl.innerHTML = "";

  for (const meta of VOICE_META) {
    const row     = document.createElement("div");
    row.className = "voice-row";

    const lbl         = document.createElement("div");
    lbl.className     = "voice-label";
    lbl.textContent   = meta.label;

    const cvs         = document.createElement("canvas");
    cvs.className     = "voice-canvas";
    cvs.height        = 104;

    row.appendChild(lbl);
    row.appendChild(cvs);
    containerEl.appendChild(row);

    const sc = new ScoreCanvas(cvs, meta.voice, meta.clef, {
      onSelect:     callbacks.onSelect,
      onDragSelect: callbacks.onDragSelect,
      onInsert:     callbacks.onInsert,
      onResize:     callbacks.onResize,
    });
    canvases[meta.voice] = sc;
  }

  function resize() {
    for (const sc of Object.values(canvases)) {
      sc.canvas.width = sc.canvas.parentElement.clientWidth - 70 - 2;
      sc.render();
    }
  }
  const ro = new ResizeObserver(resize);
  ro.observe(containerEl);
  setTimeout(resize, 50);

  return {
    canvases,
    update(voice, events, hlSteps, selSteps, overlapSteps = new Set()) {
      if (canvases[voice]) canvases[voice].setEvents(events, hlSteps, selSteps, overlapSteps);
    },
    setPlayStep(step) {
      for (const sc of Object.values(canvases)) sc.setPlayStep(step);
    },
    setSelected(voice, selSteps) {
      for (const [v, sc] of Object.entries(canvases))
        sc.selSteps = v === voice ? selSteps : new Set();
      if (canvases[voice]) canvases[voice].render();
    },
    clearSelected() {
      for (const sc of Object.values(canvases)) {
        sc.selSteps = new Set(); sc.render();
      }
    },
    renderAll() {
      for (const sc of Object.values(canvases)) sc.render();
    },
    setView(viewStart, visibleSteps) {
      for (const sc of Object.values(canvases)) sc.setView(viewStart, visibleSteps);
    },
  };
}

return { createScorePanel, VOICE_META };

})(); // SCORE IIFE
