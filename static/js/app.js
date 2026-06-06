// app.js — 対旋律作成ツール Web版 メインアプリケーション

// ═══════════════════════════════════════════════════════
//  定数
// ═══════════════════════════════════════════════════════

const VOICES     = ["melody","mid","bass_high","bass_low"];
const V_LABELS   = { melody:"主旋律", mid:"中音域", bass_high:"低音域", bass_low:"超低音域" };
const ROOTS      = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
const QUALITIES  = {"":" maj","m":"m","7":"7","maj7":"maj7","m7":"m7",
                    "dim":"dim","aug":"aug","sus4":"sus4","cont":"ー延長"};
const MAX_UNDO   = 50;

const CHORD_SLOT_LABELS = ["1.1","1.3","2.1","2.3","3.1","3.3","4.1","4.3"];
const DUMMY_CHORDS  = ["Dm","G","C","Am","C","cont","Am","cont"];
const DUMMY_MELODY_NOTES = ["C4","D4","E4","F4","G4","A4","B4","C5",
                             "D5","E5","F5","G5","A5","B5","C6","C5"];

// ═══════════════════════════════════════════════════════
//  アプリ状態
// ═══════════════════════════════════════════════════════

const state = {
  voices:       Object.fromEntries(VOICES.map(v => [v, []])),
  chords:       [...DUMMY_CHORDS],
  selVoice:     null,
  selSteps:     new Set(),
  selEv:        null,
  hlActive:     false,
  hlVA:         "melody",
  hlVB:         "mid",
  hlDeg:        3,
  hlIndices:    [],
  olVA:         "melody",
  olVB:         "mid",
  olIndices:    [],
  clipboard:    null,
  undoStack:    [],
  isPlaying:    false,
  playStep:     null,
};

// ═══════════════════════════════════════════════════════
//  Audio (Tone.js サラマンダーピアノ)
// ═══════════════════════════════════════════════════════

let piano = null;
let pianoReady = false;

async function initAudio() {
  if (piano) return;
  try {
    piano = new Tone.Sampler({
      urls: {
        A0:"A0.mp3", C1:"C1.mp3","D#1":"Ds1.mp3","F#1":"Fs1.mp3",
        A1:"A1.mp3", C2:"C2.mp3","D#2":"Ds2.mp3","F#2":"Fs2.mp3",
        A2:"A2.mp3", C3:"C3.mp3","D#3":"Ds3.mp3","F#3":"Fs3.mp3",
        A3:"A3.mp3", C4:"C4.mp3","D#4":"Ds4.mp3","F#4":"Fs4.mp3",
        A4:"A4.mp3", C5:"C5.mp3","D#5":"Ds5.mp3","F#5":"Fs5.mp3",
        A5:"A5.mp3", C6:"C6.mp3","D#6":"Ds6.mp3","F#6":"Fs6.mp3",
        A6:"A6.mp3", C7:"C7.mp3","D#7":"Ds7.mp3","F#7":"Fs7.mp3",
        A7:"A7.mp3", C8:"C8.mp3",
      },
      baseUrl: "https://tonejs.github.io/audio/salamander/",
      onload: () => { pianoReady = true; setStatus("ピアノ音源読み込み完了。再生できます。"); },
      onerror: () => {
        // フォールバック: PolySynth
        piano = new Tone.PolySynth(Tone.Synth, {
          oscillator: { type: "triangle4" },
          envelope:   { attack:0.02, decay:0.1, sustain:0.6, release:1.2 },
        }).toDestination();
        pianoReady = true;
        setStatus("オフライン: シンセサイザー音で再生します。");
      }
    }).toDestination();
  } catch(e) {
    piano = new Tone.PolySynth(Tone.Synth).toDestination();
    pianoReady = true;
  }
}

