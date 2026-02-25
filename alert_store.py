import json
import os


MONGO_URI = os.getenv("MONGO_URI")
FILE = "/tmp/data/alerts.json"
db_collection = None

if MONGO_URI:
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI)
        db = client["TradingBotDB"]
        db_collection = db["alerts"]
    except Exception as e:
        print(f"⚠️ MongoDB Connection Error in Alerts: {e}")

def load_alerts():
    if db_collection is not None:
        doc = db_collection.find_one({"_id": "active_alerts"})
        return doc.get("alerts_list", []) if doc else []
    else:
        if not os.path.exists(FILE): return []
        try:
            with open(FILE, "r") as f: return json.load(f)
        except: return []

def save_alerts(alerts):
    if db_collection is not None:
        db_collection.update_one(
            {"_id": "active_alerts"},
            {"$set": {"alerts_list": alerts}},
            upsert=True
        )
    else:
        os.makedirs(os.path.dirname(FILE), exist_ok=True)
        with open(FILE, "w") as f: json.dump(alerts, f)

def remove_alert(alert):
    alerts = load_alerts()
    if alert in alerts:
        alerts.remove(alert)
        save_alerts(alerts)

def format_alert_message(alert, current_price):
    symbol = alert.get('symbol', 'UNKNOWN')
    exchange = alert.get('exchange', 'UNKNOWN')
    direction = alert.get('direction', 'above')
    target_price = alert.get('price', 0)

    # คำนวณส่วนต่างเป็น % (Optional: เพื่อความเท่)
    diff = 0
    if target_price > 0:
        diff = ((current_price - target_price) / target_price) * 100

    # เลือก Icon และข้อความตามทิศทาง
    if direction == "above":
        icon = "🚀 🟢"
        action_text = "BREAKOUT (พุ่งทะลุแนวต้าน)"
        diff_text = f"+{diff:.2f}%"
    else:
        icon = "🔻 🔴"
        action_text = "BREAKDOWN (หลุดแนวรับ)"
        diff_text = f"{diff:.2f}%"

    msg = f"""
🔔 *PRICE ALERT TRIGGERED!* {icon}
━━━━━━━━━━━━━━━━━━
💎 *Asset:* `{symbol}`
🏦 *Exch:* {exchange}

🎯 *Target:* {target_price:,.2f}
💰 *Current:* *{current_price:,.2f}* ({diff_text})

⚠️ *Condition:* {action_text}
━━━━━━━━━━━━━━━━━━
    """
    return msg.strip()