import json
import os

FILE = "alerts.json"


# ======================
# LOAD ALERTS
# ======================
def load_alerts():
    if not os.path.exists(FILE):
        return []
    with open(FILE, "r") as f:
        return json.load(f)


# ======================
# SAVE ALERTS
# ======================
def save_alerts(alerts):
    with open(FILE, "w") as f:
        json.dump(alerts, f, indent=2)


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
