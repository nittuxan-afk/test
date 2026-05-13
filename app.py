"""Flask Webアプリ - 競馬予想"""
import logging

from flask import Flask, render_template, request

from scraper import get_horse_past_results, get_race_entries
from scorer import calculate_score, rank

app = Flask(__name__)
logging.basicConfig(level=logging.WARNING)

MARKS = ["◎", "○", "▲", "△", "×"]
MARK_COLORS = ["#e74c3c", "#2980b9", "#e67e22", "#27ae60", "#7f8c8d"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/predict", methods=["POST"])
def predict():
    race_id = request.form.get("race_id", "").strip()
    use_history = request.form.get("no_history") != "1"

    if not race_id:
        return render_template("index.html", error="レースIDを入力してください")

    try:
        horses = get_race_entries(race_id)
    except Exception as e:
        return render_template("index.html", error=str(e), prev_race_id=race_id)

    scored = []
    for horse in horses:
        past = []
        if use_history and horse.get("horse_id"):
            try:
                data = get_horse_past_results(horse["horse_id"])
                past = data["results"]
                horse["sire"] = data.get("sire", "")
                horse["dam_sire"] = data.get("dam_sire", "")
                horse["sire_stats"] = data.get("sire_stats", {})
                horse["dam_sire_stats"] = data.get("dam_sire_stats", {})
            except Exception:
                pass
        scored.append(calculate_score(horse, past))

    results = rank(scored)
    max_score = max(r["total_score"] for r in results) or 1

    return render_template(
        "result.html",
        results=results,
        race_id=race_id,
        marks=MARKS,
        mark_colors=MARK_COLORS,
        max_score=max_score,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
