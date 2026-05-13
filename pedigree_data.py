"""
血統適性スコア計算モジュール。
「ちょっちゅ使える血統辞典2026【中央競馬版】」をもとに作成。

評価レーティング:
  SUPER_BUY  (+12): 超絶買い / 超爆買い
  STRONG_BUY  (+8): 激買い
  BUY         (+4): 買い
  NEUTRAL      (0): 普通 / データなし
  CAUTION     (-3): 注意
  AVOID       (-6): 消し

sex_cond (性別条件):
  None: 性別問わず
  '牡' : 牡馬・騸馬のみ
  '牝' : 牝馬のみ
"""

# ─── 評価定数 ─────────────────────────────────────
SUPER_BUY  = 12
STRONG_BUY = 8
BUY        = 4
NEUTRAL    = 0
CAUTION    = -3
AVOID      = -6

# ─── コース別 血統評価テーブル ────────────────────
# Key  : (venue_code, surface_code, distance)
#          surface_code: 'T'=芝, 'D'=ダート
#          distance    : メートル (int)
# Value: list of (種牡馬名, rating, sex_cond)
PEDIGREE_RATINGS: dict[tuple[str, str, int], list[tuple[str, int, str | None]]] = {

    # ══════════════ 東京 (05) ══════════════
    ("05", "T", 1400): [
        ("イスラボニータ",    SUPER_BUY,  None),
        ("ロードカナロア",    STRONG_BUY, None),
        ("ダイワメジャー",    AVOID,      None),
    ],
    ("05", "T", 1600): [
        ("リアルスティール",  STRONG_BUY, "牝"),
        ("ジャスタウェイ",    STRONG_BUY, None),
        ("エピファネイア",    BUY,        None),
    ],
    ("05", "T", 1800): [
        ("キズナ",           STRONG_BUY, None),
        ("Frankel",          STRONG_BUY, None),
        ("フランケル",        STRONG_BUY, None),
        ("ルーラーシップ",    BUY,        None),
    ],
    ("05", "T", 2000): [
        ("キズナ",           STRONG_BUY, "牡"),
        ("スワーヴリチャード", STRONG_BUY, None),
        ("ルーラーシップ",    STRONG_BUY, None),
        ("エピファネイア",    BUY,        None),
    ],
    ("05", "T", 2400): [
        ("キズナ",           STRONG_BUY, None),
        ("ドゥラメンテ",      STRONG_BUY, None),
        ("ルーラーシップ",    BUY,        None),
    ],
    ("05", "D", 1400): [
        ("ロードカナロア",    STRONG_BUY, None),
        ("ゴールドアリュール", STRONG_BUY, None),
        ("クロフネ",          AVOID,      None),
    ],
    ("05", "D", 1600): [
        ("ヘニーヒューズ",    STRONG_BUY, None),
        ("アモーゲ",          STRONG_BUY, "牡"),
        ("クロフネ",          AVOID,      None),
    ],
    ("05", "D", 2100): [
        ("キングカメハメハ",   SUPER_BUY,  None),
        ("リアルスティール",  STRONG_BUY, None),
        ("マンハッタンカフェ", STRONG_BUY, None),
        ("Empire Maker",      BUY,        None),
        ("エンパイアメーカー", BUY,        None),
    ],

    # ══════════════ 中山 (06) ══════════════
    ("06", "T", 1200): [
        ("ロードカナロア",    STRONG_BUY, None),
        ("ダンシングレジェンド", STRONG_BUY, None),
    ],
    ("06", "T", 1600): [
        ("シルバーステート",  SUPER_BUY,  None),
        ("ディーマジェスティ", STRONG_BUY, "牡"),
        ("キズナ",           STRONG_BUY, None),
        ("レイデオロ",        STRONG_BUY, None),
    ],
    ("06", "T", 1800): [
        ("キズナ",           STRONG_BUY, "牡"),
        ("ドラメンテ",        STRONG_BUY, None),
        ("エピファネイア",    BUY,        None),
    ],
    ("06", "T", 2000): [
        ("ドラメンテ",        STRONG_BUY, None),
        ("キタサンブラック",  STRONG_BUY, None),
    ],
    ("06", "D", 1200): [
        ("ヘニーヒューズ",    STRONG_BUY, None),
        ("ミッキーアイル",    STRONG_BUY, None),
        ("ダンシングレジェンド", STRONG_BUY, None),
        ("ロードカナロア",    STRONG_BUY, None),
        ("キングカメハメハ",  CAUTION,    None),
    ],
    ("06", "D", 1800): [
        ("キングカメハメハ",  STRONG_BUY, None),
        ("サンダースノー",    STRONG_BUY, None),
        ("ヘニーヒューズ",    BUY,        None),
    ],

    # ══════════════ 阪神 (09) ══════════════
    ("09", "T", 2000): [
        ("キズナ",           SUPER_BUY,  None),
        ("ルーラーシップ",    SUPER_BUY,  None),
        ("キングカメハメハ",  STRONG_BUY, None),
    ],
    ("09", "D", 1400): [
        ("ドレフォン",        STRONG_BUY, None),
        ("ダンシングレジェンド", STRONG_BUY, None),
        ("ヘニーヒューズ",    BUY,        None),
    ],
    ("09", "D", 1800): [
        ("シニスターミニスター", STRONG_BUY, "牝"),
        ("ネオユニヴァース",  BUY,        None),
    ],

    # ══════════════ 京都 (08) ══════════════
    ("08", "T", 1600): [
        ("イスラボニータ",    STRONG_BUY, None),
    ],
    ("08", "T", 2000): [
        ("キタサンブラック",  STRONG_BUY, None),
        ("レイデオロ",        STRONG_BUY, None),
        ("キズナ",           BUY,        None),
    ],
    ("08", "T", 2200): [
        ("キズナ",           SUPER_BUY,  None),
        ("ルーラーシップ",    BUY,        None),
    ],
    ("08", "T", 2400): [
        ("キズナ",           SUPER_BUY,  None),
        ("ドゥラメンテ",      STRONG_BUY, None),
    ],
    ("08", "D", 1200): [
        ("ドレフォン",        STRONG_BUY, None),
        ("ダノンレジェンド",  STRONG_BUY, None),
    ],
    ("08", "D", 1400): [
        ("ヘニーヒューズ",    SUPER_BUY,  None),
        ("キタサンブラック",  SUPER_BUY,  None),
        ("シニスターミニスター", STRONG_BUY, None),
        ("モーニング",        BUY,        None),
    ],
    ("08", "D", 1800): [
        ("シニスターミニスター", STRONG_BUY, None),
        ("キズナ",           STRONG_BUY, "牡"),
        ("キングカメハメハ",  STRONG_BUY, "牡"),
        ("ゴールドアリュール", AVOID,      None),
    ],
    ("08", "D", 1900): [
        ("シニスターミニスター", STRONG_BUY, None),
        ("キングカメハメハ",  STRONG_BUY, None),
        ("サンダースノー",    STRONG_BUY, None),
    ],

    # ══════════════ 中京 (07) ══════════════
    ("07", "T", 1200): [
        ("ロードカナロア",    SUPER_BUY,  None),
        ("ファインニードル",  AVOID,      None),
    ],
    ("07", "T", 2000): [
        ("シルバーステート",  BUY,        None),
        ("クロフネ",          CAUTION,    "牡"),
    ],
    ("07", "D", 1400): [
        ("ロードカナロア",    STRONG_BUY, None),
        ("ゴールドアリュール", STRONG_BUY, None),
    ],
    ("07", "D", 1800): [
        ("キズナ",           SUPER_BUY,  None),
        ("ドシプリン",        STRONG_BUY, None),
    ],

    # ══════════════ 新潟 (04) ══════════════
    ("04", "T", 1000): [
        ("マクフィ",          STRONG_BUY, None),
        ("ロードカナロア",    BUY,        None),
        ("ダイワメジャー",    AVOID,      None),
    ],
    ("04", "T", 1600): [
        ("ダノンバラード",    STRONG_BUY, "牝"),
        ("スタウィゴールド",  BUY,        None),
    ],
    ("04", "D", 1200): [
        ("ロードカナロア",    SUPER_BUY,  None),
        ("マジェスティックウォリアー", STRONG_BUY, None),
        ("Into Mischief",     STRONG_BUY, None),
    ],
    ("04", "D", 1800): [
        ("キタサンブラック",  SUPER_BUY,  None),
        ("ヘニーヒューズ",    STRONG_BUY, None),
    ],

    # ══════════════ 函館 (02) ══════════════
    ("02", "T", 1200): [
        ("ビッグアーサー",    STRONG_BUY, None),
        ("ダイワメジャー",    BUY,        None),
    ],
    ("02", "D", 1700): [
        ("ヘニーヒューズ",    STRONG_BUY, None),
        ("ドレフォン",        BUY,        None),
    ],

    # ══════════════ 札幌 (01) ══════════════
    ("01", "T", 1200): [
        ("ロードカナロア",    STRONG_BUY, None),
        ("ドレフォン",        BUY,        None),
    ],
    ("01", "T", 1800): [
        ("キズナ",           STRONG_BUY, None),
        ("エピファネイア",    STRONG_BUY, None),
    ],
    ("01", "D", 1700): [
        ("シニスターミニスター", STRONG_BUY, None),
        ("ヘニーヒューズ",    BUY,        None),
    ],

    # ══════════════ 福島 (03) ══════════════
    ("03", "T", 1200): [
        ("ビッグアーサー",    STRONG_BUY, None),
        ("ミッキーアイル",    STRONG_BUY, None),
        ("ダイワメジャー",    STRONG_BUY, "牡"),
    ],
    ("03", "T", 1800): [
        ("キズナ",           STRONG_BUY, "牡"),
        ("レイデオロ",        STRONG_BUY, None),
    ],
    ("03", "T", 2000): [
        ("スクリーンヒーロー", SUPER_BUY,  "牡"),
        ("キズナ",           BUY,        None),
        ("コールドストーン",  STRONG_BUY, None),
    ],
    ("03", "D", 1150): [
        ("ザファクター",      SUPER_BUY,  None),
        ("ヘニーヒューズ",    STRONG_BUY, None),
    ],
    ("03", "D", 1700): [
        ("シニスターミニスター", STRONG_BUY, None),
        ("ドレフォン",        STRONG_BUY, None),
        ("マジェスティックウォリアー", BUY, None),
    ],

    # ══════════════ 小倉 (10) ══════════════
    ("10", "T", 1200): [
        ("ダイワメジャー",    STRONG_BUY, None),
        ("ビッグアーサー",    STRONG_BUY, None),
        ("ファインニードル",  NEUTRAL,    None),
    ],
    ("10", "T", 2000): [
        ("モーリス",          SUPER_BUY,  None),
        ("シルバーステート",  SUPER_BUY,  None),
        ("スクリーンヒーロー", SUPER_BUY,  None),
    ],
    ("10", "D", 1700): [
        ("パイロ",            SUPER_BUY,  None),
        ("ドレフォン",        STRONG_BUY, None),
        ("シンボリクリスエス", BUY,        None),  # 母父として
    ],
}