async function startPlayback() {
  await Tone.start();
  if (!pianoReady) { setStatus("音源読み込み中..."); await initAudio(); }

  Tone.getTransport().cancel();
  Tone.getTransport().stop();
  Tone.getTransport().bpm.value = 120;

  const stepSecs = Tone.Time("16n").toSeconds();

  // 全声部のノートをスケジュール
  for (const voice of VOICES) {
    const steps  = eventsToExportSteps(state.voices[voice]);
    const active = { note: null };

    steps.forEach((pitch, i) => {
      const t  = i * stepSecs;
      const np = normalizePitch(pitch);
      if (np && np !== "blank" && np !== "R") {
        Tone.getTransport().schedule(time => {
          if (active.note) { try { piano.triggerRelease(active.note, time); } catch{} }
          try { piano.triggerAttack(np, time, 0.8); } catch{}
          active.note = np;
        }, t);
      } else if (np === "R") {
        Tone.getTransport().schedule(time => {
          if (active.note) { try { piano.triggerRelease(active.note, time); } catch{} active.note = null; }
        }, t);
      }
    });

    // 最終音を止める
    Tone.getTransport().schedule(time => {
      if (active.note) try { piano.triggerRelease(active.note, time); } catch{}
    }, 64 * stepSecs);
  }

  // 再生カーソルのコールバック
  for (let i = 0; i < 64; i++) {
    const step = i;
    Tone.getTransport().schedule(time => {
      Tone.getDraw().schedule(() => { scorePanel.setPlayStep(step); }, time);
    }, i * stepSecs);
  }

  // 再生完了
  Tone.getTransport().schedule(() => {
    Tone.getDraw().schedule(() => {
      state.isPlaying = false;
      state.playStep  = null;
      scorePanel.setPlayStep(null);
      document.getElementById("play-btn").textContent = "▶ 再生";
      document.getElementById("play-btn").classList.replace("btn-red","btn-teal");
      setStatus("再生完了。");
    }, "+0");
  }, 64 * stepSecs + 0.1);

  Tone.getTransport().start();
  state.isPlaying = true;
}

function stopPlayback() {
  Tone.getTransport().stop();
  Tone.getTransport().cancel();
  if (piano && pianoReady) {
    try { piano.releaseAll?.(); } catch{}
  }
  state.isPlaying = false;
  state.playStep  = null;
  scorePanel.setPlayStep(null);
}

// ═══════════════════════════════════════════════════════
//  スコアパネル
// ═══════════════════════════════════════════════════════

let scorePanel = null;

function applyOL() {
  const onsetsA = new Set(
    state.voices[state.olVA].filter(ev => ev.pitch !== "R").map(ev => ev.step)
  );
  const onsetsB = new Set(
    state.voices[state.olVB].filter(ev => ev.pitch !== "R").map(ev => ev.step)
  );
  state.olIndices = [...onsetsA].filter(s => onsetsB.has(s));
  for (const v of VOICES) refreshVoice(v);
  setStatus(`重複ハイライト: ${state.olIndices.length} 箇所`);
}

function clearOL() {
  state.olIndices = [];
  for (const v of VOICES) refreshVoice(v);
  setStatus("重複ハイライトをクリアしました。");
}

function buildOLPanel() {
  const vaEl = document.getElementById("ol-va");
  const vbEl = document.getElementById("ol-vb");
  for (const v of VOICES) {
    [vaEl, vbEl].forEach(sel => {
      const opt = document.createElement("option");
      opt.value = v; opt.textContent = V_LABELS[v]; sel.appendChild(opt);
    });
  }
  vaEl.value = "melody";
  vbEl.value = "mid";
  vaEl.addEventListener("change", () => { state.olVA = vaEl.value; });
  vbEl.addEventListener("change", () => { state.olVB = vbEl.value; });
}

function refreshVoice(voice) {
  const hlIdx = (state.hlVA === voice || state.hlVB === voice) ? state.hlIndices : [];
  const olIdx = (state.olVA === voice || state.olVB === voice) ? state.olIndices : [];
  scorePanel.update(voice, state.voices[voice], hlIdx, state.selSteps, new Set(olIdx));
  if (state.selVoice === voice) scorePanel.setSelected(voice, state.selSteps);
}

function refreshAll() {
  for (const v of VOICES) refreshVoice(v);
}

// ═══════════════════════════════════════════════════════
//  選択
// ═══════════════════════════════════════════════════════

function onNoteSelect(voice, step, pitch, dur, isCtrl = false) {
  // Ctrl+クリック: 同じ声部ならトグル追加、違う声部なら通常選択
  if (isCtrl && state.selVoice === voice && pitch && pitch !== "blank") {
    const ev = findEventAt(state.voices[voice], step);
    if (ev) {
      if (state.selSteps.has(ev.step)) {
        state.selSteps = new Set([...state.selSteps].filter(s => s !== ev.step));
      } else {
        state.selSteps = new Set([...state.selSteps, ev.step]);
      }
      // selEv は最後に追加したものか、残っている中で最大step
      state.selEv = state.selSteps.size > 0
        ? findEventAt(state.voices[voice], Math.max(...state.selSteps))
        : null;
      scorePanel.clearSelected();
      scorePanel.setSelected(voice, state.selSteps);
      updateEditorInfo();
      return;
    }
  }
  // 通常選択（Ctrl なし、または別声部）
  state.selVoice = voice;
  if (pitch && pitch !== "blank") {
    const ev = findEventAt(state.voices[voice], step);
    state.selEv    = ev;
    state.selSteps = ev ? new Set([ev.step]) : new Set();
  } else {
    state.selEv    = null;
    state.selSteps = new Set();
  }
  scorePanel.clearSelected();
  if (state.selVoice) scorePanel.setSelected(state.selVoice, state.selSteps);
  updateEditorInfo();
}

