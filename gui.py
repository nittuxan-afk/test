#!/usr/bin/env python3
"""
競馬予想 デスクトップアプリ (CustomTkinter)
使い方: python gui.py
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from main import run

MARKS = ["◎", "○", "▲", "△", "×"]
MARK_COLORS = {
    "◎": "#e74c3c",
    "○": "#4a9edd",
    "▲": "#e67e22",
    "△": "#2ecc71",
    "×": "#95a1ac",
}

_BREAKDOWN_LABELS = [
    ("過去成績",   "past_results"),
    ("馬体重変化", "weight_change"),
    ("コース適性", "course_fit"),
    ("血統適性",   "pedigree"),
    ("枠番適性",   "post_position"),
    ("馬場状態",   "track_condition"),
    ("脚質適性",   "pace_match"),
    ("騎手×会場", "jockey_venue"),
    ("調教評価",   "training"),
]

_TREE_COLS = (
    "印", "順", "馬番", "馬名", "騎手", "オッズ", "合計", "評価",
    "過去", "体重", "コース", "血統", "枠番", "馬場", "脚質", "騎手統計", "調教",
)
_TREE_WIDTHS = (
    35, 35, 45, 160, 100, 75, 65, 45,
    45, 45, 55, 45, 45, 45, 45, 70, 45,
)


class _QueueWriter:
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, text: str) -> None:
        if text:
            self._q.put(("log", text))

    def flush(self) -> None:
        pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("競馬予想プログラム")
        self.geometry("1100x820")
        self.minsize(900, 650)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._ui_font = ctk.CTkFont(family="Yu Gothic UI", size=13)
        self._ui_font_bold = ctk.CTkFont(family="Yu Gothic UI", size=13, weight="bold")
        self._title_font = ctk.CTkFont(family="Yu Gothic UI", size=22, weight="bold")
        self._hint_font = ctk.CTkFont(family="Yu Gothic UI", size=11)

        self._q: queue.Queue = queue.Queue()
        self._running = False

        self._style_treeview()
        self._build_ui()

    def _style_treeview(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Results.Treeview",
            background="#2b2b2b",
            foreground="#dcddde",
            rowheight=30,
            fieldbackground="#2b2b2b",
            font=("Yu Gothic UI", 13),
            borderwidth=0,
        )
        style.configure(
            "Results.Treeview.Heading",
            background="#1a1a2e",
            foreground="#a0b4c8",
            font=("Yu Gothic UI", 12, "bold"),
            relief="flat",
        )
        style.map(
            "Results.Treeview",
            background=[("selected", "#1f6aa5")],
            foreground=[("selected", "white")],
        )
        style.configure(
            "TScrollbar",
            background="#3a3a3a",
            troughcolor="#2b2b2b",
            borderwidth=0,
        )

    def _build_ui(self):
        # ── ヘッダー ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(header, text="🏇  競馬予想プログラム", font=self._title_font).pack(side="left")

        # ── 入力エリア ──
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(fill="x", padx=16, pady=(4, 6))

        ctk.CTkLabel(input_frame, text="レースID:", font=self._ui_font).pack(
            side="left", padx=(12, 4), pady=12
        )
        self.race_id_var = ctk.StringVar()
        entry = ctk.CTkEntry(
            input_frame, textvariable=self.race_id_var,
            placeholder_text="202606030811", width=210, font=self._ui_font,
        )
        entry.pack(side="left", padx=4, pady=12)
        entry.bind("<Return>", lambda _: self._start())

        self.use_history_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            input_frame, text="過去成績・調教を取得",
            variable=self.use_history_var, font=self._ui_font,
        ).pack(side="left", padx=16)

        self.run_btn = ctk.CTkButton(
            input_frame, text="予想を実行", width=120,
            command=self._start, font=self._ui_font_bold,
        )
        self.run_btn.pack(side="left", padx=8, pady=12)

        self.clear_btn = ctk.CTkButton(
            input_frame, text="クリア", width=80,
            fg_color="gray40", hover_color="gray30",
            command=self._clear, font=self._ui_font,
        )
        self.clear_btn.pack(side="left", padx=4)

        self.status_label = ctk.CTkLabel(
            input_frame, text="", text_color="gray60", font=self._ui_font
        )
        self.status_label.pack(side="left", padx=12)

        # ── 競馬場コード説明 ──
        ctk.CTkLabel(
            self,
            text=(
                "競馬場コード: 01=札幌 02=函館 03=福島 04=新潟 05=東京 "
                "06=中山 07=中京 08=京都 09=阪神 10=小倉    "
                "形式: YYYY + 競馬場(2桁) + 開催回(2桁) + 日数(2桁) + R番号(2桁)"
            ),
            font=self._hint_font, text_color="gray60",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        # ── 取得ログエリア (小) ──
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=20, pady=(2, 0))
        ctk.CTkLabel(log_header, text="取得ログ", font=self._hint_font, text_color="gray55").pack(side="left")

        self.log_box = ctk.CTkTextbox(
            self, height=80,
            font=ctk.CTkFont(family="Yu Gothic UI", size=11),
            text_color="gray65", wrap="word",
        )
        self.log_box.pack(fill="x", padx=16, pady=(2, 8))

        # ── タブビュー ──
        self.tabs = ctk.CTkTabview(self, anchor="nw")
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.tabs.add("📊 予想結果")
        self.tabs.add("🔍 詳細 (上位5頭)")

        self._build_result_tab()
        self._build_detail_tab()

    def _build_result_tab(self):
        tab = self.tabs.tab("📊 予想結果")
        frame = tk.Frame(tab, bg="#2b2b2b")
        frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            frame, columns=_TREE_COLS, show="headings",
            style="Results.Treeview", selectmode="browse",
        )
        for col, w in zip(_TREE_COLS, _TREE_WIDTHS):
            self.tree.heading(col, text=col)
            anchor = "w" if col == "馬名" else "center"
            self.tree.column(col, width=w, anchor=anchor, stretch=False)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        for mark, color in MARK_COLORS.items():
            self.tree.tag_configure(mark, foreground=color)
        self.tree.tag_configure("stripe", background="#333333")

    def _build_detail_tab(self):
        tab = self.tabs.tab("🔍 詳細 (上位5頭)")
        self.detail_box = ctk.CTkTextbox(
            tab, font=ctk.CTkFont(family="Yu Gothic UI", size=13), wrap="word",
        )
        self.detail_box.pack(fill="both", expand=True)

    # ── イベントハンドラ ──

    def _start(self):
        race_id = self.race_id_var.get().strip()
        if not race_id:
            self._set_status("レースIDを入力してください", error=True)
            return
        if self._running:
            return

        self._running = True
        self.run_btn.configure(state="disabled", text="実行中...")
        self.log_box.delete("1.0", "end")
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.detail_box.delete("1.0", "end")
        self._set_status("データ取得中...")

        use_history = self.use_history_var.get()
        threading.Thread(
            target=self._worker, args=(race_id, use_history), daemon=True
        ).start()
        self.after(80, self._poll)

    def _clear(self):
        if self._running:
            return
        self.log_box.delete("1.0", "end")
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.detail_box.delete("1.0", "end")
        self.race_id_var.set("")
        self._set_status("")

    def _worker(self, race_id: str, use_history: bool):
        old_out, old_err = sys.stdout, sys.stderr
        writer = _QueueWriter(self._q)
        sys.stdout = writer
        sys.stderr = writer
        try:
            results = run(race_id, use_history=use_history)
            self._q.put(("results", results))
        except SystemExit:
            pass
        except Exception as e:
            self._q.put(("log", f"\nエラー: {e}\n"))
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
            self._q.put(("done", None))

    def _poll(self):
        try:
            while True:
                kind, data = self._q.get_nowait()
                if kind == "done":
                    self._running = False
                    self.run_btn.configure(state="normal", text="予想を実行")
                    self._set_status("完了")
                    return
                elif kind == "log":
                    self.log_box.insert("end", data)
                    self.log_box.see("end")
                elif kind == "results":
                    self._show_results(data)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    _MAX_RAW_SCORE = 97

    def _scaled_score(self, raw: int) -> int:
        return round(raw * 100 / self._MAX_RAW_SCORE)

    def _safe_grade(self, r: dict, key: str) -> str:
        """ブレークダウンが'データなし'の場合はグレードの代わりに'-'を返す"""
        bd = r.get("breakdown", {})
        val = bd.get(key)
        if val and "データなし" in str(val[1]):
            return "-"
        return r.get("grades", {}).get(key, "-")

    def _show_results(self, results: list[dict]):
        for i, r in enumerate(results):
            mark = MARKS[r["rank"] - 1] if r["rank"] <= 5 else ""
            g = r.get("grades", {})
            odds_str = f"{r['odds']:.1f}倍" if r.get("odds") else "-"
            tag = mark if mark else ("stripe" if i % 2 == 0 else "")
            self.tree.insert(
                "", "end", tags=(tag,),
                values=(
                    mark,
                    r["rank"],
                    r["horse_number"],
                    r["horse_name"],
                    r["jockey"],
                    odds_str,
                    f"{self._scaled_score(r['total_score'])}点",
                    g.get("total", "-"),
                    self._safe_grade(r, "past_results"),
                    self._safe_grade(r, "weight_change"),
                    self._safe_grade(r, "course_fit"),
                    self._safe_grade(r, "pedigree"),
                    self._safe_grade(r, "post_position"),
                    self._safe_grade(r, "track_condition"),
                    self._safe_grade(r, "pace_match"),
                    self._safe_grade(r, "jockey_venue"),
                    self._safe_grade(r, "training"),
                ),
            )

        self._show_details(results[:5])
        self.tabs.set("📊 予想結果")

    def _show_details(self, top5: list[dict]):
        self.detail_box.delete("1.0", "end")
        for r in top5:
            mark = MARKS[r["rank"] - 1]
            kinryo = f'{r["kinryo"]}kg' if r.get("kinryo") else "不明"
            weight = r.get("weight_text") or "不明"
            odds_str = f"{r['odds']:.1f}倍" if r.get("odds") else "データなし"
            self.detail_box.insert(
                "end",
                f"{mark}  {r['horse_number']}番  {r['horse_name']}  "
                f"({r.get('sex_age', '')})  斤量:{kinryo}  馬体重:{weight}  単勝:{odds_str}\n"
            )
            bd = r.get("breakdown", {})
            for label, key in _BREAKDOWN_LABELS:
                val = bd.get(key)
                if val:
                    pts, desc = val
                    self.detail_box.insert("end", f"    {label}    {pts:2d}点  {desc}\n")
            self.detail_box.insert("end", f"    {'─' * 40}\n")
            self.detail_box.insert("end", f"    合計    {self._scaled_score(r['total_score'])}点 / 100点\n\n")

    def _set_status(self, msg: str, *, error: bool = False):
        color = "#ff6666" if error else "gray60"
        self.status_label.configure(text=msg, text_color=color)


if __name__ == "__main__":
    App().mainloop()
