"""
コース特性データと適性スコア計算モジュール。
2026年版コース特性資料をもとにした統計データを収録。

統計の意味:
  fav_rate    : 1番人気の馬券率 (%)
  fastest_rate: 上がり最速馬の馬券率 (%)
  pace_rate   : 逃げ馬の馬券率 (%)
"""

VENUE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}

# Key: (venue_code, surface_code, distance)
#   venue_code  : '01'〜'10'
#   surface_code: 'T'=芝, 'D'=ダート
#   distance    : メートル (int)
# Value: (fav_rate, fastest_rate, pace_rate)
COURSE_STATS: dict[tuple[str, str, int], tuple[float, float, float]] = {
    # ─────────── 東京 (05) ───────────
    ("05", "T", 1400): (64.4, 54.5, 36.9),
    ("05", "T", 1600): (70.1, 71.5, 37.2),
    ("05", "T", 1800): (72.3, 71.5, 34.3),
    ("05", "T", 2000): (70.2, 76.2, 38.7),
    ("05", "T", 2400): (70.9, 82.1, 32.8),
    ("05", "T", 2500): (71.4, 52.9, 28.6),
    ("05", "D", 1400): (62.5, 58.2, 43.2),
    ("05", "D", 1600): (65.8, 66.5, 35.5),
    # ─────────── 中山 (06) ───────────
    ("06", "T", 1200): (61.1, 41.0, 50.0),
    ("06", "T", 1600): (60.2, 56.9, 39.6),
    ("06", "T", 1800): (64.8, 58.1, 42.1),
    ("06", "T", 2000): (65.2, 62.8, 33.5),
    ("06", "T", 2200): (65.4, 74.2, 31.6),
    ("06", "T", 2500): (74.6, 74.7, 29.2),
    ("06", "D", 1200): (65.0, 52.4, 48.0),
    ("06", "D", 1800): (65.4, 73.2, 44.3),
    # ─────────── 阪神 (09) ───────────
    ("09", "T", 1200): (60.3, 50.0, 66.4),
    ("09", "T", 1400): (63.2, 51.0, 46.1),
    ("09", "T", 1600): (66.4, 67.0, 34.0),
    ("09", "T", 1800): (70.6, 77.6, 39.4),
    ("09", "T", 2000): (66.5, 78.7, 45.9),
    ("09", "T", 2200): (61.9, 79.0, 29.7),
    ("09", "T", 2400): (69.9, 81.2, 33.0),
    ("09", "D", 1400): (66.5, 62.1, 32.7),
    ("09", "D", 1800): (69.0, 80.6, 39.8),
    ("09", "D", 2000): (68.3, 76.2, 27.2),
    # ─────────── 京都 (08) ───────────
    ("08", "T", 1200): (56.5, 38.7, 41.3),
    ("08", "T", 1400): (50.0, 44.3, 38.5),
    ("08", "T", 1600): (59.3, 63.0, 26.4),
    ("08", "T", 1800): (71.9, 72.8, 31.7),
    ("08", "T", 2000): (69.0, 76.1, 39.9),
    ("08", "T", 2200): (64.4, 72.6, 35.0),
    ("08", "T", 2400): (78.9, 77.4, 27.9),
    ("08", "D", 1800): (65.4, 78.6, 43.9),
    ("08", "D", 1900): (72.1, 78.3, 31.0),
    # ─────────── 中京 (07) ───────────
    ("07", "T", 1200): (62.1, 48.2, 42.1),
    ("07", "T", 1400): (60.3, 56.4, 39.2),
    ("07", "T", 1600): (66.2, 61.5, 38.2),
    ("07", "T", 2000): (66.9, 74.4, 43.4),
    ("07", "T", 2200): (69.8, 79.3, 34.3),
    ("07", "D", 1400): (63.3, 60.4, 40.9),
    ("07", "D", 1800): (69.1, 79.1, 42.7),
    ("07", "D", 1900): (66.5, 77.7, 38.5),
    # ─────────── 新潟 (04) ───────────
    ("04", "T", 1000): (61.9, 52.5, 51.9),
    ("04", "T", 1600): (61.8, 68.3, 34.7),
    ("04", "T", 2000): (62.7, 84.5, 30.1),
    ("04", "D", 1800): (64.4, 73.5, 40.4),
    # ─────────── 函館 (02) ───────────
    ("02", "T", 1200): (55.8, 46.8, 46.5),
    ("02", "T", 1800): (70.2, 60.9, 44.4),
    ("02", "T", 2000): (57.6, 63.2, 38.5),
    ("02", "D", 1700): (60.1, 71.0, 47.6),
    # ─────────── 札幌 (01) ───────────
    ("01", "T", 1200): (57.9, 48.0, 51.6),
    ("01", "T", 1800): (77.8, 79.6, 43.9),
    ("01", "T", 2000): (61.2, 68.2, 39.9),
    ("01", "D", 1700): (64.4, 78.3, 31.6),
    # ─────────── 福島 (03) ───────────
    ("03", "T", 1800): (60.5, 63.0, 36.3),
    ("03", "T", 2000): (56.8, 65.1, 31.4),
    # ─────────── 小倉 (10) ───────────
    ("10", "T", 1200): (56.5, 49.9, 45.5),
    ("10", "T", 1800): (66.1, 71.4, 38.5),
    ("10", "T", 2000): (61.1, 71.0, 29.9),
    ("10", "D", 1700): (59.6, 71.3, 44.9),
}


