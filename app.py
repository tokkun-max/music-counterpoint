# Flask Webアプリ — 対旋律作成ツール（音楽生成・MIDI/CSVエクスポート・CSVインポートAPI）

import os, sys, tempfile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, send_file, render_template

from voice_generator import generate_all_voices
from note_utils import steps_to_events, events_to_export_steps
from csv_exporter import export_csv, chord_names_to_steps
from midi_exporter import export_midi

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024   # 4 MB


# ──────────────────────────── ページ ────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────── API ────────────────────────────

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json()
        chord_names = data.get("chord_names", ["C", "F", "G", "C"])
        voices = generate_all_voices(chord_names)
        return jsonify(voices)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export_midi", methods=["POST"])
def api_export_midi():
    try:
        data = request.get_json()
        voices = {k: v for k, v in data["voices"].items()}
        fd, path = tempfile.mkstemp(suffix=".mid")
        os.close(fd)
        export_midi(voices, filepath=path)
        return send_file(path, as_attachment=True,
                         download_name="counterpoint.mid",
                         mimetype="audio/midi")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/export_csv", methods=["POST"])
def api_export_csv():
    try:
        data = request.get_json()
        chord_steps = chord_names_to_steps(data["chord_names"])
        v = data["voices"]
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        export_csv(chord_steps,
                   v["melody"], v["mid"], v["bass_high"], v["bass_low"],
                   filepath=path)
        return send_file(path, as_attachment=True,
                         download_name="counterpoint.csv",
                         mimetype="text/csv")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/import_csv", methods=["POST"])
def api_import_csv():
    if "file" not in request.files:
        return jsonify({"error": "ファイルがありません"}), 400
    file = request.files["file"]
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        file.save(path)
        # csv_importer は tkinter を使うのでインポートし直して直接パース
        result = _parse_csv(path)
        if result is None:
            return jsonify({"error": "CSVフォーマットが正しくありません"}), 400
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def _parse_csv(filepath: str) -> dict | None:
    """tkinter 不使用の CSV パーサ（csv_importer の内部ロジックを再実装）。"""
    import csv
    STEPS = 64
    EXPECTED = ["4小節", "16拍子", "コード進行", "主旋律③",
                "対旋律③中音域", "対旋律③低音域", "対旋律③超低音域"]
    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception:
        return None
    if not rows or len(rows[0]) < 7:
        return None
    header = [h.strip() for h in rows[0]]
    for i, (exp, got) in enumerate(zip(EXPECTED, header)):
        if exp != got:
            return None

    def col(row, idx):
        v = row[idx].strip() if idx < len(row) else ""
        return v if v else "blank"

    chord_col, mel, mid, bh, bl = [], [], [], [], []
    for row in rows[1:STEPS + 1]:
        chord_col.append(col(row, 2))
        mel.append(col(row, 3))
        mid.append(col(row, 4))
        bh.append(col(row, 5))
        bl.append(col(row, 6))

    while len(chord_col) < STEPS: chord_col.append("blank")
    while len(mel)       < STEPS: mel.append("blank")
    while len(mid)       < STEPS: mid.append("blank")
    while len(bh)        < STEPS: bh.append("blank")
    while len(bl)        < STEPS: bl.append("blank")

    prev, chord_names = "", []
    for c in chord_col:
        if c and c != "blank" and c != prev:
            chord_names.append(c); prev = c

    return {
        "chord_steps": chord_col,
        "chord_names": chord_names,
        "melody":      mel,
        "mid":         mid,
        "bass_high":   bh,
        "bass_low":    bl,
    }


if __name__ == "__main__":
    print("http://localhost:5000 を開いてください")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, port=port, host="0.0.0.0")
