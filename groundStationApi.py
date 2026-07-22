from flask import Flask, request, jsonify
import logging
import pandas as pd
import io
from typing import Any, Dict

# need this so the timestamp doesn't look weird
EXCEL_EPOCH = pd.Timestamp("1899-12-30")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("groundStationApi.app")

app = Flask(__name__)

# @app.route("/")
# def hello_world():
#     return "hello!!"

# helper functions for analyzing the incoming metrics
def parse_csv(file_bytes: bytes) -> pd.DataFrame:

    data = pd.read_csv(io.BytesIO(file_bytes))

    numeric_cols = ["date", "hour", "num_contacts", "total_bytes_sent", "total_bytes_received"]
    for col in numeric_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data["timestamp"] = EXCEL_EPOCH + pd.to_timedelta(data["date"], unit="D") + pd.to_timedelta(data["hour"], unit="h")

    # would like to do some error checking of the file + it's contents, but leaving for now :/

    return data

def compute_metrics(data: pd.DataFrame) -> Dict[str, Any]:
    # get metrics accross the entire time window, per station

    overall = {
        "time_window_start": data["timestamp"].min().isoformat(),
                "time_window_end": data["timestamp"].max().isoformat(),
                "total_bytes_sent": int(data["total_bytes_sent"].sum()),
                "total_bytes_received": int(data["total_bytes_received"].sum()),
                "total_bytes_transferred": int(data["total_bytes_sent"].sum() + data["total_bytes_received"].sum()),
                "total_contacts": int(data["num_contacts"].sum()),
                "station_count": data["station_id"].nunique(),
                "row_count": len(data),
    }

    per_station = []
    for station_id, group in data.groupby("station_id"):
        per_station.append({
            "station_id": station_id,
            "total_bytes_sent": int(group["total_bytes_sent"].sum()),
            "total_bytes_received": int(group["total_bytes_received"].sum()),
            "total_bytes_transferred": int(group["total_bytes_sent"].sum() + group["total_bytes_received"].sum()),
            "total_contacts": int(group["num_contacts"].sum()),
        })

    overall["per_station"] = sorted(per_station, key=lambda s: s["station_id"])
    return overall

# analyze the incoming csv
def analyze_input(file_bytes: bytes):

    data = parse_csv(file_bytes)
    metrics = compute_metrics(data)

    # would analyze the anomalies here too, something a little more in depth than compute_metrics

    summary = {
        "status": "ok",
        "metrics": metrics
    }

    return summary

@app.route("/", methods=["POST"])
def publish_metrics():
    # takes a csv and publishes an analysis of the metrics

    if "file" in request.files:
        upload = request.files["file"]
        if upload.filename == "":
            return jsonify({"status": "error", "message": "no file selected"}), 400

        file_bytes = upload.read()
    elif request.data:
        file_bytes = request.data
    else:
        return jsonify({
                    "status": "error",
                    "message": "no csv provided",
                }), 400

    # check if the csv is empty
    if not file_bytes:
        return jsonify({"status": "error", "message": "Uploaded file is empty."}), 400

    try:
        # try to analyze the input
        summary = analyze_input(file_bytes)
    except ValueError as e:
            logger.warning("rejected telemetry upload: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 400
    except Exception:
        logger.exception("unexpected error")
        return jsonify({"status": "error", "message": "unexpeted error"}), 500
    return jsonify(summary), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)