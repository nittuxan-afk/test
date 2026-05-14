"""
netkeiba.com から出走表・過去成績をスクレイピングするモジュール。
利用にあたっては netkeiba の利用規約を確認してください。
"""
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}
REQUEST_INTERVAL = 1.5  # サーバー負荷軽減のためリクエスト間隔(秒)

# 種牡馬統計のインメモリキャッシュ（同一種牡馬の重複取得を防ぐ）
_sire_stats_cache: dict[str, dict] = {}


def _fetch(url: str) -> BeautifulSoup:
    """URLを取得してBeautifulSoupを返す。EUC-JP/UTF-8を自動判定。"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    content = resp.content
    # netkeibaはページによってEUC-JPを使う
    for enc in ("utf-8", "euc-jp", "shift_jis"):
        try:
            decoded = content.decode(enc)
            if any(ord(c) > 0x3000 for c in decoded[:1000]):
                time.sleep(REQUEST_INTERVAL)
                return BeautifulSoup(decoded, "html.parser")
        except (UnicodeDecodeError, LookupError):
            continue

    time.sleep(REQUEST_INTERVAL)
    return BeautifulSoup(content, "html.parser")


def get_race_entries(race_id: str) -> list[dict]:
    """
    出走表を取得して馬リストを返す。

    Args:
        race_id: ネットケイバのレースID (例: '202506050811')
                 形式: YYYY(年) + RR(場コード) + CC(開催回) + DD(日) + HH(R番号)

    Returns:
        馬の情報リスト。各辞書のキー:
        number, name, horse_id, sex_age, kinryo, jockey, jockey_id,
        trainer, weight, weight_change, weight_text, odds,
        venue_code, surface, distance
    """
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    logger.info("出走表取得: %s", url)
    soup = _fetch(url)

    table = _find_shutuba_table(soup)
    if table is None:
        raise ValueError(f"出走表テーブルが見つかりません (race_id={race_id})")

    # race_id[4:6] が競馬場コード
    venue_code = race_id[4:6] if len(race_id) >= 6 else ""
    race_info = _parse_race_info(soup, venue_code)

    horses = []
    all_rows = table.find_all("tr")

    # HorseList クラスで絞る。なければ horse リンクを含む行を使う
    candidate_rows = [r for r in all_rows if "HorseList" in " ".join(r.get("class", []))]
    if not candidate_rows:
        logger.debug(
            "HorseList クラスが見つかりません。tr クラス一覧: %s",
            list({" ".join(r.get("class", [])) for r in all_rows if r.get("class")}),
        )
        candidate_rows = [r for r in all_rows if r.find("a", href=re.compile(r"/horse/"))]

    for row in candidate_rows:
        horse = _parse_entry_row(row)
        if horse:
            horse.update(race_info)
            horses.append(horse)

    if not horses:
        raise ValueError(f"出走馬が見つかりません (race_id={race_id})")

    # HTML からオッズが取れなかった場合は API で補完
    if not any(h.get("odds") for h in horses):
        logger.debug("HTMLからオッズ未取得のため API で補完します")
        _fill_odds_from_api(race_id, horses)

    return horses


def _fill_odds_from_api(race_id: str, horses: list[dict]) -> None:
    """netkeibaの単勝オッズAPIから各馬のオッズを取得して horses に書き込む。"""
    url = (
        "https://race.netkeiba.com/api/api_get_jra_odds.html"
        f"?race_id={race_id}&type=1&action=update"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # レスポンス形式: {"status":"result","data":{"odds":{"1":{"01":["3.5",...],...},...}}}
        # "1" が単勝種別キー、その中が馬番(ゼロ埋め2桁)→[オッズ,...]
        odds_map: dict = (
            data.get("data", {}).get("odds", {}).get("1", {})
            or data.get("odds", {}).get("1", {})
        )
        for horse in horses:
            num = str(horse.get("number", "")).zfill(2).lstrip("0") or str(horse.get("number", ""))
            for key in (num, num.zfill(2)):
                entry = odds_map.get(key)
                if entry:
                    try:
                        horse["odds"] = float(entry[0])
                    except (ValueError, IndexError, TypeError):
                        pass
                    break
        logger.debug("APIオッズ取得完了")
    except Exception as e:
        logger.warning("オッズAPI取得失敗: %s", e)


def _parse_race_info(soup: BeautifulSoup, venue_code: str) -> dict:
    """出走表ページからレース情報 (馬場・距離) を解析する。"""
    info: dict = {"venue_code": venue_code, "surface": "", "distance": 0}

    # 候補テキストを広く探す
    # 対象: "芝1600m", "ダ1400m", "ダート1400m", "障1600m" 等
    surface_map = {"芝": "芝", "ダ": "ダート", "ダート": "ダート", "障": "障害"}
    pattern = re.compile(r"(芝|ダート|ダ|障)[\s　]*(\d{3,4})\s*m", re.IGNORECASE)

    # RaceData01 / Race_Data / RaceData 等の div を優先して探す
    for cls_name in ("RaceData01", "Race_Data01", "RaceData", "Race_Data"):
        tag = soup.find(class_=cls_name)
        if tag:
            m = pattern.search(tag.get_text())
            if m:
                info["surface"] = surface_map.get(m.group(1), m.group(1))
                info["distance"] = int(m.group(2))
                return info

    # フォールバック: ページ全体のテキストから探す
    for text in soup.stripped_strings:
        m = pattern.match(text)
        if m:
            info["surface"] = surface_map.get(m.group(1), m.group(1))
            info["distance"] = int(m.group(2))
            return info

    return info


def _find_shutuba_table(soup: BeautifulSoup):
    """出走表のtableタグを返す。class名が変わっていてもフォールバックで探す。"""
    # 1. 既知クラス名（複数クラスでも部分一致）
    for cls in ("Shutuba_Table", "ShutubaTable", "RaceTable01"):
        t = soup.find("table", class_=cls)
        if t:
            return t
    # 2. HorseList 行を含むテーブル
    for t in soup.find_all("table"):
        if t.find("tr", class_=re.compile(r"HorseList")):
            return t
    # 3. /horse/ リンクを複数含むテーブル（クラス名変更に対応）
    for t in soup.find_all("table"):
        if len(t.find_all("a", href=re.compile(r"/horse/"))) >= 3:
            return t
    return None


def _parse_entry_row(row) -> dict | None:
    """TR要素から1頭分の情報を解析する。クラス名ベース → 位置・リンクベースの順でフォールバック。"""
    horse: dict = {}

    for td in row.find_all("td"):
        cls = " ".join(td.get("class", []))
        text = td.get_text(strip=True)

        if "Umaban" in cls and not horse.get("number"):
            horse["number"] = text

        elif "HorseName" in cls and not horse.get("name"):
            horse["name"] = text
            a = td.find("a", href=re.compile(r"/horse/"))
            if a:
                m = re.search(r"/horse/(\w+)", a["href"])
                if m:
                    horse["horse_id"] = m.group(1)

        elif re.search(r"Barei|SexAge", cls) and not horse.get("sex_age"):
            horse["sex_age"] = text

        elif "Jockey" in cls and not horse.get("jockey"):
            a = td.find("a")
            if a:
                horse["jockey"] = a.get_text(strip=True)
                m = re.search(r"/jockey/\w+/(\w+)", a.get("href", ""))
                if m:
                    horse["jockey_id"] = m.group(1)
            else:
                horse["jockey"] = text

        elif "Trainer" in cls and not horse.get("trainer"):
            a = td.find("a")
            horse["trainer"] = (a or td).get_text(strip=True)

        elif re.search(r"^Weight$", cls) and not horse.get("weight_text"):
            horse["weight_text"] = text
            m = re.match(r"(\d+)\(([+-]?\d+)\)", text)
            if m:
                horse["weight"] = int(m.group(1))
                horse["weight_change"] = int(m.group(2))

        elif re.search(r"Odds|Tansho", cls) and not horse.get("odds"):
            try:
                horse["odds"] = float(text)
            except ValueError:
                pass

    # ── クラス名ベースで馬名が取れなかった場合、horse リンクから取得 ──
    if not horse.get("name"):
        a = row.find("a", href=re.compile(r"/horse/"))
        if a:
            horse["name"] = a.get_text(strip=True)
            m = re.search(r"/horse/(\w+)", a["href"])
            if m:
                horse["horse_id"] = m.group(1)

    # ── 馬番: 1〜18の数字セルをフォールバック ──
    if not horse.get("number") and horse.get("name"):
        for td in row.find_all("td"):
            t = td.get_text(strip=True)
            if re.match(r"^(1[0-8]|[1-9])$", t):
                horse["number"] = t
                break

    # ── 斤量: Jockeyの直前セルを推定 ──
    if not horse.get("kinryo"):
        _try_extract_kinryo(row, horse)

    # ── 馬体重: 数字(±数字) パターンをフォールバック ──
    if not horse.get("weight_text"):
        for td in row.find_all("td"):
            t = td.get_text(strip=True)
            m = re.match(r"(\d{3})\(([+-]?\d+)\)", t)
            if m:
                horse["weight_text"] = t
                horse["weight"] = int(m.group(1))
                horse["weight_change"] = int(m.group(2))
                break

    # ── オッズ: 馬体重セルの直後から探す（斤量との混同を防ぐ）──
    if not horse.get("odds"):
        tds = row.find_all("td")
        weight_idx = next(
            (i for i, td in enumerate(tds)
             if re.match(r"\d{3}\([+-]?\d+\)", td.get_text(strip=True))),
            None,
        )
        if weight_idx is not None:
            for td in tds[weight_idx + 1: weight_idx + 4]:
                t = td.get_text(strip=True)
                try:
                    val = float(t)
                    if val >= 1.0:
                        horse["odds"] = val
                        break
                except ValueError:
                    pass

    return horse if horse.get("name") else None


def _try_extract_kinryo(row, horse: dict) -> None:
    """斤量セルを位置ベースで推定して取得する。"""
    tds = row.find_all("td")
    jockey_idx = None
    for i, td in enumerate(tds):
        if "Jockey" in " ".join(td.get("class", [])):
            jockey_idx = i
            break
    if jockey_idx and jockey_idx > 0:
        candidate = tds[jockey_idx - 1].get_text(strip=True)
        try:
            val = float(candidate)
            if 40.0 <= val <= 65.0:  # 斤量の妥当な範囲
                horse["kinryo"] = val
        except ValueError:
            pass


def _fetch_ajax_html(endpoint: str, horse_id: str) -> "BeautifulSoup | None":
    """AJAXエンドポイントからJSONを取得し、data フィールドのHTMLをBeautifulSoupで返す。"""
    url = f"https://db.netkeiba.com/horse/{endpoint}"
    params = {"input": "UTF-8", "output": "json", "id": horse_id}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "OK":
            time.sleep(REQUEST_INTERVAL)
            return BeautifulSoup(data["data"], "html.parser")
        logger.warning("AJAX status!=OK (%s, horse_id=%s): %s", endpoint, horse_id, data.get("status"))
    except Exception as e:
        logger.warning("AJAX取得失敗 (%s, horse_id=%s): %s", endpoint, horse_id, e)
    return None


def get_horse_past_results(horse_id: str, limit: int = 5) -> dict:
    """
    AJAXエンドポイントから過去成績と血統情報を取得する。
    netkeibaの馬詳細ページは成績・血統をJSで動的挿入するため、
    静的HTMLでなく専用AJAXを直接呼ぶ。

    Args:
        horse_id: 馬ID (例: '2019105678')
        limit: 取得する最大レース数

    Returns:
        {
          'results': list[dict],  # date, venue, finish, grade, surface, distance, pace
          'sire': str,
          'dam_sire': str,
          'sire_ped_id': str,
          'dam_sire_ped_id': str,
          'sire_stats': dict,     # preferred_surface, preferred_distance
          'dam_sire_stats': dict,
        }
    """
    logger.info("過去成績取得 (horse_id=%s)", horse_id)

    # 血統（父・母父の名前とped_id）
    pedigree_soup = _fetch_ajax_html("ajax_horse_pedigree.html", horse_id)
    if pedigree_soup:
        sire, dam_sire, sire_ped_id, dam_sire_ped_id = _parse_pedigree(pedigree_soup)
    else:
        sire = dam_sire = sire_ped_id = dam_sire_ped_id = ""

    # 種牡馬Web統計（キャッシュ済みなら即返す）
    sire_stats = _get_sire_stats(sire_ped_id) if sire_ped_id else {}
    dam_sire_stats = _get_sire_stats(dam_sire_ped_id) if dam_sire_ped_id else {}

    # 過去成績
    results_soup = _fetch_ajax_html("ajax_horse_results.html", horse_id)
    if results_soup is None:
        return {
            "results": [], "sire": sire, "dam_sire": dam_sire,
            "sire_ped_id": sire_ped_id, "dam_sire_ped_id": dam_sire_ped_id,
            "sire_stats": sire_stats, "dam_sire_stats": dam_sire_stats,
        }

    table = _find_results_table(results_soup)
    if table is None:
        logger.warning("成績テーブルが見つかりません (horse_id=%s)", horse_id)
        return {
            "results": [], "sire": sire, "dam_sire": dam_sire,
            "sire_ped_id": sire_ped_id, "dam_sire_ped_id": dam_sire_ped_id,
            "sire_stats": sire_stats, "dam_sire_stats": dam_sire_stats,
        }

    results = []
    rows = table.find_all("tr")[1:]  # ヘッダー行をスキップ
    for row in rows[:limit]:
        tds = row.find_all("td")
        if len(tds) < 12:
            continue
        result = _parse_result_row(tds)
        if result:
            results.append(result)

    return {
        "results": results,
        "sire": sire,
        "dam_sire": dam_sire,
        "sire_ped_id": sire_ped_id,
        "dam_sire_ped_id": dam_sire_ped_id,
        "sire_stats": sire_stats,
        "dam_sire_stats": dam_sire_stats,
    }


def _parse_pedigree(soup: BeautifulSoup) -> tuple[str, str, str, str]:
    """
    血統テーブルから父(sire)・母父(dam_sire)とそのped_idを取得する。
    Returns: (sire_name, dam_sire_name, sire_ped_id, dam_sire_ped_id)
    """
    sire = dam_sire = sire_ped_id = dam_sire_ped_id = ""

    # Strategy 1: blood_table / blood 系クラスのテーブル
    blood_table = (
        soup.find("table", class_="blood_table")
        or soup.find("table", class_=re.compile(r"blood", re.I))
    )
    if blood_table:
        tds = blood_table.find_all("td")
        for td in tds:
            cls_set = set(td.get("class", []))
            a = td.find("a")
            text = (a.get_text(strip=True) if a else td.get_text(strip=True))
            if not text or text in ("－", "-", ""):
                continue

            if cls_set & {"b_01", "b_02"} and not sire:
                sire = text
                if a:
                    m = re.search(r"/horse/ped/(\w+)", a.get("href", ""))
                    if m:
                        sire_ped_id = m.group(1)

            elif cls_set & {"b_04", "b_05", "b_06"} and not dam_sire:
                dam_sire = text
                if a:
                    m = re.search(r"/horse/ped/(\w+)", a.get("href", ""))
                    if m:
                        dam_sire_ped_id = m.group(1)

        # 位置ベースフォールバック: 有効セルの1番目=父, 4〜5番目=母父
        if not sire or not dam_sire:
            valid = [td for td in tds
                     if td.get_text(strip=True) not in ("", "－", "-")]
            if not sire and valid:
                a = valid[0].find("a")
                sire = (a.get_text(strip=True) if a else valid[0].get_text(strip=True))
                if a:
                    m = re.search(r"/horse/ped/(\w+)", a.get("href", ""))
                    if m and not sire_ped_id:
                        sire_ped_id = m.group(1)
            if not dam_sire:
                for td in valid[3:6]:
                    a = td.find("a")
                    candidate = (a.get_text(strip=True) if a else td.get_text(strip=True))
                    if candidate and candidate != sire:
                        dam_sire = candidate
                        if a and not dam_sire_ped_id:
                            m = re.search(r"/horse/ped/(\w+)", a.get("href", ""))
                            if m:
                                dam_sire_ped_id = m.group(1)
                        break

    # Strategy 2: 「父」「母父」ラベルの隣セルを探す (th または td)
    if not sire or not dam_sire:
        for cell in soup.find_all(["th", "td"]):
            label = cell.get_text(strip=True)
            if label not in ("父", "母父"):
                continue
            parent_tr = cell.find_parent("tr")
            if not parent_tr:
                continue
            cells_in_row = parent_tr.find_all(["th", "td"])
            for i, c in enumerate(cells_in_row):
                if c == cell and i + 1 < len(cells_in_row):
                    next_cell = cells_in_row[i + 1]
                    a = next_cell.find("a")
                    val = (a.get_text(strip=True) if a else next_cell.get_text(strip=True))
                    if label == "父" and not sire:
                        sire = val
                        if a and not sire_ped_id:
                            m = re.search(r"/horse/ped/(\w+)", a.get("href", ""))
                            if m:
                                sire_ped_id = m.group(1)
                    elif label == "母父" and not dam_sire:
                        dam_sire = val
                        if a and not dam_sire_ped_id:
                            m = re.search(r"/horse/ped/(\w+)", a.get("href", ""))
                            if m:
                                dam_sire_ped_id = m.group(1)
                    break

    # Strategy 3: /horse/ped/ リンクを4件以上含むテーブルから位置で推定
    if not sire:
        for t in soup.find_all("table"):
            links = [a for a in t.find_all("a", href=re.compile(r"/horse/ped/"))]
            if len(links) >= 4:
                sire = links[0].get_text(strip=True)
                if not sire_ped_id:
                    m = re.search(r"/horse/ped/(\w+)", links[0].get("href", ""))
                    if m:
                        sire_ped_id = m.group(1)
                if len(links) > 3:
                    dam_sire = links[3].get_text(strip=True)
                    if not dam_sire_ped_id:
                        m = re.search(r"/horse/ped/(\w+)", links[3].get("href", ""))
                        if m:
                            dam_sire_ped_id = m.group(1)
                break

    logger.debug("血統取得結果: 父=%s(%s) 母父=%s(%s)", sire, sire_ped_id, dam_sire, dam_sire_ped_id)
    return sire, dam_sire, sire_ped_id, dam_sire_ped_id


def _get_sire_stats(ped_id: str) -> dict:
    """
    種牡馬の芝/ダート・距離カテゴリ別成績をnetkeibaから取得する。
    キャッシュを使い、同一種牡馬の重複リクエストを防ぐ。

    Returns:
        {
          'preferred_surface': '芝' or 'ダート' or '',  # 優位性が明確な場合のみセット
          'preferred_distance': '短距離' or '中距離' or '長距離' or '',
        }
    """
    if not ped_id:
        return {}
    if ped_id in _sire_stats_cache:
        return _sire_stats_cache[ped_id]

    try:
        url = f"https://db.netkeiba.com/horse/sire/{ped_id}/"
        soup = _fetch(url)
        stats = _parse_sire_stats(soup)
    except Exception as e:
        logger.warning("種牡馬統計取得失敗 (ped_id=%s): %s", ped_id, e)
        stats = {}

    _sire_stats_cache[ped_id] = stats
    return stats


def _parse_sire_stats(soup: BeautifulSoup) -> dict:
    """
    種牡馬ページから芝/ダート・距離カテゴリ別の勝利数を解析し、
    優位な馬場・距離区分を返す。
    """
    turf_wins = 0
    dirt_wins = 0
    short_wins = 0   # ≤1400m
    middle_wins = 0  # 1500-2000m
    long_wins = 0    # ≥2200m

    # 芝/ダート・距離ラベルのマッピング
    surface_labels = {"芝": "turf", "ダート": "dirt", "ダ": "dirt"}
    distance_labels = {
        "短距離": "short",
        "マイル": "middle",
        "中距離": "middle",
        "中長距離": "long",
        "長距離": "long",
    }

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            wins = _extract_wins_from_cells(cells)
            if wins is None:
                continue

            if label in surface_labels:
                if surface_labels[label] == "turf":
                    turf_wins += wins
                else:
                    dirt_wins += wins

            elif label in distance_labels:
                cat = distance_labels[label]
                if cat == "short":
                    short_wins += wins
                elif cat == "middle":
                    middle_wins += wins
                else:
                    long_wins += wins

    result: dict = {}

    # 芝/ダート優位判定: 60%以上のシェアがある場合のみ断言
    total_surf = turf_wins + dirt_wins
    if total_surf >= 5:
        turf_ratio = turf_wins / total_surf
        if turf_ratio >= 0.60:
            result["preferred_surface"] = "芝"
        elif turf_ratio <= 0.40:
            result["preferred_surface"] = "ダート"

    # 距離優位判定: 最も勝利数が多いカテゴリ
    dist_wins = {"短距離": short_wins, "中距離": middle_wins, "長距離": long_wins}
    total_dist = sum(dist_wins.values())
    if total_dist >= 5:
        best_dist = max(dist_wins, key=lambda k: dist_wins[k])
        result["preferred_distance"] = best_dist

    logger.debug("種牡馬統計解析結果: %s", result)
    return result


def _extract_wins_from_cells(cells) -> int | None:
    """テーブル行のセルから勝利数（整数）を取得する。2〜4列目を探す。"""
    for cell in cells[1:5]:
        text = cell.get_text(strip=True)
        if re.match(r"^\d+$", text):
            return int(text)
    return None


def _find_results_table(soup: BeautifulSoup):
    """過去成績テーブルを返す。"""
    # 1. 既知クラス名
    for cls in ("db_h_race_results", "nk_tb_common", "race_table_01"):
        t = soup.find("table", class_=cls)
        if t:
            return t
    # 2. 「着順」ヘッダーを th または td で含むテーブル
    for t in soup.find_all("table"):
        cells = [c.get_text(strip=True) for c in t.find_all(["th", "td"])[:30]]
        if "着順" in cells:
            return t
    # 3. 着順数値(1〜18)を最も多く含むテーブル（成績表を推定）
    best_t, best_count = None, 2
    for t in soup.find_all("table"):
        count = sum(
            1 for td in t.find_all("td")
            if re.match(r"^(1[0-8]|[1-9])$", td.get_text(strip=True))
        )
        if count > best_count:
            best_count, best_t = count, t
    return best_t


def _extract_grade(td) -> str:
    """
    レース名セル (index 4) からグレードを判定する。
    テキストとCSSクラスの両方を確認する。
    """
    text = td.get_text(strip=True)

    # テキスト内のグレード文字列（"(G1)"、"G1" など）
    for grade, patterns in [
        ("G1", ["G1", "GⅠ", "G１"]),
        ("G2", ["G2", "GⅡ", "G２"]),
        ("G3", ["G3", "GⅢ", "G３"]),
    ]:
        if any(p in text for p in patterns):
            return grade

    # CSSクラスベースの判定（子要素含む）
    for tag in [td] + td.find_all(["span", "a", "img"]):
        cls_str = " ".join(tag.get("class", []))
        alt = tag.get("alt", "")
        for src in (cls_str.lower(), alt.lower()):
            if "g1" in src or "grade1" in src:
                return "G1"
            if "g2" in src or "grade2" in src:
                return "G2"
            if "g3" in src or "grade3" in src:
                return "G3"

    if "重賞" in text:
        return "重賞"
    return ""


def _extract_pace(passage: str) -> str:
    """
    通過順文字列（例: '4-4-4-3'）から4コーナー位置を取り出し脚質を推定する。
    逃:1-2位 / 先:3-5位 / 差:6-9位 / 追:10位以上
    """
    nums = [int(n) for n in re.findall(r"\d+", passage)]
    if not nums:
        return ""
    last = nums[-1]
    if last <= 2:
        return "逃"
    elif last <= 5:
        return "先"
    elif last <= 9:
        return "差"
    else:
        return "追"


def _parse_result_row(tds) -> dict | None:
    """
    成績テーブルの1行から各種情報を解析する。

    netkeibaの成績テーブルカラム順（AJAXレスポンス）:
      0:日付 1:開催 2:天気 3:R 4:レース名 5:映像 6:頭数 7:枠番 8:馬番
      9:オッズ 10:人気 11:着順 12:騎手 13:斤量 14:距離 15:水分量 16:馬場
      17:馬場指数 18:タイム 19:着差 20:タイム指数 21:タイム指数マスター
      22:スタート指数 23:追走指数 24:上がり指数 25:通過 26:ペース 27:上り
      28:馬体重 29:騎乗ペース 30:備考 31:勝ち馬 32:賞金
    """
    result = {
        "date": tds[0].get_text(strip=True),
        "venue": tds[1].get_text(strip=True),
        "finish": 99,
        "grade": "",    # G1 / G2 / G3 / 重賞 / ""
        "surface": "",  # 芝 / ダート
        "distance": 0,  # メートル
        "pace": "",     # 逃 / 先 / 差 / 追
    }

    # グレード (index 4: レース名)
    if len(tds) > 4:
        result["grade"] = _extract_grade(tds[4])

    # 着順 (index 11 が正確だが、9〜12で範囲サーチ)
    for i in range(9, min(13, len(tds))):
        text = tds[i].get_text(strip=True)
        if re.match(r"^\d{1,2}$", text):
            val = int(text)
            if 1 <= val <= 28:
                result["finish"] = val
                break

    # 距離・馬場 (index 14: e.g. "芝1600", "ダ1400", "障2000")
    if len(tds) > 14:
        dist_text = tds[14].get_text(strip=True)
        m = re.match(r"(芝|ダ|障)(\d{3,4})", dist_text)
        if m:
            surface_char = m.group(1)
            result["surface"] = "芝" if surface_char == "芝" else "ダート"
            result["distance"] = int(m.group(2))

    # 脚質 (index 25: 通過順 e.g. "4-4-4-3")
    if len(tds) > 25:
        passage = tds[25].get_text(strip=True)
        result["pace"] = _extract_pace(passage)

    # 馬体重 (index 28: e.g. "480(+4)" or "480")
    if len(tds) > 28:
        wt_text = tds[28].get_text(strip=True)
        m = re.match(r"(\d{3,4})", wt_text)
        if m:
            result["weight"] = int(m.group(1))

    return result
