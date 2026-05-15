"""
各種要素にスコアを付けて馬の予想順位を算出するモジュール。

スコアの内訳 (最大97点):
  過去成績(3走): 0-30点  ※ G1/G2/G3は着順ポイントにグレード係数を乗算
  馬体重変化   : 0-10点 (データなし時は5点、前走太め絞りはボーナス)
  コース適性   : 0-15点 (コースデータなし時は5点)
  血統適性     : -6~15点 (血統S該当時に+3ボーナス含む)
  枠番適性     : 0-10点 (馬場×開催時期×産駒特性)
  馬場状態適性 : 0-8点  (同条件の過去成績平均着順)
  脚質マッチング: 0-6点  (レースのペース傾向との相性)
  騎手×会場   : 0-5点  (会場勝率ボーナス、データなし=0)
  調教評価     : 0-8点  (レター評価A/B/C + ポジティブテキストボーナス)
"""
from course_data import score_course
from pedigree_data import score_pedigree
from post_position import score_post_position

# グレード別の着順ポイント乗算係数
GRADE_MULTIPLIER: dict[str, float] = {
    "G1": 1.5,
    "G2": 1.3,
    "G3": 1.2,
    "重賞": 1.1,
}


def _time_diff_to_base(time_diff: float) -> int:
    """着差(秒)を1走あたりの基礎点(0-10)に変換する。"""
    if time_diff <= 0.0:
        return 10
    elif time_diff <= 0.2:
        return 9
    elif time_diff <= 0.4:
        return 8
    elif time_diff <= 0.6:
        return 6
    elif time_diff <= 0.9:
        return 4
    elif time_diff <= 1.3:
        return 2
    elif time_diff <= 1.8:
        return 1
    return 0


_FINISH_POINT_MAP = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}


def score_past_results(results: list[dict]) -> tuple[int, str]:
    """
    直近3走のスコア (0-30点)。着差データがあれば秒差で、なければ着順で評価する。
    グレードレースは係数で加重する。

    着差ベース: 0.0s=10, ≤0.2=9, ≤0.4=8, ≤0.6=6, ≤0.9=4, ≤1.3=2, ≤1.8=1, >1.8=0
    着順ベース: 1着=10, 2着=8, 3着=6, 4着=5, 5着=4, 6着=3, 7着=2, 8着=1
    グレード係数: G1=×1.5, G2=×1.3, G3=×1.2, 重賞=×1.1
    """
    if not results:
        return 10, "データなし (中間値)"

    recent = results[:3]
    total = 0.0
    labels = []

    for r in recent:
        finish = r.get("finish", 99)
        grade = r.get("grade", "")
        time_diff = r.get("time_diff")
        mult = GRADE_MULTIPLIER.get(grade, 1.0)

        if finish == 1:
            base = 10
            label = "1着"
        elif time_diff is not None and time_diff > 0:
            base = _time_diff_to_base(time_diff)
            label = f"{finish}着(+{time_diff:.1f}秒)"
        else:
            base = _FINISH_POINT_MAP.get(finish, 0)
            label = f"{finish}着"

        if grade:
            label += f"[{grade}]"
        labels.append(label)
        total += base * mult

    total_int = round(total)

    if len(recent) < 3:
        avg = total / len(recent)
        total_int = round(avg * 3)

    return min(total_int, 30), " → ".join(labels)


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


def score_track_condition(current_cond: str, past_results: list[dict]) -> tuple[int, str]:
    """同条件の過去成績平均着順から馬場状態適性スコアを算出する (0-8点)。"""
    if not current_cond:
        return 4, "馬場情報なし"
    if not past_results:
        return 4, f"{current_cond} (実績なし)"

    same = [r for r in past_results if r.get("track_condition") == current_cond]
    if not same:
        return 4, f"{current_cond} 同条件実績なし"

    finishes = [r["finish"] for r in same if r.get("finish", 99) <= 18]
    if not finishes:
        return 4, f"{current_cond} {len(same)}走 (着順不明)"

    avg = sum(finishes) / len(finishes)
    count = len(same)

    if avg <= 2.0:
        sc = 8
    elif avg <= 3.5:
        sc = 7
    elif avg <= 5.0:
        sc = 6
    elif avg <= 7.0:
        sc = 5
    else:
        sc = 2

    return sc, f"{current_cond} {count}走 平均{avg:.1f}着"


def calculate_pace_distribution(all_pasts: list[list[dict]]) -> dict[str, int]:
    """全出走馬の直近1走脚質を集計して分布を返す。"""
    dist: dict[str, int] = {"逃": 0, "先": 0, "差": 0, "追": 0}
    for past in all_pasts:
        if past:
            pace = past[0].get("pace", "")
            if pace in dist:
                dist[pace] += 1
    return dist


def score_pace_match(horse_pace: str, pace_dist: dict[str, int]) -> tuple[int, str]:
    """脚質マッチングスコア (0-6点)。ペース傾向と馬の脚質の相性を評価する。"""
    if not horse_pace or not pace_dist:
        return 3, "脚質データなし"

    total = sum(pace_dist.values())
    if total == 0:
        return 3, "脚質データなし"

    front = pace_dist.get("逃", 0) + pace_dist.get("先", 0)
    ratio = front / total

    if ratio >= 0.55:
        adj = {"逃": -1, "先": 0, "差": 2, "追": 1}.get(horse_pace, 0)
        pace_label = "前傾"
    elif ratio <= 0.30:
        adj = {"逃": 3, "先": 2, "差": -1, "追": -2}.get(horse_pace, 0)
        pace_label = "スロー"
    else:
        adj = {"逃": 0, "先": 1, "差": 1, "追": 0}.get(horse_pace, 0)
        pace_label = "平均"

    sign = f"+{adj}" if adj >= 0 else str(adj)
    return max(0, min(6, 3 + adj)), f"{horse_pace}({pace_label}ペース {sign})"


