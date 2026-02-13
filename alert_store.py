import json
import os

FILE = "/tmp/data/alerts.json"

def load_alerts():
    if not os.path.exists(FILE): return []
    try:
        with open(FILE, "r") as f: return json.load(f)
    except: return []

def save_alerts(alerts):
    # ✅ เพิ่มบรรทัดนี้: สร้างโฟลเดอร์ก่อนเสมอ
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w") as f: json.dump(alerts, f, indent=2)

def remove_alert(alerts, item):
    return [a for a in alerts if a != item]

# ======================
# FORMAT ALERT MESSAGE
# ======================
def format_alert_message(alert, current_price):
    direction_icon = "⬆️" if alert["direction"] == "above" else "⬇️"

    return f"""
🔔 *PRICE ALERT HIT!*
📌 Symbol : {alert["symbol"]}
🏦 Exchange : {alert["exchange"]}

🎯 Target : {alert["direction"].upper()} {alert["price"]:,.2f}
💰 Price  : {current_price:,.2f} {direction_icon}

⏰ Alert triggered successfully
"""


# ======================
# REMOVE ALERT (AFTER HIT)
# ======================
def remove_alert(alerts, alert_to_remove):
    return [a for a in alerts if a != alert_to_remove]