def _get_sex(sex_age: str) -> str:
    """sex_age 文字列 ('牡4' 等) から性別文字を返す。"""
    if sex_age:
        c = sex_age[0]
        if c in ("牡", "牝", "騸", "セ"):
            return "牡" if c in ("騸", "セ") else c
    return ""


def score_pedigree(
    venue_code: str,
    surface: str,
    distance: int,
    sire: str,
    dam_sire: str,
    sex_age: str,
) -> tuple[int, str]:
    """
    血統適性スコアを計算する。最大12点 (最小-6点)。

    父馬: 完全一致でレーティングを取得
    母父: 同テーブルで一致した場合は 60% のポイントを付与

    Returns:
        (score, description)
    """
    if not venue_code or not surface or not distance:
        return 0, "コース情報なし"

    s = "T" if surface == "芝" else "D"
    key = (venue_code, s, distance)

    # 最近傍距離で補完
    entries = PEDIGREE_RATINGS.get(key)
    if entries is None:
        candidates = [
            (abs(d - distance), d)
            for (v, sc, d) in PEDIGREE_RATINGS
            if v == venue_code and sc == s
        ]
        if candidates:
            _, nearest = min(candidates)
            entries = PEDIGREE_RATINGS.get((venue_code, s, nearest), [])
            approx = True
        else:
            return 0, "血統データなし"
    else:
        approx = False

    sex = _get_sex(sex_age)
    best_sire_score = 0
    best_sire_name = ""
    best_dam_score = 0
    best_dam_name = ""

    for sire_name, rating, sex_cond in entries:
        # 性別条件チェック
        if sex_cond is not None and sex and sex != sex_cond:
            continue

        # 父馬マッチ
        if sire and sire_name == sire:
            if abs(rating) > abs(best_sire_score):
                best_sire_score = rating
                best_sire_name = sire_name

        # 母父マッチ (ポイント60%に減衰)
        if dam_sire and sire_name == dam_sire:
            reduced = round(rating * 0.6)
            if abs(reduced) > abs(best_dam_score):
                best_dam_score = reduced
                best_dam_name = dam_sire

    # スコア確定: 父・母父の合算(ただし上限・下限クリップ)
    total = best_sire_score + best_dam_score
    total = max(-6, min(12, total))

    # 説明文
    parts = []
    if best_sire_name:
        tag = _rating_label(best_sire_score)
        parts.append(f"父{best_sire_name}({tag})")
    if best_dam_name:
        tag = _rating_label(best_dam_score)
        parts.append(f"母父{best_dam_name}({tag})")
    if not parts:
        name_parts = []
        if sire:
            name_parts.append(f"父{sire}")
        if dam_sire:
            name_parts.append(f"母父{dam_sire}")
        label = f"辞典なし ({' / '.join(name_parts)})" if name_parts else "血統データなし"
        return 0, label

    approx_str = "(近似)" if approx else ""
    desc = " / ".join(parts) + approx_str
    return total, desc


def _rating_label(score: int) -> str:
    if score >= SUPER_BUY:
        return "超絶買い"
    elif score >= STRONG_BUY:
        return "激買い"
    elif score >= BUY:
        return "買い"
    elif score <= AVOID:
        return "消し"
    elif score <= CAUTION:
        return "注意"
    else:
        return "普通"
