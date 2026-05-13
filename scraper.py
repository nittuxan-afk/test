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

    return horses


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


def get_horse_past_results(horse_id: str, limit: int = 5) -> dict:
    """
    db.netkeiba.com から過去成績と血統情報を取得する。

    Args:
        horse_id: 馬ID (例: '2019105678')
        limit: 取得する最大レース数

    Returns:
        {'results': list[dict], 'sire': str, 'dam_sire': str}
        results の各辞書のキー: date, venue, finish(着順int)
    """
    url = f"https://db.netkeiba.com/horse/{horse_id}/"
    logger.info("過去成績取得: %s", url)

    try:
        soup = _fetch(url)
    except requests.RequestException as e:
        logger.warning("過去成績取得失敗 (horse_id=%s): %s", horse_id, e)
        return {"results": [], "sire": "", "dam_sire": ""}

    sire, dam_sire = _parse_pedigree(soup)

    table = _find_results_table(soup)
    if table is None:
        logger.warning("成績テーブルが見つかりません (horse_id=%s)", horse_id)
        return {"results": [], "sire": sire, "dam_sire": dam_sire}

    results = []
    rows = table.find_all("tr")[1:]  # ヘッダー行をスキップ
    for row in rows[:limit]:
        tds = row.find_all("td")
        if len(tds) < 12:
            continue
        result = _parse_result_row(tds)
        if result:
            results.append(result)

    return {"results": results, "sire": sire, "dam_sire": dam_sire}


def _parse_pedigree(soup: BeautifulSoup) -> tuple[str, str]:
    """
    血統テーブルから父(sire)・母父(dam_sire)を取得する。
    Returns: (sire, dam_sire) -- 見つからない場合は空文字
    """
    sire = ""
    dam_sire = ""

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
            elif cls_set & {"b_04", "b_05", "b_06"} and not dam_sire:
                dam_sire = text

        # 位置ベースフォールバック: 有効セルの1番目=父, 4〜5番目=母父
        if not sire or not dam_sire:
            valid = [td for td in tds
                     if td.get_text(strip=True) not in ("", "－", "-")]
            if not sire and valid:
                a = valid[0].find("a")
                sire = (a.get_text(strip=True) if a else valid[0].get_text(strip=True))
            if not dam_sire:
                for td in valid[3:6]:
                    a = td.find("a")
                    candidate = (a.get_text(strip=True) if a else td.get_text(strip=True))
                    if candidate and candidate != sire:
                        dam_sire = candidate
                        break

    # Strategy 2: 「父」「母父」ラベルの隣セルを探す (th または td)
    if not sire or not dam_sire:
        for cell in soup.find_all(["th", "td"]):
            label = cell.get_text(strip=True)
            if label not in ("父", "母父"):
                continue
            # 同じ行 (tr) の次の td を取得
            parent_tr = cell.find_parent("tr")
            if not parent_tr:
                continue
            cells_in_row = parent_tr.find_all(["th", "td"])
            for i, c in enumerate(cells_in_row):
                if c == cell and i + 1 < len(cells_in_row):
                    a = cells_in_row[i + 1].find("a")
                    val = (a.get_text(strip=True) if a
                           else cells_in_row[i + 1].get_text(strip=True))
                    if label == "父" and not sire:
                        sire = val
                    elif label == "母父" and not dam_sire:
                        dam_sire = val
                    break

    # Strategy 3: /horse/ リンクを4件以上含むテーブルから位置で推定
    if not sire:
        for t in soup.find_all("table"):
            links = [a for a in t.find_all("a", href=re.compile(r"/horse/"))]
            if len(links) >= 4:
                sire = links[0].get_text(strip=True)
                if len(links) > 3:
                    dam_sire = links[3].get_text(strip=True)
                break

    logger.debug("血統取得結果: 父=%s 母父=%s", sire, dam_sire)
    return sire, dam_sire


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


def _parse_result_row(tds) -> dict | None:
    """成績テーブルの1行から着順などを解析する。"""
    result = {
        "date": tds[0].get_text(strip=True),
        "venue": tds[1].get_text(strip=True),
        "finish": 99,
    }
    # 着順は通常9-11番目のセルにある (ページにより異なる)
    for i in range(9, min(13, len(tds))):
        text = tds[i].get_text(strip=True)
        if re.match(r"^\d{1,2}$", text):
            val = int(text)
            if 1 <= val <= 28:
                result["finish"] = val
                break
    return result
