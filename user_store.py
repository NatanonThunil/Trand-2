import json
import os

# ดึง URL สำหรับเชื่อมต่อฐานข้อมูลจากตั้งค่าของ Render
MONGO_URI = os.getenv("MONGO_URI")

FILE = "/tmp/data/users.json"
db_collection = None

print("========================================")
print(f"🔍 เช็คสถานะ MONGO_URI: {'✅ มีข้อมูล' if MONGO_URI else '❌ ว่างเปล่า (หาไม่เจอ)'}")

# ถ้ามีการตั้งค่า MongoDB ระบบจะเชื่อมต่ออัตโนมัติ
if MONGO_URI:
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI)
        # ทดสอบการเชื่อมต่อ
        client.admin.command('ping') 
        db = client["TradingBotDB"]
        db_collection = db["all_users"]
        print("✅ MongoDB: เชื่อมต่อฐานข้อมูล 'all_users' สำเร็จแล้ว! ข้อมูลจะไม่หายอีกต่อไป")
    except Exception as e:
        print(f"❌ MongoDB Connection Error (เชื่อมต่อล้มเหลว): {e}")
        db_collection = None
else:
    print("⚠️ ระบบจะใช้การเซฟลงไฟล์ /tmp (ข้อมูลจะหายเมื่ออัปเดตโค้ด)")
print("========================================")

def load_users():
    try:
        # โหลดจากฐานข้อมูลออนไลน์
        if db_collection is not None:
            doc = db_collection.find_one({"_id": "general_users_list"})
            return doc.get("chat_ids", []) if doc else []
        # โหลดจากไฟล์เครื่อง
        else:
            if not os.path.exists(FILE): return []
            with open(FILE, "r") as f: 
                return json.load(f)
    except Exception as e:
        print(f"❌ Load Users Error: {e}")
        return []

def save_users(users):
    try:
        # บังคับให้ทุกคนเป็นตัวเลข (int) และลบตัวซ้ำออกให้หมด
        users = list(set([int(x) for x in users])) 
        
        # เซฟลงฐานข้อมูลออนไลน์
        if db_collection is not None:
            db_collection.update_one(
                {"_id": "general_users_list"},
                {"$set": {"chat_ids": users}},
                upsert=True
            )
        # เซฟลงไฟล์เครื่อง
        else:
            os.makedirs(os.path.dirname(FILE), exist_ok=True)
            with open(FILE, "w") as f: 
                json.dump(users, f)
    except Exception as e:
        print(f"❌ Save Users Error: {e}")

def is_new_user(chat_id):
    users = load_users()
    return int(chat_id) not in [int(x) for x in users]

def mark_user_seen(chat_id):
    users = load_users()
    chat_id = int(chat_id)
    if chat_id not in [int(x) for x in users]:
        users.append(chat_id)
        save_users(users)