function onDragSelect(voice, selections) {
  state.selVoice = voice;
  state.selSteps = new Set(selections.map(s => s.step));
  if (state.selSteps.size > 0) {
    const first = Math.min(...state.selSteps);
    state.selEv = findEventAt(state.voices[voice], first);
  } else {
    state.selEv = null;
  }
  scorePanel.clearSelected();
  scorePanel.setSelected(voice, state.selSteps);
  updateEditorInfo();
}

// ダブルクリックで8分音符（2ステップ）を挿入
function onInsert(voice, step) {
  // すでに音符がある場合は挿入しない（選択のみ）
  const existing = findEventAt(state.voices[voice], step);
  if (existing) {
    onNoteSelect(voice, step, existing.pitch, existing.dur);
    return;
  }

  // 直前の音符からピッチを引き継ぐ（なければ C4）
  const prevEv = [...state.voices[voice]]
    .filter(ev => ev.step < step && ev.pitch !== "R")
    .sort((a, b) => b.step - a.step)[0];
  const pitch = prevEv ? prevEv.pitch : "C4";

  pushUndo();
  state.voices[voice] = insertOrReplace(state.voices[voice], step, pitch, 2); // 八分音符 = 2step
  state.selVoice = voice;
  state.selEv    = findEventAt(state.voices[voice], step);
  state.selSteps = state.selEv ? new Set([state.selEv.step]) : new Set();
  refreshVoice(voice);
  scorePanel.setSelected(voice, state.selSteps);
  updateEditorInfo();
  setStatus(`[${V_LABELS[voice]}] Step ${step} に 八分音符（${pitch}）を挿入しました`);
}

function updateEditorInfo() {
  const el = document.getElementById("editor-info");
  if (state.selEv) {
    const p  = state.selEv.pitch;
    const d  = state.selEv.dur;
    const vl = V_LABELS[state.selVoice] || "?";
    const n  = state.selSteps.size;
    el.textContent = `${vl} | Step ${state.selEv.step} | ${p==="R"?"休符":p} | ${durLabel(d)}（${d}step）${n>1?` / ${n}音選択中`:""}`;
  } else {
    el.textContent = "（音符をクリックまたはドラッグで選択）";
  }
}

// ═══════════════════════════════════════════════════════
//  Undo
// ═══════════════════════════════════════════════════════

function pushUndo() {
  const snap = {};
  for (const v of VOICES) snap[v] = state.voices[v].map(ev => ({...ev}));
  state.undoStack.push(snap);
  if (state.undoStack.length > MAX_UNDO) state.undoStack.shift();
}

function copySelection() {
  if (!state.selVoice || !state.selSteps.size) return;
  const evs = state.voices[state.selVoice].filter(ev => state.selSteps.has(ev.step));
  if (!evs.length) return;
  const baseStep  = Math.min(...evs.map(ev => ev.step));
  const totalDur  = Math.max(...evs.map(ev => ev.step + ev.dur)) - baseStep;
  state.clipboard = {
    notes: evs.map(ev => ({ relStep: ev.step - baseStep, pitch: ev.pitch, dur: ev.dur })),
    totalDur,
  };
  setStatus(`${evs.length}音コピー。貼り付けたい位置を選択して Ctrl+V`);
}