_TRAINING_POSITIVE = frozenset([
    "気配抜群", "文句なし", "態勢万全", "絶好調", "最高潮",
    "気配最高", "状態万全", "仕上がり抜群", "馬体目立",
])


def score_training(training: dict | None) -> tuple[int, str]:
    """追い切り評価スコア (0-8点)。
    レター評価: A→7, B→4, C→2, なし→3
    超ポジティブテキスト: +1ボーナス
    """
    if not training:
        return 3, "データなし"
    grade = training.get("grade", "")
    text = training.get("text", "")
    base = {"A": 7, "B": 4, "C": 2}.get(grade, 3)
    bonus = 1 if text in _TRAINING_POSITIVE else 0
    label = f"{text}[{grade}]" if grade else (text or "データなし")
    return min(8, base + bonus), label


def score_jockey_venue(win_rate: float | None) -> tuple[int, str]:
    """騎手×会場勝率ボーナス (0-5pt)。データなし=0pt（下振れなし）。"""
    if win_rate is None:
        return 0, "データなし"
    pct = win_rate * 100
    label = f"会場勝率 {pct:.1f}%"
    if win_rate >= 0.20:
        return 5, label
    elif win_rate >= 0.15:
        return 4, label
    elif win_rate >= 0.10:
        return 3, label
    elif win_rate >= 0.07:
        return 2, label
    elif win_rate >= 0.04:
        return 1, label
    return 0, label


_GRADE_THRESHOLDS: dict[str, list[tuple[int, str]]] = {
    "past_results":    [(25, "S"), (20, "A"), (14, "B"), (8, "C"), (0, "D")],
    "weight_change":   [(10, "S"), (8, "A"), (6, "B"), (3, "C"), (0, "D")],
    "course_fit":      [(13, "S"), (10, "A"), (7, "B"), (5, "C"), (0, "D")],
    "pedigree":        [(10, "S"), (7, "A"), (4, "B"), (0, "C"), (-99, "D")],
    "post_position":   [(9, "S"), (7, "A"), (5, "B"), (3, "C"), (0, "D")],
    "track_condition": [(7, "S"), (6, "A"), (5, "B"), (3, "C"), (0, "D")],
    "pace_match":      [(5, "S"), (4, "A"), (3, "B"), (1, "C"), (0, "D")],
    "jockey_venue":    [(5, "S"), (4, "A"), (3, "B"), (1, "C"), (0, "D")],
    "training":        [(8, "S"), (7, "A"), (4, "B"), (2, "C"), (0, "D")],
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


def calculate_score(
    horse: dict,
    past_results: list[dict],
    day_num: int = 1,
    num_horses: int = 16,
    pace_dist: dict | None = None,
    jockey_win_rate: float | None = None,
    training: dict | None = None,
) -> dict:
    """
    1頭の総合スコアを計算する。

    Args:
        horse: scraper.get_race_entries() が返す馬辞書
               (venue_code, surface, distance, track_condition フィールドを含む)
               sire_stats / dam_sire_stats は get_horse_past_results() が付与
        past_results: scraper.get_horse_past_results() が返す成績リスト
                      各要素に grade / surface / distance / pace /
                      track_condition / weight フィールドを含む
        day_num   : 開催日数 (race_id[8:10] の整数値)
        num_horses: 出走頭数
        pace_dist : 全出走馬の脚質分布 (calculate_pace_distribution の返り値)
        training  : get_training_data() の馬番辞書から取得した当該馬のデータ

    Returns:
        スコア情報辞書 (horse_number, horse_name, jockey, total_score, breakdown, grades)
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

    post_score, post_label = score_post_position(
        horse.get("number", 0),
        num_horses,
        horse.get("surface", ""),
        horse.get("distance", 0),
        day_num,
        horse.get("sire", ""),
        horse.get("dam_sire", ""),
    )

    track_score, track_label = score_track_condition(
        horse.get("track_condition", ""),
        past_results,
    )

    horse_pace = past_results[0].get("pace", "") if past_results else ""
    pace_score, pace_label = score_pace_match(horse_pace, pace_dist or {})

    jockey_score, jockey_label = score_jockey_venue(jockey_win_rate)
    training_score, training_label = score_training(training)

    total = (
        past_score + weight_score + course_score + pedigree_score
        + post_score + track_score + pace_score + jockey_score
        + training_score
    )

    breakdown = {
        "past_results":    (past_score, past_label),
        "weight_change":   (weight_score, weight_label),
        "course_fit":      (course_score, course_label),
        "pedigree":        (pedigree_score, pedigree_label),
        "post_position":   (post_score, post_label),
        "track_condition": (track_score, track_label),
        "pace_match":      (pace_score, pace_label),
        "jockey_venue":    (jockey_score, jockey_label),
        "training":        (training_score, training_label),
    }

    grades = factor_grades(breakdown)
    grades["total"] = next(
        letter for min_s, letter in [(71, "S"), (58, "A"), (45, "B"), (32, "C"), (0, "D")]
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
