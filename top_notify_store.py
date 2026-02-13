import json
import os

# ✅ ต้องมี /tmp/data/ นำหน้า
FILE = "/tmp/data/notify_users.json"

def load_top_notify_users():
    if not os.path.exists(FILE): return []
    try:
        with open(FILE, "r") as f: return json.load(f)
    except: return []

def save_top_notify_users(users):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w") as f: json.dump(users, f)

def add_top_notify_user(chat_id):
    users = load_top_notify_users()
    if chat_id not in users:
        users.append(chat_id)
        save_top_notify_users(users)

def remove_top_notify_user(chat_id):
    users = load_top_notify_users()
    if chat_id in users:
        users.remove(chat_id)
        save_top_notify_users(users)