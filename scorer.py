"""
各種要素にスコアを付けて馬の予想順位を算出するモジュール。

スコアの内訳 (最大80点):
  単勝オッズ   : 0-25点
  過去成績(3走): 0-30点
  馬体重変化   : 0-10点 (データなし時は5点)
  コース適性   : 0-15点 (コースデータなし時は5点)
"""
from course_data import score_course


def score_odds(odds: float | None) -> tuple[int, str]:
    """単勝オッズのスコア (0-25点)。人気馬ほど高スコア。"""
    if odds is None:
        return 0, "データなし"
    if odds < 2.0:
        return 25, f"{odds:.1f}倍 (断然人気)"
    elif odds < 3.0:
        return 20, f"{odds:.1f}倍 (1番人気圏)"
    elif odds < 5.0:
        return 15, f"{odds:.1f}倍 (上位人気)"
    elif odds < 10.0:
        return 10, f"{odds:.1f}倍 (中位人気)"
    elif odds < 20.0:
        return 6, f"{odds:.1f}倍 (下位人気)"
    elif odds < 50.0:
        return 3, f"{odds:.1f}倍 (低人気)"
    else:
        return 1, f"{odds:.1f}倍 (超低人気)"


def score_past_results(results: list[dict]) -> tuple[int, str]:
    """
    直近3走の着順スコア (0-30点)。

    着順別ポイント: 1着=10, 2着=8, 3着=6, 4着=5, 5着=4,
                   6着=3, 7着=2, 8着=1, 9着以下=0
    """
    if not results:
        return 10, "データなし (中間値)"

    point_map = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
    recent = results[:3]
    total = sum(point_map.get(r["finish"], 0) for r in recent)

    # データが3走未満の場合は平均を3走分に換算
    if len(recent) < 3:
        avg = total / len(recent)
        total = round(avg * 3)

    labels = [f'{r["finish"]}着' for r in recent]
    detail = " → ".join(labels)
    return min(total, 30), detail


def score_weight_change(change: int | None) -> tuple[int, str]:
    """馬体重変化のスコア (0-10点)。変化が小さいほど高スコア。"""
    if change is None:
        return 5, "計不・データなし"
    abs_c = abs(change)
    label = f"{change:+d}kg"
    if abs_c == 0:
        return 10, f"{label} (増減なし)"
    elif abs_c <= 2:
        return 9, f"{label} (微変動)"
    elif abs_c <= 4:
        return 8, f"{label} (小幅変動)"
    elif abs_c <= 8:
        return 6, f"{label} (中程度変動)"
    elif abs_c <= 12:
        return 3, f"{label} (大幅変動)"
    else:
        return 1, f"{label} (極端な変動)"


def calculate_score(horse: dict, past_results: list[dict]) -> dict:
    """
    1頭の総合スコアを計算する。

    Args:
        horse: scraper.get_race_entries() が返す馬辞書
               (venue_code, surface, distance フィールドを含む)
        past_results: scraper.get_horse_past_results() が返す成績リスト

    Returns:
        スコア情報辞書 (horse_number, horse_name, jockey, total_score, breakdown)
    """
    odds_score, odds_label = score_odds(horse.get("odds"))
    past_score, past_label = score_past_results(past_results)
    weight_score, weight_label = score_weight_change(horse.get("weight_change"))
    course_score, course_label = score_course(
        horse.get("venue_code", ""),
        horse.get("surface", ""),
        horse.get("distance", 0),
        horse.get("odds"),
        past_results,
    )

    total = odds_score + past_score + weight_score + course_score

    return {
        "horse_number": horse.get("number", "?"),
        "horse_name": horse.get("name", "不明"),
        "jockey": horse.get("jockey", "不明"),
        "sex_age": horse.get("sex_age", ""),
        "kinryo": horse.get("kinryo"),
        "weight_text": horse.get("weight_text", ""),
        "total_score": total,
        "breakdown": {
            "odds": (odds_score, odds_label),
            "past_results": (past_score, past_label),
            "weight_change": (weight_score, weight_label),
            "course_fit": (course_score, course_label),
        },
    }


def rank(scored_horses: list[dict]) -> list[dict]:
    """スコア降順に並び替えて順位を付ける。"""
    ranked = sorted(scored_horses, key=lambda h: h["total_score"], reverse=True)
    for i, h in enumerate(ranked, 1):
        h["rank"] = i
    return ranked
