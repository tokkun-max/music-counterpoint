# CSVファイルを読み込み4声部64要素リストを返すモジュール

import csv
import tkinter.filedialog as fd
import tkinter.messagebox as mb

EXPECTED_HEADER = [
    "4小節", "16拍子", "コード進行", "主旋律③",
    "対旋律③中音域", "対旋律③低音域", "対旋律③超低音域",
]
STEPS = 64


def _normalize(val: str) -> str:
    v = val.strip()
    return v if v else "blank"


def import_csv(filepath: str | None = None) -> dict | None:
    """
    CSVを読み込み以下の辞書を返す。失敗時は None。
    {
        "chord_steps": list[str],   # 64要素のコード名列
        "chord_names": list[str],   # 重複除去したコード進行（4要素）
        "melody":      list[str],   # 64要素
        "mid":         list[str],
        "bass_high":   list[str],
        "bass_low":    list[str],
    }
    """
    if filepath is None:
        filepath = fd.askopenfilename(
            title="CSVファイルを選択",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
    if not filepath:
        return None

    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception as e:
        mb.showerror("読み込みエラー", f"ファイルを開けませんでした:\n{e}")
        return None

    if not rows:
        mb.showerror("フォーマットエラー", "ファイルが空です。")
        return None

    # ヘッダー検証
    header = [h.strip() for h in rows[0]]
    if len(header) < len(EXPECTED_HEADER):
        mb.showerror("フォーマットエラー",
                     f"列数が不足しています（{len(header)} 列）。必要: {len(EXPECTED_HEADER)} 列")
        return None
    for i, (exp, got) in enumerate(zip(EXPECTED_HEADER, header)):
        if exp != got:
            mb.showerror("フォーマットエラー",
                         f"列 {i+1} ヘッダーが一致しません。\n期待: {exp}\n実際: {got}")
            return None

    data = rows[1:]
    if len(data) != STEPS:
        mb.showwarning("行数警告",
                       f"データ行数が {len(data)} 行です（期待: {STEPS} 行）。処理を続けます。")

    def col(row: list[str], idx: int) -> str:
        return row[idx].strip() if idx < len(row) else ""

    chord_steps: list[str] = []
    melody:      list[str] = []
    mid:         list[str] = []
    bass_high:   list[str] = []
    bass_low:    list[str] = []

    for row in data[:STEPS]:
        chord_steps.append(_normalize(col(row, 2)))
        melody.append(_normalize(col(row, 3)))
        mid.append(_normalize(col(row, 4)))
        bass_high.append(_normalize(col(row, 5)))
        bass_low.append(_normalize(col(row, 6)))

    # 不足分を blank で補完
    for lst in [chord_steps, melody, mid, bass_high, bass_low]:
        while len(lst) < STEPS:
            lst.append("blank")

    # コード名のユニーク列を抽出（変化ポイントのみ）
    chord_names: list[str] = []
    prev = ""
    for c in chord_steps:
        if c and c != "blank" and c != prev:
            chord_names.append(c)
            prev = c

    return {
        "chord_steps": chord_steps,
        "chord_names": chord_names,
        "melody":      melody,
        "mid":         mid,
        "bass_high":   bass_high,
        "bass_low":    bass_low,
    }
