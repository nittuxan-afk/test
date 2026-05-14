"""
各種要素にスコアを付けて馬の予想順位を算出するモジュール。

スコアの内訳 (最大70点):
  過去成績(3走): 0-30点  ※ G1/G2/G3は着順ポイントにグレード係数を乗算
  馬体重変化   : 0-10点 (データなし時は5点)
  コース適性   : 0-15点 (コースデータなし時は5点)
  血統適性     : -6~15点 (血統S該当時に+3ボーナス含む)
"""
from course_data import score_course
from pedigree_data import score_pedigree

# グレード別の着順ポイント乗算係数
GRADE_MULTIPLIER: dict[str, float] = {
    "G1": 1.5,
    "G2": 1.3,
    "G3": 1.2,
    "重賞": 1.1,
}


def score_past_results(results: list[dict]) -> tuple[int, str]:
    """
    直近3走の着順スコア (0-30点)。グレードレースは係数で加重する。

    着順別ポイント: 1着=10, 2着=8, 3着=6, 4着=5, 5着=4,
                   6着=3, 7着=2, 8着=1, 9着以下=0
    グレード係数: G1=×1.5, G2=×1.3, G3=×1.2, 重賞=×1.1
    """
    if not results:
        return 10, "データなし (中間値)"

    point_map = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
    recent = results[:3]

    total = 0.0
    for r in recent:
        base = point_map.get(r.get("finish", 99), 0)
        mult = GRADE_MULTIPLIER.get(r.get("grade", ""), 1.0)
        total += base * mult

    total_int = round(total)

    # データが3走未満の場合は平均を3走分に換算
    if len(recent) < 3:
        avg = total / len(recent)
        total_int = round(avg * 3)

    labels = []
    for r in recent:
        finish = r.get("finish", 99)
        grade = r.get("grade", "")
        label = f"{finish}着"
        if grade:
            label += f"({grade})"
        labels.append(label)

    detail = " → ".join(labels)
    return min(total_int, 30), detail


def _is_rebound_loss(past_results: list[dict] | None, threshold: int = 6) -> bool:
    """前走が大幅増量だったか判定（今回の大幅減が「前走太め→絞り」かどうか）。"""
    if not past_results or len(past_results) < 2:
        return False
    w0 = past_results[0].get("weight")
    w1 = past_results[1].get("weight")
    if w0 is None or w1 is None:
        return False
    return (w0 - w1) >= threshold


def score_weight_change(change: int | None, past_results: list[dict] | None = None) -> tuple[int, str]:
    """馬体重変化のスコア (0-10点)。変化が小さいほど高スコア。
    大幅減の場合、前走が大幅増加（太め）なら絞り込みとしてボーナス評価する。"""
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
        if change < 0:
            if _is_rebound_loss(past_results):
                return 7, f"{label} (前走太め→絞り込み)"
            return 4, f"{label} (体重絞り)"
        return 3, f"{label} (大幅増加)"
    else:
        if change < 0:
            if _is_rebound_loss(past_results):
                return 5, f"{label} (前走大幅太め→絞り込み)"
            return 2, f"{label} (大幅絞り)"
        return 1, f"{label} (極端な増加)"


_GRADE_THRESHOLDS: dict[str, list[tuple[int, str]]] = {
    "past_results": [(25, "S"), (20, "A"), (14, "B"), (8, "C"), (0, "D")],
    "weight_change": [(10, "S"), (8, "A"), (6, "B"), (3, "C"), (0, "D")],
    "course_fit":    [(13, "S"), (10, "A"), (7, "B"), (5, "C"), (0, "D")],
    "pedigree":      [(10, "S"), (7, "A"), (4, "B"), (0, "C"), (-99, "D")],
}


def factor_grades(breakdown: dict) -> dict[str, str]:
    """各ファクターのスコアをS~Dのレター評価に変換する。"""
    grades = {}
    for key, thresholds in _GRADE_THRESHOLDS.items():
        score = breakdown[key][0]
        for min_score, letter in thresholds:
            if score >= min_score:
                grades[key] = letter
                break
    return grades


def calculate_score(horse: dict, past_results: list[dict]) -> dict:
    """
    1頭の総合スコアを計算する。

    Args:
        horse: scraper.get_race_entries() が返す馬辞書
               (venue_code, surface, distance フィールドを含む)
               sire_stats / dam_sire_stats は get_horse_past_results() が付与
        past_results: scraper.get_horse_past_results() が返す成績リスト
                      各要素に grade / surface / distance / pace フィールドを含む

    Returns:
        スコア情報辞書 (horse_number, horse_name, jockey, total_score, breakdown)
    """
    past_score, past_label = score_past_results(past_results)
    weight_score, weight_label = score_weight_change(horse.get("weight_change"), past_results)
    course_score, course_label = score_course(
        horse.get("venue_code", ""),
        horse.get("surface", ""),
        horse.get("distance", 0),
        past_results,
    )
    pedigree_score, pedigree_label = score_pedigree(
        horse.get("venue_code", ""),
        horse.get("surface", ""),
        horse.get("distance", 0),
        horse.get("sire", ""),
        horse.get("dam_sire", ""),
        horse.get("sex_age", ""),
        horse.get("sire_stats", {}),
        horse.get("dam_sire_stats", {}),
    )

    # 血統Sボーナス: 父/母父が最高適性クラスの場合に加点
    if pedigree_score >= 10:
        pedigree_score += 3
        pedigree_label += " 【血統S+3】"

    total = past_score + weight_score + course_score + pedigree_score

    breakdown = {
        "past_results": (past_score, past_label),
        "weight_change": (weight_score, weight_label),
        "course_fit": (course_score, course_label),
        "pedigree": (pedigree_score, pedigree_label),
    }

    grades = factor_grades(breakdown)
    grades["total"] = next(
        letter for min_s, letter in [(55, "S"), (45, "A"), (35, "B"), (25, "C"), (0, "D")]
        if total >= min_s
    )

    return {
        "horse_number": horse.get("number", "?"),
        "horse_name": horse.get("name", "不明"),
        "jockey": horse.get("jockey", "不明"),
        "sex_age": horse.get("sex_age", ""),
        "kinryo": horse.get("kinryo"),
        "weight_text": horse.get("weight_text", ""),
        "odds": horse.get("odds"),
        "total_score": total,
        "breakdown": breakdown,
        "grades": grades,
    }


def rank(scored_horses: list[dict]) -> list[dict]:
    """スコア降順に並び替えて順位を付ける。"""
    ranked = sorted(scored_horses, key=lambda h: h["total_score"], reverse=True)
    for i, h in enumerate(ranked, 1):
        h["rank"] = i
    return ranked
