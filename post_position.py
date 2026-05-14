"""
枠番適性スコアリングモジュール。
馬番・競走日数・産駒特性からポジションの有利不利を評価する。

スコア (0-10点):
  芝×開幕週(日1-2): 内枠9点 → 外枠3点  (内前有利・先行馬の恩恵が大きい)
  芝×中盤(日3-6) : 内6点 ≒ 外5点      (差はつきにくい)
  芝×後半(日7+)  : 内4点 ← 外7点      (外差し馬場に変わりやすい)
  ダート          : 外枠8点 → 内枠3点   (砂被り回避・スタート主張)
  産駒特性補正    : DIRT_OUTER_BIAS_SIRES × ダート → 内枠-2 / 外枠+2
"""

# ダートで砂被り・揉まれを嫌う傾向のある産駒 (代表的な種牡馬)
DIRT_OUTER_BIAS_SIRES: set[str] = {
    "シニスターミニスター", "パイロ", "ヘニーヒューズ", "カジノドライヴ",
    "スパイツタウン", "ストリートボス", "タイムパラドックス",
    "アメリカンペイトリオット", "バトルプラン", "バーリ",
    "ドレフォン", "クリソベリル",
}

_ZONE_LABEL = {"inner": "内枠", "mid": "中枠", "outer": "外枠"}


def _zone(horse_number: int, num_horses: int) -> str:
    """馬番と頭数から内/中/外を判定する。"""
    ratio = horse_number / max(num_horses, 1)
    if ratio <= 0.30:
        return "inner"
    elif ratio <= 0.70:
        return "mid"
    return "outer"


def score_post_position(
    horse_number,
    num_horses: int,
    surface: str,
    distance: int,
    day_num: int,
    sire: str = "",
    dam_sire: str = "",
) -> tuple[int, str]:
    """
    枠番・開催時期・産駒特性から枠番適性スコアを算出する (0-10点)。

    Args:
        horse_number: 馬番 (int または str)
        num_horses  : 出走頭数
        surface     : "芝" / "ダート" / "障害"
        distance    : レース距離(m)
        day_num     : 開催日数 (race_id[8:10] の整数値)
        sire        : 父馬名
        dam_sire    : 母父馬名
    """
    try:
        n = int(horse_number)
    except (TypeError, ValueError):
        return 5, "枠番不明"

    z = _zone(n, num_horses)
    label = f"{n}番 {_ZONE_LABEL[z]}"

    if surface == "ダート":
        base = {"inner": 3, "mid": 6, "outer": 8}[z]
        label += "(ダート)"
    elif day_num <= 2:
        base = {"inner": 9, "mid": 6, "outer": 3}[z]
        label += "(芝・開幕週)"
        if distance <= 1400 and z == "inner":
            base = min(base + 1, 10)
    elif day_num <= 6:
        base = {"inner": 6, "mid": 6, "outer": 5}[z]
        label += "(芝・中盤)"
    else:
        base = {"inner": 4, "mid": 6, "outer": 7}[z]
        label += "(芝・後半)"

    # 産駒特性補正 (ダートのみ)
    sire_set = {s for s in [sire, dam_sire] if s}
    if surface == "ダート" and sire_set & DIRT_OUTER_BIAS_SIRES:
        if z == "inner":
            base -= 2
            label += " 【砂被りNG-2】"
        elif z == "outer":
            base += 2
            label += " 【砂被りNG+2】"

    return max(0, min(10, base)), label