function pasteSelection() {
  if (!state.clipboard || !state.selVoice || !state.selSteps.size) return;
  const pasteStart = Math.min(...state.selSteps);
  const pasteEnd   = pasteStart + state.clipboard.totalDur;

  pushUndo();

  // ペースト範囲内の既存音符を除去
  const evs = state.voices[state.selVoice].filter(ev =>
    !(ev.step >= pasteStart && ev.step < pasteEnd)
  );

  // コピーした音符を配置（64ステップを超えるものはクリップ）
  for (const n of state.clipboard.notes) {
    const newStep = pasteStart + n.relStep;
    if (newStep >= 64) continue;
    evs.push({ step: newStep, pitch: n.pitch, dur: Math.min(n.dur, 64 - newStep) });
  }

  evs.sort((a, b) => a.step - b.step);
  state.voices[state.selVoice] = evs;

  const newSteps = state.clipboard.notes.map(n => pasteStart + n.relStep).filter(s => s < 64);
  state.selSteps = new Set(newSteps);
  state.selEv    = newSteps.length ? findEventAt(state.voices[state.selVoice], Math.min(...newSteps)) : null;

  refreshVoice(state.selVoice);
  scorePanel.setSelected(state.selVoice, state.selSteps);
  updateEditorInfo();
  setStatus(`${state.clipboard.notes.length}音貼り付けました。Ctrl+Z で元に戻せます。`);
}

function undo() {
  if (!state.undoStack.length) { setStatus("これ以上戻れません。"); return; }
  const snap = state.undoStack.pop();
  for (const v of VOICES) state.voices[v] = snap[v];
  state.selEv    = null;
  state.selSteps = new Set();
  refreshAll();
  updateEditorInfo();
  setStatus("元に戻しました。");
}

// ═══════════════════════════════════════════════════════
//  音符編集
// ═══════════════════════════════════════════════════════

function shiftPitchSel(semis) {
  if (!state.selVoice || !state.selSteps.size) return;
  pushUndo();
  const evs = state.voices[state.selVoice];
  let changed = false;
  for (const ev of evs) {
    if (state.selSteps.has(ev.step) && ev.pitch !== "R") {
      ev.pitch = shiftPitch(ev.pitch, semis);
      changed  = true;
    }
  }
  if (changed) { refreshVoice(state.selVoice); updateEditorInfo(); }
}

function navigate(dir) {
  if (!state.selVoice) { state.selVoice = "melody"; }
  const evs = [...state.voices[state.selVoice]].sort((a,b)=>a.step-b.step);
  if (!evs.length) return;
  let cur = state.selEv ? evs.findIndex(e => e.step === state.selEv.step) : -1;
  if (cur < 0) cur = dir > 0 ? -1 : evs.length;
  const next = Math.max(0, Math.min(evs.length - 1, cur + dir));
  const ev   = evs[next];
  state.selEv    = ev;
  state.selSteps = new Set([ev.step]);
  scorePanel.setSelected(state.selVoice, state.selSteps);
  updateEditorInfo();
  const p = ev.pitch;
  setStatus(`[${V_LABELS[state.selVoice]}] Step ${ev.step} : ${p==="R"?"休符":p} / ${durLabel(ev.dur)}（${ev.dur}step）`);
}

function cycleDur(dir) {
  if (!state.selEv) return;
  const cur = state.selEv.dur;
  let idx   = DUR_ORDER.indexOf(cur);
  if (idx < 0) idx = DUR_ORDER.reduce((bi,v,i)=>Math.abs(v-cur)<Math.abs(DUR_ORDER[bi]-cur)?i:bi, 0);
  const next = Math.max(0, Math.min(DUR_ORDER.length-1, idx + dir));
  if (DUR_ORDER[next] !== cur) setDur(DUR_ORDER[next]);
}

function setDur(newDur) {
  if (!state.selEv || !state.selVoice) return;

  const step   = state.selEv.step;
  const pitch  = state.selEv.pitch;
  const oldDur = state.selEv.dur;

  if (newDur === oldDur) return;

  if (newDur > oldDur) {
    // ── 拡張: 後続イベントを右シフト（短縮の逆操作）──
    const gap = newDur - oldDur;
    pushUndo();

    const evs = state.voices[state.selVoice]
      .filter(ev => ev.step !== step)
      .map(ev => {
        if (ev.step < step + oldDur) return ev;
        const newStep = ev.step + gap;
        if (newStep >= 64) return null;
        return { ...ev, step: newStep, dur: Math.min(ev.dur, 64 - newStep) };
      })
      .filter(Boolean);

    evs.push({ step, pitch, dur: newDur });
    evs.sort((a, b) => a.step - b.step);
    state.voices[state.selVoice] = evs;

  } else {
    // ── 短縮: 後続イベントを左シフト、末尾に休符を追加 ──
    const gap = oldDur - newDur;
    pushUndo();

    const evs = state.voices[state.selVoice]
      .filter(ev => ev.step !== step)
      .map(ev => ev.step >= step + oldDur
        ? { ...ev, step: ev.step - gap }
        : ev
      );
    evs.push({ step, pitch, dur: newDur });

    // 末尾の空きを休符で埋める
    const lastEnd = evs.reduce((max, ev) => Math.max(max, ev.step + ev.dur), 0);
    if (lastEnd < 64) evs.push({ step: lastEnd, pitch: "R", dur: 64 - lastEnd });

    evs.sort((a, b) => a.step - b.step);
    state.voices[state.selVoice] = evs;
  }

  state.selEv = findEventAt(state.voices[state.selVoice], step);
  if (state.selEv) state.selSteps = new Set([state.selEv.step]);
  refreshVoice(state.selVoice);
  updateEditorInfo();
}

