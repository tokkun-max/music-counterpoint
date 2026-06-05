# ピアノ/シンセ音色リアルタイム再生モジュール（winmm.dll 直接制御）

import threading
import time
import sys
from music21 import pitch as m21pitch

_WINMM_OK = False
if sys.platform == "win32":
    try:
        import ctypes, ctypes.wintypes
        _winmm = ctypes.windll.winmm
        _WINMM_OK = True
    except Exception:
        _WINMM_OK = False

# pygame フォールバック
_PYGAME_OK = False
if not _WINMM_OK:
    try:
        import pygame, pygame.midi
        _PYGAME_OK = True
    except Exception:
        pass

PIANO_PROGRAM  = 0      # GM: Acoustic Grand Piano
SYNTH_PROGRAM  = 80     # GM: Lead 1 (Square) — フォールバック
DEFAULT_TEMPO  = 120
VELOCITY       = 90
STEPS_PER_BEAT = 4

_CH = {"melody": 0, "mid": 1, "bass_high": 2, "bass_low": 3}

MIDI_MAPPER = 0xFFFFFFFF


# ---- MIDI デバイス名取得 ----
if _WINMM_OK:
    class _MIDIOUTCAPS(ctypes.Structure):
        _fields_ = [
            ("wMid",           ctypes.c_ushort),
            ("wPid",           ctypes.c_ushort),
            ("vDriverVersion", ctypes.c_uint),
            ("szPname",        ctypes.c_wchar * 32),
            ("wTechnology",    ctypes.c_ushort),
            ("wVoices",        ctypes.c_ushort),
            ("wNotes",         ctypes.c_ushort),
            ("wChannelMask",   ctypes.c_ushort),
            ("dwSupport",      ctypes.c_ulong),
        ]


def _num_devs() -> int:
    try:
        return _winmm.midiOutGetNumDevs() if _WINMM_OK else 0
    except Exception:
        return 0


def _dev_name(idx: int) -> str:
    if not _WINMM_OK:
        return ""
    try:
        caps = _MIDIOUTCAPS()
        _winmm.midiOutGetDevCapsW(idx, ctypes.byref(caps), ctypes.sizeof(caps))
        return caps.szPname
    except Exception:
        return ""


def _find_best_dev() -> int:
    """GS Wavetable Synth（内蔵ソフトシンセ）を優先して返す。"""
    n = _num_devs()
    for keyword in ("Wavetable", "GS Wave", "Microsoft GS", "Synth"):
        for i in range(n):
            if keyword.lower() in _dev_name(i).lower():
                return i
    return 0   # 見つからなければ 0 番


def list_midi_devices() -> list[tuple[int, str]]:
    """利用可能な MIDI 出力デバイス一覧を返す。"""
    return [(i, _dev_name(i)) for i in range(_num_devs())]


# ---- Windows MIDI ラッパー ----

def _msg(status: int, d1: int = 0, d2: int = 0) -> int:
    return status | (d1 << 8) | (d2 << 16)


class _WinMidi:
    def __init__(self, dev_id: int | None = None):
        self._h = ctypes.c_uint(0)
        devs = ([dev_id] if dev_id is not None
                else [_find_best_dev()] + list(range(_num_devs())) + [MIDI_MAPPER])
        last = -1
        for d in devs:
            res = _winmm.midiOutOpen(ctypes.byref(self._h), ctypes.c_uint(d), 0, 0, 0)
            if res == 0:
                self._dev = d
                return
            last = res
        raise OSError(f"midiOutOpen failed (err={last}). devices={list_midi_devices()}")

    def program_change(self, ch: int, prog: int):
        _winmm.midiOutShortMsg(self._h, _msg(0xC0 | ch, prog))

    def note_on(self, ch: int, note: int, vel: int = VELOCITY):
        _winmm.midiOutShortMsg(self._h, _msg(0x90 | ch, note, vel))

    def note_off(self, ch: int, note: int):
        _winmm.midiOutShortMsg(self._h, _msg(0x80 | ch, note, 0))

    def all_off(self):
        for ch in range(16):
            _winmm.midiOutShortMsg(self._h, _msg(0xB0 | ch, 123, 0))  # All Notes Off
            _winmm.midiOutShortMsg(self._h, _msg(0xB0 | ch, 120, 0))  # All Sound Off

    def close(self):
        try:
            self.all_off()
            _winmm.midiOutClose(self._h)
        except Exception:
            pass


# ---- プレーヤー ----

# 事前変換済みステップの特殊値
_CONT = -1   # blank（前音継続）
_REST = -2   # R（休符：前音を止める）


