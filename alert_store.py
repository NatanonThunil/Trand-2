import json
import os

# ✅ ต้องมี /tmp/data/ นำหน้า
FILE = "/tmp/data/alerts.json"

# --- เพิ่มบรรทัดนี้ ---
print(f"🟢 ALERT STORE LOADED: Using file path -> {FILE}")

def load_alerts():
    if not os.path.exists(FILE): return []
    try:
        with open(FILE, "r") as f: return json.load(f)
    except: return []

def save_alerts(alerts):
    # ✅ ต้องมีบรรทัดนี้: สร้างโฟลเดอร์ก่อนเขียน
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w") as f: json.dump(alerts, f, indent=2)

def remove_alert(alerts, item):
    return [a for a in alerts if a != item]

def format_alert_message(alert, current_price):
    icon = "⬆️" if alert["direction"] == "above" else "⬇️"
    return f"🔔 *ALERT HIT*\n{alert['symbol']} : {current_price:,.2f} {icon}"