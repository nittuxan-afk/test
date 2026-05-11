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
    for row in table.find_all("tr"):
        row_classes = " ".join(row.get("class", []))
        if "HorseList" not in row_classes:
            continue
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
    table = soup.find("table", class_="Shutuba_Table")
    if table:
        return table
    # フォールバック: HorseList行を含むtableを探す
    for t in soup.find_all("table"):
        if t.find("tr", class_=re.compile(r"HorseList")):
            return t
    return None


def _parse_entry_row(row) -> dict | None:
    """TR要素から1頭分の情報を解析する。"""
    horse: dict = {}

    for td in row.find_all("td"):
        cls = " ".join(td.get("class", []))

        if "Umaban" in cls and not horse.get("number"):
            horse["number"] = td.get_text(strip=True)

        elif "HorseName" in cls and not horse.get("name"):
            horse["name"] = td.get_text(strip=True)
            a = td.find("a", href=re.compile(r"/horse/"))
            if a:
                m = re.search(r"/horse/(\w+)", a["href"])
                if m:
                    horse["horse_id"] = m.group(1)

        elif re.search(r"Barei|SexAge", cls) and not horse.get("sex_age"):
            horse["sex_age"] = td.get_text(strip=True)

        elif "Jockey" in cls and not horse.get("jockey"):
            a = td.find("a")
            if a:
                horse["jockey"] = a.get_text(strip=True)
                m = re.search(r"/jockey/\w+/(\w+)", a.get("href", ""))
                if m:
                    horse["jockey_id"] = m.group(1)
            else:
                horse["jockey"] = td.get_text(strip=True)

        elif "Trainer" in cls and not horse.get("trainer"):
            a = td.find("a")
            horse["trainer"] = (a or td).get_text(strip=True)

        elif re.search(r"^Weight$", cls) and not horse.get("weight_text"):
            text = td.get_text(strip=True)
            horse["weight_text"] = text
            m = re.match(r"(\d+)\(([+-]?\d+)\)", text)
            if m:
                horse["weight"] = int(m.group(1))
                horse["weight_change"] = int(m.group(2))

        elif re.search(r"Odds|Tansho", cls) and not horse.get("odds"):
            text = td.get_text(strip=True)
            try:
                horse["odds"] = float(text)
            except ValueError:
                pass

    # 斤量は専用クラスがない場合、Jockeyの直前のセルを推定
    if not horse.get("kinryo"):
        _try_extract_kinryo(row, horse)

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


def get_horse_past_results(horse_id: str, limit: int = 5) -> list[dict]:
    """
    db.netkeiba.com から過去成績を取得する。

    Args:
        horse_id: 馬ID (例: '2019105678')
        limit: 取得する最大レース数

    Returns:
        成績リスト。各辞書のキー: date, venue, finish(着順int)
    """
    url = f"https://db.netkeiba.com/horse/{horse_id}/"
    logger.info("過去成績取得: %s", url)

    try:
        soup = _fetch(url)
    except requests.RequestException as e:
        logger.warning("過去成績取得失敗 (horse_id=%s): %s", horse_id, e)
        return []

    table = _find_results_table(soup)
    if table is None:
        logger.warning("成績テーブルが見つかりません (horse_id=%s)", horse_id)
        return []

    results = []
    rows = table.find_all("tr")[1:]  # ヘッダー行をスキップ
    for row in rows[:limit]:
        tds = row.find_all("td")
        if len(tds) < 12:
            continue
        result = _parse_result_row(tds)
        if result:
            results.append(result)

    return results


def _find_results_table(soup: BeautifulSoup):
    """過去成績テーブルを返す。"""
    for cls in ("db_h_race_results nk_tb_common", "db_h_race_results"):
        t = soup.find("table", class_=cls)
        if t:
            return t
    # フォールバック: 着順列を含むテーブルを探す
    for t in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in t.find_all("th")]
        if "着順" in headers:
            return t
    return None


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