def _preprocess(voices: dict[str, list[str]]) -> dict[str, list[int]]:
    """
    文字列ステップ列を整数ステップ列に変換する（メインスレッドで実行）。
    音名 → MIDI番号, "blank" → _CONT, "R" → _REST
    music21 のスレッド問題を回避するため必ず threading 前に呼ぶ。
    """
    result: dict[str, list[int]] = {}
    for v, steps in voices.items():
        nums: list[int] = []
        for s in steps:
            if not s or s == "blank":
                nums.append(_CONT)
            elif s == "R":
                nums.append(_REST)
            else:
                try:
                    nums.append(m21pitch.Pitch(s).midi)
                except Exception:
                    nums.append(_CONT)
        result[v] = nums
    return result


class Player:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop   = threading.Event()
        self._midi   = None
        self._on_step = None
        self._available = _WINMM_OK or _PYGAME_OK
        if _WINMM_OK:
            devs = list_midi_devices()
            print(f"[Player] MIDI devices: {devs}")

    @property
    def available(self) -> bool:
        return self._available

    def set_step_callback(self, cb):
        self._on_step = cb

    def start(self, voices: dict[str, list[str]], tempo: int = DEFAULT_TEMPO):
        self.stop()
        self._stop.clear()
        # 事前変換（メインスレッドで music21 を呼ぶ）
        midi_data = _preprocess(voices)
        self._thread = threading.Thread(
            target=self._run, args=(midi_data, tempo), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._kill_midi()

    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _kill_midi(self):
        if self._midi is not None:
            try:
                if _WINMM_OK:
                    self._midi.close()
                else:
                    self._midi.close()
            except Exception:
                pass
            self._midi = None

    # ---- 内部 ----

    def _run(self, midi_data: dict[str, list[int]], tempo: int):
        try:
            if _WINMM_OK:
                self._run_winmm(midi_data, tempo)
            elif _PYGAME_OK:
                self._run_pygame(midi_data, tempo)
        except Exception as e:
            print(f"[Player] error: {e}")
        finally:
            self._kill_midi()

    def _run_winmm(self, midi_data: dict[str, list[int]], tempo: int):
        midi = _WinMidi()
        self._midi = midi
        print(f"[Player] opened device {midi._dev}: {_dev_name(midi._dev)}")

        # ピアノ音色をセット
        for ch in _CH.values():
            midi.program_change(ch, PIANO_PROGRAM)
        time.sleep(0.05)   # program change が反映されるまで少し待つ

        step_sec = 60.0 / tempo / STEPS_PER_BEAT
        active: dict[int, int | None] = {ch: None for ch in _CH.values()}

        for step in range(64):
            if self._stop.is_set():
                break
            for voice, ch in _CH.items():
                lst = midi_data.get(voice, [])
                val = lst[step] if step < len(lst) else _CONT
                if val >= 0:          # 音符
                    if active[ch] is not None:
                        midi.note_off(ch, active[ch])
                    midi.note_on(ch, val, VELOCITY)
                    active[ch] = val
                elif val == _REST:    # 休符
                    if active[ch] is not None:
                        midi.note_off(ch, active[ch])
                        active[ch] = None
                # _CONT: 何もしない（前音継続）

            if self._on_step:
                try:
                    self._on_step(step)
                except Exception:
                    pass
            time.sleep(step_sec)

        midi.all_off()
        midi.close()
        self._midi = None

    def _run_pygame(self, midi_data: dict[str, list[int]], tempo: int):
        import pygame.midi as pgm
        if not pgm.get_init():
            pgm.init()
        out = pgm.Output(pgm.get_default_output_id())
        self._midi = out
        for ch in _CH.values():
            out.set_instrument(PIANO_PROGRAM, ch)

        step_sec = 60.0 / tempo / STEPS_PER_BEAT
        active: dict[int, int | None] = {ch: None for ch in _CH.values()}

        for step in range(64):
            if self._stop.is_set():
                break
            for voice, ch in _CH.items():
                lst = midi_data.get(voice, [])
                val = lst[step] if step < len(lst) else _CONT
                if val >= 0:
                    if active[ch] is not None:
                        out.note_off(active[ch], 0, ch)
                    out.note_on(val, VELOCITY, ch)
                    active[ch] = val
                elif val == _REST:
                    if active[ch] is not None:
                        out.note_off(active[ch], 0, ch)
                        active[ch] = None
            if self._on_step:
                try:
                    self._on_step(step)
                except Exception:
                    pass
            time.sleep(step_sec)

        for ch, n in active.items():
            if n is not None:
                try:
                    out.note_off(n, 0, ch)
                except Exception:
                    pass
        out.close()
        self._midi = None
