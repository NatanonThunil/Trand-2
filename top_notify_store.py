import json
import os

FILE = "top_notify.json"

def load_top_notify_users():
    if not os.path.exists(FILE):
        return []
    with open(FILE, "r") as f:
        return json.load(f)

def save_top_notify_users(users):
    with open(FILE, "w") as f:
        json.dump(users, f)

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
