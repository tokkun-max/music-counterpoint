# 前の音と候補リストを受け取り最短移動距離の音を返すボイスリーディングモジュール


def choose_closest(prev_midi: int | None, candidates: list[int]) -> int:
    """
    prev_midi から最も近い MIDI 番号を candidates から選ぶ。
    - 同距離の場合は高い音を優先する。
    - prev_midi が None の場合は candidates の中央値を返す。
    """
    if not candidates:
        raise ValueError("候補リストが空です")
    if prev_midi is None:
        return candidates[len(candidates) // 2]

    best: int | None = None
    best_dist = 99999
    for midi in candidates:
        dist = abs(midi - prev_midi)
        if dist < best_dist or (dist == best_dist and midi > (best or 0)):
            best = midi
            best_dist = dist
    return best  # type: ignore[return-value]


def choose_closest_in_range(
    prev_midi: int | None,
    chord_midis: list[int],
    lo: int,
    hi: int,
) -> int:
    """
    chord_midis の各音を [lo, hi] 内のオクターブに展開し、
    prev_midi に最も近い音を返す。
    """
    candidates: list[int] = []
    for base in chord_midis:
        # base を [lo, hi] 内に収める全オクターブを列挙
        m = base % 12
        octave_base = (lo // 12) * 12 + m
        if octave_base < lo:
            octave_base += 12
        while octave_base <= hi:
            candidates.append(octave_base)
            octave_base += 12

    if not candidates:
        return lo
    return choose_closest(prev_midi, candidates)
