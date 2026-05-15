#!/usr/bin/env python3
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
"""
競馬予想プログラム
netkeibaのデータを取得してスコアリングで予想順位を表示します。

使い方:
  python main.py --race-id 202506050811
  python main.py --race-id 202506050811 --no-history

race_id の形式:
  YYYY + 競馬場コード(2桁) + 開催回(2桁) + 日数(2桁) + R番号(2桁)
  例: 202506050811 = 2025年 06(阪神) 05回 08日 11R

主な競馬場コード:
  01=札幌 02=函館 03=福島 04=新潟 05=東京
  06=中山 07=中京 08=京都 09=阪神 10=小倉
"""
import argparse
import logging
import sys

from scraper import get_horse_past_results, get_jockey_venue_stats, get_race_entries, get_training_data
from scorer import calculate_pace_distribution, calculate_score, rank

PREDICTION_MARKS = ["◎", "○", "▲", "△", "×"]


def run(race_id: str, use_history: bool = True) -> list[dict]:
    """スクレイピングとスコアリングを実行して結果リストを返す。"""
    print(f"\n{'='*60}")
    print(f"  競馬予想プログラム  |  race_id: {race_id}")
    print(f"{'='*60}")
    print("出走表を取得中...", flush=True)

    try:
        horses = get_race_entries(race_id)
    except Exception as e:
        print(f"\nエラー: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{len(horses)}頭の出走馬を取得しました\n")

    day_num = int(race_id[8:10]) if len(race_id) >= 10 else 1
    venue_code = race_id[4:6] if len(race_id) >= 6 else ""
    num_horses = len(horses)

    # Phase 1: 全馬の過去成績・騎手統計を取得
    all_pasts: list[list[dict]] = []
    for horse in horses:
        past: list[dict] = []
        if use_history and horse.get("horse_id"):
            print(f"  [{horse['number']:>2}] {horse.get('name', '?')} の過去成績を取得中...", flush=True)
            try:
                data = get_horse_past_results(horse["horse_id"])
                past = data["results"]
                horse["sire"] = data.get("sire", "")
                horse["dam_sire"] = data.get("dam_sire", "")
                horse["sire_stats"] = data.get("sire_stats", {})
                horse["dam_sire_stats"] = data.get("dam_sire_stats", {})
            except Exception as e:
                logging.warning("過去成績取得失敗: %s", e)

        if use_history and horse.get("jockey_id"):
            try:
                horse["jockey_win_rate"] = get_jockey_venue_stats(horse["jockey_id"], venue_code)
            except Exception as e:
                logging.warning("騎手統計取得失敗: %s", e)

        all_pasts.append(past)

    # Phase 2: 調教データ取得
    training_map: dict[int, dict] = {}
    if use_history:
        print("調教データを取得中...", flush=True)
        try:
            training_map = get_training_data(race_id)
            if training_map:
                print(f"  調教データ取得: {len(training_map)}頭\n", flush=True)
            else:
                print("  調教データなし（レース前週のみ取得可）\n", flush=True)
        except Exception as e:
            logging.warning("調教データ取得失敗: %s", e)
            print("  調教データ取得失敗\n", flush=True)

    # Phase 3: 脚質分布を算出してスコアリング
    pace_dist = calculate_pace_distribution(all_pasts)

    scored = []
    for horse, past in zip(horses, all_pasts):
        scored.append(calculate_score(
            horse, past,
            day_num=day_num,
            num_horses=num_horses,
            pace_dist=pace_dist,
            jockey_win_rate=horse.get("jockey_win_rate"),
            training=training_map.get(int(horse.get("number", 0))),
        ))

    return rank(scored)


