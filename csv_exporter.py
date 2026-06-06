# 4声部64要素リストを仕様書フォーマットのCSVファイルに保存するモジュール

import csv

HEADER = [
    "4小節", "16拍子", "コード進行", "主旋律③",
    "対旋律③中音域", "対旋律③低音域", "対旋律③超低音域",
]
STEPS = 64
STEPS_PER_MEASURE = 16


def export_csv(
    chord_steps: list[str],        # 64要素：各ステップのコード名
    melody: list[str],
    mid: list[str],
    bass_high: list[str],
    bass_low: list[str],
    filepath: str | None = None,
) -> str:
    """
    指定パス（None の場合は保存ダイアログ）に CSV を書き出す。
    小節番号は各小節の先頭ステップのみ記入、それ以外は空文字。
    保存したパスを返す。
    """
    if filepath is None:
        import tkinter.filedialog as fd
        filepath = fd.asksaveasfilename(
            title="CSVファイルを保存",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
    if not filepath:
        return ""

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for step in range(STEPS):
            measure_idx = step // STEPS_PER_MEASURE
            beat_in_measure = step % STEPS_PER_MEASURE

            # 小節番号は先頭ステップのみ記入
            measure_cell = str(measure_idx + 1) if beat_in_measure == 0 else ""
            beat_cell    = str(beat_in_measure + 1)

            writer.writerow([
                measure_cell,
                beat_cell,
                chord_steps[step]  if step < len(chord_steps) else "",
                melody[step]       if step < len(melody)      else "blank",
                mid[step]          if step < len(mid)         else "blank",
                bass_high[step]    if step < len(bass_high)   else "blank",
                bass_low[step]     if step < len(bass_low)    else "blank",
            ])
    return filepath


def chord_names_to_steps(chord_names: list[str]) -> list[str]:
    """コード名リスト（8要素）を64要素のステップ列に展開する（各スロット8ステップ）。"""
    STEPS_PER_SLOT = 8
    steps: list[str] = []
    for chord in chord_names:
        steps.extend([chord] * STEPS_PER_SLOT)
    while len(steps) < STEPS:
        steps.append(steps[-1] if steps else "")
    return steps[:STEPS]