def lookup_course(
    venue_code: str,
    surface: str,
    distance: int,
) -> dict | None:
    """
    コース特性データを返す。完全一致がない場合は最近傍距離で補完。

    Args:
        venue_code: 競馬場コード ('01'〜'10')
        surface   : 馬場種別 ('芝' または 'ダート')
        distance  : 距離 (メートル)

    Returns:
        {'fav_rate': float, 'fastest_rate': float, 'pace_rate': float,
         'approx': bool}  または None (データなし)
    """
    s = "T" if surface == "芝" else "D"

    # 完全一致
    key = (venue_code, s, distance)
    if key in COURSE_STATS:
        fav, fast, pace = COURSE_STATS[key]
        return {"fav_rate": fav, "fastest_rate": fast, "pace_rate": pace, "approx": False}

    # 最近傍距離で補完
    candidates = [
        (abs(d - distance), d)
        for (v, sc, d) in COURSE_STATS
        if v == venue_code and sc == s
    ]
    if candidates:
        _, nearest_dist = min(candidates)
        fav, fast, pace = COURSE_STATS[(venue_code, s, nearest_dist)]
        return {"fav_rate": fav, "fastest_rate": fast, "pace_rate": pace, "approx": True}

    return None


def score_course(
    venue_code: str,
    surface: str,
    distance: int,
    odds: float | None,
    past_results: list[dict],
) -> tuple[int, str]:
    """
    コース適性スコアを計算する。最大15点。

    採点ロジック:
      1. コース信頼度 (0-5pt): 1番人気馬券率が高いほど点数が高い
      2. オッズ×信頼度 (0-7pt): 人気馬ほど得点、かつ信頼度の高いコースで加算
      3. 上がり適性 (0-3pt): 最速上がり率が高いコースで近走好走なら加算

    Returns:
        (score, description)
    """
    if not venue_code or not surface or not distance:
        return 5, "コース情報なし (中間評価)"

    course = lookup_course(venue_code, surface, distance)
    if course is None:
        venue_name = VENUE_NAMES.get(venue_code, venue_code)
        return 5, f"{venue_name} データなし (中間評価)"

    fav_rate = course["fav_rate"]
    fastest_rate = course["fastest_rate"]
    approx = course["approx"]

    # ① コース信頼度ベース (0-5pt)
    if fav_rate >= 72:
        rel_pts = 5
    elif fav_rate >= 68:
        rel_pts = 4
    elif fav_rate >= 64:
        rel_pts = 3
    elif fav_rate >= 60:
        rel_pts = 2
    else:
        rel_pts = 1

    # ② オッズ × 信頼度 (0-7pt)
    # 信頼度係数: 1番人気率50%〜75%を0.0〜1.0にマップ
    rel_factor = min(1.0, max(0.0, (fav_rate - 50.0) / 25.0))
    if odds is not None:
        if odds < 3.0:
            o_raw = 7.0
        elif odds < 6.0:
            o_raw = 5.0
        elif odds < 12.0:
            o_raw = 2.5
        else:
            o_raw = 0.0
        o_pts = round(o_raw * rel_factor)
    else:
        o_pts = 2  # オッズ不明時は中間値

    # ③ 上がり適性 (0-3pt)
    # 最速上がり率が高いコースで近走好走馬を評価
    if past_results:
        top3_count = sum(1 for r in past_results[:3] if r.get("finish", 99) <= 3)
        if fastest_rate >= 75:
            r_pts = min(3, top3_count + 1)
        else:
            r_pts = min(2, top3_count)
    else:
        r_pts = 1  # 過去成績なしは中間値

    total = min(15, rel_pts + o_pts + r_pts)

    # 説明文生成
    venue_name = VENUE_NAMES.get(venue_code, venue_code)
    approx_str = "(近似)" if approx else ""
    desc = (
        f"{venue_name}{surface}{distance}m{approx_str} "
        f"1人気率{fav_rate:.0f}% / 最速率{fastest_rate:.0f}%"
    )
    return total, desc