def display(results: list[dict]) -> None:
    """予測結果をコンソールに表示する。"""
    print(f"\n{'='*80}")
    print("  【 予想結果 】")
    print(f"{'='*80}")
    header = (
        f"{'印':^3} {'順':^3} {'馬番':^4} {'馬名':<14} {'騎手':<8} {'オッズ':>6} {'合計':>8}"
        f"  過去 体重 コース 血統 枠番 馬場 脚質 騎手 調教"
    )
    print(header)
    print("-" * 92)

    for r in results:
        mark = PREDICTION_MARKS[r["rank"] - 1] if r["rank"] <= 5 else "  "
        name = r["horse_name"][:12]
        jockey = r["jockey"][:7]
        odds_str = f"{r['odds']:.1f}倍" if r.get("odds") else "  -  "
        g = r.get("grades", {})
        gt  = g.get("total", "-")
        gp  = g.get("past_results", "-")
        gw  = g.get("weight_change", "-")
        gc  = g.get("course_fit", "-")
        gb  = g.get("pedigree", "-")
        gpp = g.get("post_position", "-")
        gtc = g.get("track_condition", "-")
        gpm = g.get("pace_match", "-")
        gjv = g.get("jockey_venue", "-")
        gtr = g.get("training", "-")
        print(
            f"{mark:^3} {r['rank']:>3}  {r['horse_number']:^4}  {name:<14} {jockey:<8}"
            f" {odds_str:>6} {r['total_score']:>3}点[{gt}]"
            f"  {gp:^2}   {gw:^2}    {gc:^2}   {gb:^2}  {gpp:^2}   {gtc:^2}  {gpm:^2}  {gjv:^2}  {gtr:^2}"
        )

    print(f"\n  ※スコアの最高点: 約97点  評価基準: S=超優秀 A=優秀 B=普通 C=やや低 D=低\n")

    print("【 詳細スコア (上位5頭) 】")
    print("-" * 80)
    for r in results[:5]:
        mark = PREDICTION_MARKS[r["rank"] - 1]
        bd = r["breakdown"]
        weight = r["weight_text"] or "不明"
        kinryo = f'{r["kinryo"]}kg' if r.get("kinryo") else "不明"
        odds_str = f"{r['odds']:.1f}倍" if r.get("odds") else "データなし"
        print(f"\n{mark} {r['horse_number']}番 {r['horse_name']}  "
              f"({r.get('sex_age', '')}) 斤量:{kinryo}  馬体重:{weight}  単勝:{odds_str}")
        print(f"    過去成績    : {bd['past_results'][0]:2d}点  {bd['past_results'][1]}")
        print(f"    馬体重変化  : {bd['weight_change'][0]:2d}点  {bd['weight_change'][1]}")
        print(f"    コース適性  : {bd['course_fit'][0]:2d}点  {bd['course_fit'][1]}")
        print(f"    血統適性    : {bd['pedigree'][0]:2d}点  {bd['pedigree'][1]}")
        print(f"    枠番適性    : {bd['post_position'][0]:2d}点  {bd['post_position'][1]}")
        print(f"    馬場状態    : {bd['track_condition'][0]:2d}点  {bd['track_condition'][1]}")
        print(f"    脚質適性    : {bd['pace_match'][0]:2d}点  {bd['pace_match'][1]}")
        print(f"    騎手×会場  : {bd['jockey_venue'][0]:2d}点  {bd['jockey_venue'][1]}")
        print(f"    調教評価    : {bd['training'][0]:2d}点  {bd['training'][1]}")
        print(f"    合計        : {r['total_score']}点")

    print(f"\n{'='*92}")
    print("注意: この予想はエンターテインメント目的です。")
    print("      馬券購入の判断はご自身でお願いします。")
    print(f"{'='*92}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="競馬予想プログラム - netkeibaデータのスコアリング予想",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--race-id",
        metavar="RACE_ID",
        help="ネットケイバのレースID (例: 202506050811)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="過去成績を取得しない (高速モード、精度は下がります)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="デバッグログを表示",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    race_id = args.race_id
    if not race_id:
        print("\n  競馬場コード: 01=札幌 02=函館 03=福島 04=新潟 05=東京")
        print("               06=中山 07=中京 08=京都 09=阪神 10=小倉")
        print("  形式: YYYY + 競馬場(2桁) + 開催回(2桁) + 日数(2桁) + R番号(2桁)")
        race_id = input("\nレースID (12桁) を入力してください: ").strip()
        if not race_id:
            print("レースIDが入力されていません。終了します。")
            sys.exit(1)

        use_history = args.no_history
        ans = input("過去成績を取得しますか？ [Y/n]: ").strip().lower()
        use_history = ans not in ("n", "no")
    else:
        use_history = not args.no_history

    results = run(race_id, use_history=use_history)
    display(results)


if __name__ == "__main__":
    main()
