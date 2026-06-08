// note_utils.js — NoteEvent ↔ 64ステップ変換・音高変換・度数計算

const STEPS = 64;

const DUR_ORDER  = [1, 2, 3, 4, 6, 8, 12, 16];
const DUR_LABELS = {
  1: "十六分音符", 2: "八分音符", 3: "付点八分音符",
  4: "四分音符",  6: "付点四分音符", 8: "二分音符",
  12: "付点二分音符", 16: "全音符",
};
const DUR_SHORT = {
  1:"十六", 2:"八", 3:"付八", 4:"四", 6:"付四", 8:"二", 12:"付二", 16:"全"
};
function durLabel(steps) {
  return DUR_LABELS[steps] || `${steps}step`;
}

// ── 音高変換 ──────────────────────────────────────────────────

const _NOTE_SEMI = {
  C:0,"C#":1,Db:1,D:2,"D#":3,Eb:3,E:4,F:5,"F#":6,Gb:6,
  G:7,"G#":8,Ab:8,A:9,"A#":10,Bb:10,B:11,
};

// music21 の "E-4" → "Eb4" に正規化
function normalizePitch(p) {
  if (!p || p === "blank" || p === "R") return p;
  return p.replace(/([A-G])-(\d)/, "$1b$2");
}

function pitchToMidi(name) {
  const n = normalizePitch(name);
  if (!n || n === "blank" || n === "R") return -1;
  const m = n.match(/^([A-G][#b]?)(\d+)$/);
  if (!m) return -1;
  const semi = _NOTE_SEMI[m[1]];
  if (semi === undefined) return -1;
  return (parseInt(m[2]) + 1) * 12 + semi;
}

function midiToPitch(midi) {
  const names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
  const oct   = Math.floor(midi / 12) - 1;
  return names[midi % 12] + oct;
}

function shiftPitch(pitchName, semitones) {
  const midi = pitchToMidi(pitchName);
  if (midi < 0) return pitchName;
  return midiToPitch(midi + semitones);
}

// ── NoteEvent ↔ ステップ変換 ──────────────────────────────────

function stepsToEvents(steps) {
  const events = [];
  let i = 0;
  while (i < steps.length) {
    const p = steps[i];
    if (!p || p === "blank") { i++; continue; }
    if (p === "R") {
      let dur = 0, j = i;
      while (j < steps.length && steps[j] === "R") { dur++; j++; }
      events.push({ step: i, pitch: "R", dur });
      i = j;
    } else {
      let dur = 1, j = i + 1;
      while (j < steps.length && steps[j] === "blank") { dur++; j++; }
      events.push({ step: i, pitch: normalizePitch(p), dur });
      i = j;
    }
  }
  return events;
}

function eventsToSteps(events) {
  const steps = Array(STEPS).fill("blank");
  for (const ev of [...events].sort((a, b) => a.step - b.step)) {
    if (ev.step < 0 || ev.step >= STEPS) continue;
    if (ev.pitch === "R") {
      for (let k = 0; k < ev.dur && ev.step + k < STEPS; k++)
        steps[ev.step + k] = "R";
    } else {
      steps[ev.step] = ev.pitch;
    }
  }
  return steps;
}

function eventsToExportSteps(events) {
  return eventsToSteps(events).map(s => (s === "R" ? "blank" : s));
}

// ── イベント操作 ──────────────────────────────────────────────

function findEventAt(events, step) {
  return events.find(ev => ev.step <= step && step < ev.step + ev.dur) || null;
}

function insertOrReplace(events, step, pitch, dur) {
  const newEnd = step + dur;
  const result = [];
  for (const ev of events) {
    const es = ev.step, ee = es + ev.dur;
    if (ee <= step || es >= newEnd) { result.push(ev); continue; }
    if (es < step)  result.push({ step: es, pitch: ev.pitch, dur: step - es });
    if (ee > newEnd) result.push({ step: newEnd, pitch: ev.pitch, dur: ee - newEnd });
  }
  result.push({ step, pitch, dur });
  return result.sort((a, b) => a.step - b.step);
}

function insertShift(events, step, pitch, dur) {
  // 挿入点以降の音符をまるごと dur ステップ右にシフトする（長さは変えない）
  const result = events.map(ev =>
    ev.step >= step
      ? { ...ev, step: ev.step + dur }
      : ev
  );
  result.push({ step, pitch, dur });
  return result.sort((a, b) => a.step - b.step);
}

function removeEventAt(events, step) {
  return events.filter(ev => !(ev.step <= step && step < ev.step + ev.dur));
}

// ── 度数ハイライト ────────────────────────────────────────────

const DEGREE_MAP = {0:1,1:2,2:2,3:3,4:3,5:4,6:4,7:5,8:6,9:6,10:7,11:7};

function semiToDegree(semi) {
  return DEGREE_MAP[Math.abs(semi) % 12];
}

function findIntervalIndices(stepsA, stepsB, degree) {
  const idxs = [];
  const len  = Math.min(stepsA.length, stepsB.length);
  for (let i = 0; i < len; i++) {
    const a = stepsA[i], b = stepsB[i];
    if (!a || a === "blank" || a === "R") continue;
    if (!b || b === "blank" || b === "R") continue;
    const ma = pitchToMidi(a), mb = pitchToMidi(b);
    if (ma < 0 || mb < 0) continue;
    if (semiToDegree(ma - mb) === degree) idxs.push(i);
  }
  return idxs;
}

// 度数HL用: 音符が鳴っている全ステップにピッチを埋めた配列を返す
function eventsToSoundingSteps(events) {
  const steps = Array(STEPS).fill("blank");
  for (const ev of events) {
    if (ev.step < 0 || ev.step >= STEPS || ev.pitch === "R") continue;
    for (let k = 0; k < ev.dur && ev.step + k < STEPS; k++)
      steps[ev.step + k] = ev.pitch;
  }
  return steps;
}

// ── コード進行ステップ展開 ──────────────────────────────────

function chordNamesToSteps(chordNames) {
  const steps = [];
  for (const c of chordNames)
    for (let i = 0; i < 16; i++) steps.push(c);
  while (steps.length < STEPS) steps.push(steps[steps.length - 1] || "");
  return steps.slice(0, STEPS);
}