function toggleRest() {
  if (!state.selVoice || !state.selSteps.size) return;
  pushUndo();
  for (const ev of state.voices[state.selVoice]) {
    if (!state.selSteps.has(ev.step)) continue;
    if (ev.pitch === "R") {
      // 直前の音を参照して復元
      const prev = [...state.voices[state.selVoice]]
        .filter(e => e.step < ev.step && e.pitch !== "R")
        .sort((a,b) => b.step - a.step)[0];
      ev.pitch = prev ? prev.pitch : "C4";
    } else {
      ev.pitch = "R";
    }
  }
  if (state.selEv) state.selEv = findEventAt(state.voices[state.selVoice], state.selEv.step);
  refreshVoice(state.selVoice);
  updateEditorInfo();
}

function deleteSel() {
  if (!state.selVoice || !state.selSteps.size) return;
  pushUndo();
  state.voices[state.selVoice] = state.voices[state.selVoice]
    .filter(ev => !state.selSteps.has(ev.step));
  state.selEv    = null;
  state.selSteps = new Set();
  refreshVoice(state.selVoice);
  updateEditorInfo();
  setStatus("削除しました。Ctrl+Z で元に戻せます。");
}

// ═══════════════════════════════════════════════════════
//  HL（度数ハイライト）
// ═══════════════════════════════════════════════════════

function applyHL() {
  const stepsA = eventsToSoundingSteps(state.voices[state.hlVA]);
  const stepsB = eventsToSoundingSteps(state.voices[state.hlVB]);
  state.hlIndices = findIntervalIndices(stepsA, stepsB, state.hlDeg);
  for (const v of VOICES) refreshVoice(v);
  setStatus(`${state.hlDeg}度: ${state.hlIndices.length} 箇所ハイライト`);
}

function clearHL() {
  state.hlIndices = [];
  for (const v of VOICES) refreshVoice(v);
}

function selectHLVoice(voice) {
  if (!state.hlIndices.length) { setStatus("先にハイライトを適用してください。"); return; }
  const hlSet = new Set(state.hlIndices);
  const matched = state.voices[voice].filter(ev => {
    if (ev.pitch === "R") return false;
    for (let s = ev.step; s < ev.step + ev.dur; s++) {
      if (hlSet.has(s)) return true;
    }
    return false;
  });
  if (!matched.length) { setStatus(`[${V_LABELS[voice]}] ハイライト音符なし`); return; }
  state.selVoice = voice;
  state.selSteps = new Set(matched.map(ev => ev.step));
  state.selEv    = matched[0];
  scorePanel.clearSelected();
  scorePanel.setSelected(voice, state.selSteps);
  updateEditorInfo();
  setStatus(`[${V_LABELS[voice]}] ${matched.length}音を一括選択しました。`);
}

// ═══════════════════════════════════════════════════════
//  バックエンド API
// ═══════════════════════════════════════════════════════

async function apiFetch(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(()=>({error:`HTTP ${res.status}`}));
    throw new Error(err.error || "不明なエラー");
  }
  return res;
}

async function generateVoices() {
  showLoading(true);
  try {
    const resolved = resolveChords(state.chords);
    const res  = await apiFetch("/api/generate", { chord_names: resolved });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    // melody: すでにイベントがある場合は保持（リズムを壊さない）
    // 空の場合のみテキスト入力またはAPIから設定
    if (state.voices["melody"].length === 0) {
      const melText = document.getElementById("melody-input").value.trim();
      if (melText) {
        state.voices["melody"] = stepsToEvents(parseMelodyText(melText));
      } else {
        state.voices["melody"] = stepsToEvents(data["melody"] || []);
      }
    }
    for (const v of ["mid","bass_high","bass_low"])
      state.voices[v] = stepsToEvents(data[v] || []);

    refreshAll();
    const label = state.chords.map(c => c === "cont" ? "ー" : c).join(" / ");
    setStatus(`生成完了: ${label}`);
  } catch(e) {
    alert("生成エラー: " + e.message);
  } finally {
    showLoading(false);
  }
}

