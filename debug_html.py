#!/usr/bin/env python3
"""
HTMLダンプ診断ツール。
取得したページの構造を確認して scraper.py の修正に役立てる。

使い方:
  python debug_html.py horse 2020103945   # 馬ページ
  python debug_html.py race 202608030411  # 出走表ページ
"""
import sys
from scraper import _fetch


def dump(page_type: str, id_: str) -> None:
    if page_type == "horse":
        url = f"https://db.netkeiba.com/horse/{id_}/"
    elif page_type == "race":
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={id_}"
    else:
        print("page_type は 'horse' か 'race' を指定してください")
        sys.exit(1)

    print(f"取得中: {url}")
    soup = _fetch(url)

    # HTML 保存
    out = f"debug_{page_type}_{id_}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(str(soup))
    print(f"HTML 保存完了: {out}")

    # テーブル一覧
    tables = soup.find_all("table")
    print(f"\n=== テーブル数: {len(tables)} ===")
    for i, t in enumerate(tables):
        rows = t.find_all("tr")
        cls = t.get("class", [])
        # 最初のヘッダーセル
        headers = [c.get_text(strip=True) for c in t.find_all(["th", "td"])[:8]]
        print(f"  [{i}] class={cls} rows={len(rows)} headers={headers}")

    # script タグ内 JSON の有無
    scripts = [s for s in soup.find_all("script") if "race_id" in (s.string or "")]
    if scripts:
        print(f"\n=== race_id を含む script タグ: {len(scripts)}件 ===")
        for s in scripts[:2]:
            print(s.string[:300])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    dump(sys.argv[1], sys.argv[2])