async function exportMidi() {
  showLoading(true);
  try {
    const voices = {};
    for (const v of VOICES) voices[v] = eventsToExportSteps(state.voices[v]);
    const res = await apiFetch("/api/export_midi", { voices });
    const blob = await res.blob();
    downloadBlob(blob, "counterpoint.mid");
    setStatus("MIDI出力完了");
  } catch(e) { alert("MIDIエラー: " + e.message); }
  finally { showLoading(false); }
}

async function exportCsv() {
  showLoading(true);
  try {
    const voices = {};
    for (const v of VOICES) voices[v] = eventsToExportSteps(state.voices[v]);
    const res = await apiFetch("/api/export_csv", { chord_names: resolveChords(state.chords), voices });
    const blob = await res.blob();
    downloadBlob(blob, "counterpoint.csv");
    setStatus("CSV出力完了");
  } catch(e) { alert("CSVエラー: " + e.message); }
  finally { showLoading(false); }
}

async function importCsv(file) {
  const fd = new FormData();
  fd.append("file", file);
  showLoading(true);
  try {
    const res  = await fetch("/api/import_csv", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    state.chords = data.chord_names.slice(0, 8);
    for (const v of VOICES) state.voices[v] = stepsToEvents(data[v] || []);
    syncChordUI();
    refreshAll();
    setStatus(`CSV読込: ${state.chords.join(" / ")}`);
  } catch(e) { alert("CSVエラー: " + e.message); }
  finally { showLoading(false); }
}

// ═══════════════════════════════════════════════════════
//  ユーティリティ
// ═══════════════════════════════════════════════════════

function parseMelodyText(text) {
  const steps = [];
  for (const tok of text.trim().split(/\s+/)) {
    if (!tok) continue;
    if (tok.toLowerCase() === "blank" || tok.toLowerCase() === "r") {
      steps.push("R","blank","blank","blank");
    } else {
      steps.push(normalizePitch(tok),"blank","blank","blank");
    }
  }
  while (steps.length < 64) steps.push("blank");
  return steps.slice(0, 64);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href     = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function showLoading(on) {
  document.getElementById("loading").style.display = on ? "flex" : "none";
}

function setStatus(msg) {
  document.getElementById("statusbar").textContent = msg;
}

function syncChordUI() {
  for (let i = 0; i < 8; i++) {
    const chord = state.chords[i] || "C";
    const row   = document.querySelectorAll(".chord-selector")[i];
    if (!row) continue;
    const [rootSel, qualSel] = row.querySelectorAll("select");
    if (chord === "cont") {
      qualSel.value    = "cont";
      rootSel.disabled = true;
    } else {
      const root = chord.match(/^([A-G][#b]?)/)?.[1] || "C";
      const qual = chord.slice(root.length);
      rootSel.value    = ROOTS.includes(root) ? root : "C";
      qualSel.value    = qual || "";
      rootSel.disabled = false;
    }
  }
}

function readChordUI() {
  state.chords = [];
  document.querySelectorAll(".chord-selector").forEach((row, i) => {
    const [rootSel, qualSel] = row.querySelectorAll("select");
    if (qualSel.value === "cont") {
      state.chords.push("cont");
    } else {
      state.chords.push(rootSel.value + qualSel.value);
    }
  });
}

function resolveChords(chords) {
  const resolved = [];
  let prev = "C";
  for (const c of chords) {
    if (c === "cont") {
      resolved.push(prev);
    } else {
      resolved.push(c);
      prev = c;
    }
  }
  return resolved;
}

// ═══════════════════════════════════════════════════════
//  初期化 & キーバインド
// ═══════════════════════════════════════════════════════

function buildChordSelectors() {
  const container = document.getElementById("chord-selectors");
  container.innerHTML = "";
  for (let i = 0; i < 8; i++) {
    const div = document.createElement("div");
    div.className = "chord-selector";

    const lbl = document.createElement("label");
    lbl.textContent = CHORD_SLOT_LABELS[i];

    const rootSel = document.createElement("select");
    for (const r of ROOTS) {
      const opt = document.createElement("option");
      opt.value = r; opt.textContent = r; rootSel.appendChild(opt);
    }

    const qualSel = document.createElement("select");
    for (const [val, lbl2] of Object.entries(QUALITIES)) {
      const opt = document.createElement("option");
      opt.value = val; opt.textContent = lbl2; qualSel.appendChild(opt);
    }

    qualSel.addEventListener("change", () => {
      rootSel.disabled = qualSel.value === "cont";
    });

    div.appendChild(lbl);
    div.appendChild(rootSel);
    div.appendChild(qualSel);
    container.appendChild(div);
  }
}

function buildDurButtons() {
  const container = document.getElementById("dur-buttons");
  if (!container) return;
  container.innerHTML = "";
  const pairs = [["全",16],["付二",12],["二",8],["付四",6],["四",4],["付八",3],["八",2],["十六",1]];
  for (const [lbl, steps] of pairs) {
    const btn = document.createElement("button");
    btn.className   = "dur-btn";
    btn.textContent = lbl;
    btn.title       = durLabel(steps);
    btn.addEventListener("click", () => setDur(steps));
    container.appendChild(btn);
  }
}

function buildHLPanel() {
  const vaEl  = document.getElementById("hl-va");
  const vbEl  = document.getElementById("hl-vb");
  const degEl = document.getElementById("hl-deg");

  for (const v of VOICES) {
    [vaEl, vbEl].forEach(sel => {
      const opt = document.createElement("option");
      opt.value = v; opt.textContent = V_LABELS[v]; sel.appendChild(opt);
    });
  }
  vaEl.value  = "melody";
  vbEl.value  = "mid";

  for (let d = 1; d <= 7; d++) {
    const opt = document.createElement("option");
    opt.value = d; opt.textContent = d; degEl.appendChild(opt);
  }
  degEl.value = "3";

  vaEl .addEventListener("change", () => { state.hlVA  = vaEl.value; });
  vbEl .addEventListener("change", () => { state.hlVB  = vbEl.value; });
  degEl.addEventListener("change", () => { state.hlDeg = parseInt(degEl.value); });
}

function initKeyBindings() {
  document.addEventListener("keydown", e => {
    // テキスト入力中はスキップ（HL ON の場合の select も）
    const tag = document.activeElement?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;

    // HL ON 中は ↑↓ で degree 変更
    if (state.hlActive && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      const degEl = document.getElementById("hl-deg");
      let v = parseInt(degEl.value);
      v = e.key === "ArrowUp" ? Math.min(7, v+1) : Math.max(1, v-1);
      degEl.value   = v;
      state.hlDeg   = v;
      return;
    }

    if (e.key === "ArrowUp")   { e.preventDefault(); shiftPitchSel(+1); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); shiftPitchSel(-1); return; }
    if (e.key === "ArrowLeft") { e.preventDefault(); navigate(-1); return; }
    if (e.key === "ArrowRight"){ e.preventDefault(); navigate(+1); return; }
    if (e.key === "+" || e.key === "=") { e.preventDefault(); cycleDur(+1); return; }
    if (e.key === "-")         { e.preventDefault(); cycleDur(-1); return; }
    if (e.key === "0")         { e.preventDefault(); toggleRest();  return; }
    if (e.key === "Delete")    { e.preventDefault(); deleteSel();   return; }
    if (e.ctrlKey && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
    if (e.ctrlKey && e.key.toLowerCase() === "c") { e.preventDefault(); copySelection(); return; }
    if (e.ctrlKey && e.key.toLowerCase() === "v") { e.preventDefault(); pasteSelection(); return; }
  });
}

// ═══════════════════════════════════════════════════════
//  HL トグル
// ═══════════════════════════════════════════════════════

function toggleHL() {
  state.hlActive = !state.hlActive;
  const btn = document.getElementById("hl-toggle-btn");
  if (state.hlActive) {
    btn.textContent = "HL: ON";
    btn.classList.replace("btn-hl-off","btn-hl-on");
    document.getElementById("hl-deg").focus();
    setStatus("HL ON: ↑↓ で度数変更、「HL」ボタンで反映");
  } else {
    btn.textContent = "HL: OFF";
    btn.classList.replace("btn-hl-on","btn-hl-off");
    document.body.focus();
    setStatus("HL OFF: 音符を選択して ↑↓ で音高調整");
  }
}

// ═══════════════════════════════════════════════════════
//  起動
// ═══════════════════════════════════════════════════════

window.addEventListener("DOMContentLoaded", async () => {
  buildChordSelectors();
  syncChordUI();
  buildDurButtons();
  buildHLPanel();
  buildOLPanel();

  // スコアパネル初期化
  scorePanel = SCORE.createScorePanel(document.getElementById("score-area"), {
    onSelect:     onNoteSelect,
    onDragSelect: onDragSelect,
    onInsert:     onInsert,
  });

  // MIDIから読み込んだ主旋律を設定（16分音符ステップ解像度）
  // 1小節目(steps 0-15): Dm上 — D5(付点四分=6), A4(八分=2), B4(八分=2), G5(付点四分=6)
  // 2小節目(steps 16-31): C上  — A5(八分=2), G5(四分=4), A4(八分=2), B4(四分=4), G5(八分=2), C5(八分=2)
  const midiMelSteps = Array(64).fill("blank");
  midiMelSteps[0]  = "D5";
  midiMelSteps[6]  = "A4";
  midiMelSteps[8]  = "B4";
  midiMelSteps[10] = "G5";
  midiMelSteps[16] = "A5";
  midiMelSteps[18] = "G5";
  midiMelSteps[22] = "A4";
  midiMelSteps[24] = "B4";
  midiMelSteps[28] = "G5";
  midiMelSteps[30] = "C5";
  state.voices["melody"] = stepsToEvents(midiMelSteps);
  refreshVoice("melody");
  document.getElementById("melody-input").value = "";

  // ボタンイベント
  document.getElementById("btn-import").addEventListener("click", () =>
    document.getElementById("csv-file-input").click());
  document.getElementById("csv-file-input").addEventListener("change", e => {
    if (e.target.files[0]) { importCsv(e.target.files[0]); e.target.value = ""; }
  });
  document.getElementById("btn-new").addEventListener("click", () => {
    for (const v of VOICES) state.voices[v] = [];
    state.selEv = null; state.selSteps = new Set();
    refreshAll(); updateEditorInfo(); setStatus("新規作成。");
  });
  document.getElementById("btn-generate").addEventListener("click", () => {
    readChordUI(); generateVoices();
  });
  document.getElementById("btn-midi").addEventListener("click", exportMidi);
  document.getElementById("btn-csv").addEventListener("click", exportCsv);

  document.getElementById("play-btn").addEventListener("click", async () => {
    if (state.isPlaying) {
      stopPlayback();
      document.getElementById("play-btn").textContent = "▶ 再生";
      document.getElementById("play-btn").classList.replace("btn-red","btn-teal");
      setStatus("停止。");
    } else {
      document.getElementById("play-btn").textContent = "■ 停止";
      document.getElementById("play-btn").classList.replace("btn-teal","btn-red");
      await startPlayback();
    }
  });

  document.getElementById("hl-toggle-btn").addEventListener("click", toggleHL);
  document.getElementById("hl-apply-btn").addEventListener("click", () => {
    state.hlVA  = document.getElementById("hl-va").value;
    state.hlVB  = document.getElementById("hl-vb").value;
    state.hlDeg = parseInt(document.getElementById("hl-deg").value);
    applyHL();
  });
  document.getElementById("hl-clear-btn").addEventListener("click", clearHL);
  document.getElementById("hl-select-a-btn").addEventListener("click", () => selectHLVoice(state.hlVA));
  document.getElementById("hl-select-b-btn").addEventListener("click", () => selectHLVoice(state.hlVB));

  document.getElementById("ol-apply-btn").addEventListener("click", () => {
    state.olVA = document.getElementById("ol-va").value;
    state.olVB = document.getElementById("ol-vb").value;
    applyOL();
  });
  document.getElementById("ol-clear-btn").addEventListener("click", clearOL);

  // 音符エディタのボタン（要素が存在する場合のみ）
  document.getElementById("btn-pitch-up")  ?.addEventListener("click", () => shiftPitchSel(+1));
  document.getElementById("btn-pitch-down")?.addEventListener("click", () => shiftPitchSel(-1));
  document.getElementById("btn-rest")      ?.addEventListener("click", toggleRest);
  document.getElementById("btn-delete")    ?.addEventListener("click", deleteSel);
  document.getElementById("btn-undo")      ?.addEventListener("click", undo);

  // キーバインド
  initKeyBindings();

  // 音源の非同期プリロード
  await initAudio();

  setStatus("起動しました。「対旋律を自動生成」を押してください。");
});
