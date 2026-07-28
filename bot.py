#!/usr/bin/env python3
"""
Pokémon GO Account Sales Description Writer Telegram Bot (Python Version)
===========================================================================
Powered by:
- pyTelegramBotAPI (telebot) for Telegram Bot interface
- Gemini Vision AI for OCR & Screenshot parsing
- Groq LLM (Llama 3.3 70B) for High-Converting Sales Copy generation
- JSON File storage for persistent user balance, history & queue
"""

import os
import sys
import json
import time
import base64
import logging
from datetime import datetime, timedelta
from threading import Timer
from typing import Dict, Any, List, Optional

import telebot
from telebot import types
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================
CONFIG = {
    "BOT_TOKEN": os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "",
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY") or "",
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY") or "",
    "ADMIN_ID": os.getenv("ADMIN_ID") or "7568676840",
    "FREE_COINS_LIMIT": 3,
    "GENERATION_COST": 4,
    "DB_FILE": os.path.join(os.getcwd(), "database.json"),
    "TEMP_DIR": os.path.join(os.getcwd(), "temp"),
}

# Ensure temp directory exists
os.makedirs(CONFIG["TEMP_DIR"], exist_ok=True)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PogoBot")

# ==========================================
# DATABASE LAYER (database.json)
# ==========================================
def load_db() -> Dict[str, Any]:
    default_db = {
        "users": [],
        "description_history": [],
        "temporary_upload_queue": [],
        "settings": {"group_chat_id": None}
    }
    if not os.path.exists(CONFIG["DB_FILE"]):
        save_db(default_db)
        return default_db
    try:
        with open(CONFIG["DB_FILE"], "r", encoding="utf-8") as f:
            data = json.load(f)
            if "users" not in data: data["users"] = []
            if "description_history" not in data: data["description_history"] = []
            if "temporary_upload_queue" not in data: data["temporary_upload_queue"] = []
            if "settings" not in data: data["settings"] = {"group_chat_id": None}
            return data
    except Exception as e:
        logger.error(f"Error loading database.json: {e}")
        return default_db

def save_db(data: Dict[str, Any]) -> None:
    try:
        with open(CONFIG["DB_FILE"], "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving database.json: {e}")

def is_subscription_active(expiry_str: Optional[str]) -> bool:
    if not expiry_str:
        return False
    try:
        expiry_dt = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
        now_dt = datetime.now(expiry_dt.tzinfo) if expiry_dt.tzinfo else datetime.now()
        return expiry_dt > now_dt
    except Exception:
        return False

def get_or_create_user(user_id: str, username: str = "Trainer") -> Dict[str, Any]:
    db = load_db()
    for user in db["users"]:
        if str(user["id"]) == str(user_id):
            if username and user.get("username") != username:
                user["username"] = username
                save_db(db)
            return user

    new_user = {
        "id": str(user_id),
        "username": username,
        "coins": 0,
        "free_trials_remaining": CONFIG["FREE_COINS_LIMIT"],
        "subscription_expiry": None,
        "descriptions_generated": 0,
        "join_date": datetime.utcnow().isoformat() + "Z"
    }
    db["users"].append(new_user)
    save_db(db)
    return new_user

def add_coins(user_id: str, amount: int) -> Dict[str, Any]:
    db = load_db()
    user = get_or_create_user(user_id)
    for u in db["users"]:
        if str(u["id"]) == str(user_id):
            u["coins"] += amount
            save_db(db)
            return u
    return user

def remove_coins(user_id: str, amount: int) -> Dict[str, Any]:
    db = load_db()
    user = get_or_create_user(user_id)
    for u in db["users"]:
        if str(u["id"]) == str(user_id):
            u["coins"] = max(0, u["coins"] - amount)
            save_db(db)
            return u
    return user

def add_subscription(user_id: str, plan: str) -> str:
    db = load_db()
    user = get_or_create_user(user_id)
    days_map = {"1d": 1, "3d": 3, "7d": 7, "31d": 31, "365d": 365}
    days = days_map.get(plan.lower(), 1)

    base_dt = datetime.utcnow()
    if user.get("subscription_expiry") and is_subscription_active(user["subscription_expiry"]):
        try:
            base_dt = datetime.fromisoformat(user["subscription_expiry"].replace("Z", ""))
        except Exception:
            pass

    new_expiry_dt = base_dt + timedelta(days=days)
    new_expiry_str = new_expiry_dt.isoformat() + "Z"

    for u in db["users"]:
        if str(u["id"]) == str(user_id):
            u["subscription_expiry"] = new_expiry_str
            save_db(db)
            return new_expiry_str
    return new_expiry_str

def remove_subscription(user_id: str) -> None:
    db = load_db()
    for u in db["users"]:
        if str(u["id"]) == str(user_id):
            u["subscription_expiry"] = None
            save_db(db)
            return

def get_queue(user_id: str) -> List[Dict[str, Any]]:
    db = load_db()
    return [item for item in db["temporary_upload_queue"] if str(item["user_id"]) == str(user_id)]

def add_to_queue(user_id: str, file_path: str) -> None:
    db = load_db()
    next_id = max([item.get("id", 0) for item in db["temporary_upload_queue"]], default=0) + 1
    new_item = {
        "id": next_id,
        "user_id": str(user_id),
        "file_path": file_path,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    db["temporary_upload_queue"].append(new_item)
    save_db(db)

def clear_queue(user_id: str) -> None:
    db = load_db()
    user_queue = [item for item in db["temporary_upload_queue"] if str(item["user_id"]) == str(user_id)]
    for item in user_queue:
        file_path = item.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error removing temp file {file_path}: {e}")
    db["temporary_upload_queue"] = [item for item in db["temporary_upload_queue"] if str(item["user_id"]) != str(user_id)]
    save_db(db)

def add_history(user_id: str, screenshots_count: int, description: str) -> None:
    db = load_db()
    next_id = max([item.get("id", 0) for item in db["description_history"]], default=0) + 1
    new_history = {
        "id": next_id,
        "user_id": str(user_id),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "screenshots_count": screenshots_count,
        "description": description
    }
    db["description_history"].append(new_history)

    # Deduct coins or free trial
    for u in db["users"]:
        if str(u["id"]) == str(user_id):
            u["descriptions_generated"] += 1
            if not is_subscription_active(u.get("subscription_expiry")):
                if u.get("free_trials_remaining", 0) > 0:
                    u["free_trials_remaining"] -= 1
                else:
                    u["coins"] = max(0, u.get("coins", 0) - CONFIG["GENERATION_COST"])
            break
    save_db(db)

def get_history(user_id: str) -> List[Dict[str, Any]]:
    db = load_db()
    user_history = [item for item in db["description_history"] if str(item["user_id"]) == str(user_id)]
    user_history.sort(key=lambda x: x.get("id", 0), reverse=True)
    return user_history

def get_group_chat_id() -> Optional[str]:
    db = load_db()
    return db.get("settings", {}).get("group_chat_id") or os.getenv("TELEGRAM_GROUP_ID")

def set_group_chat_id(chat_id: Optional[str]) -> None:
    db = load_db()
    if "settings" not in db:
        db["settings"] = {}
    db["settings"]["group_chat_id"] = str(chat_id) if chat_id else None
    save_db(db)

# ==========================================
# GEMINI VISION & GROQ AI ENGINE
# ==========================================
def analyze_screenshots_gemini(file_paths: List[str]) -> Dict[str, Any]:
    """
    Analyzes uploaded Pokémon GO screenshots using Gemini 2.5/3.5 Vision API.
    Extracts structured JSON containing trainer stats, Pokémon counts, items, etc.
    """
    gemini_key = CONFIG["GEMINI_API_KEY"]
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY is not configured in environment variables.")

    parts = []
    for fp in file_paths:
        if os.path.exists(fp):
            with open(fp, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": encoded
                    }
                })

    if not parts:
        raise ValueError("No valid image files found to process.")

    prompt_text = (
        "You are an expert OCR and image analysis system specialized in parsing Pokémon GO screenshots.\n"
        "Analyze the provided screenshots and extract every visible statistic and asset.\n\n"
        "Instructions:\n"
        "1. Merge information from all screenshots into one cohesive account profile.\n"
        "2. Only extract values that are actually visible. Do NOT guess, invent, or estimate missing numbers.\n"
        "3. Output valid JSON adhering to this schema:\n"
        "{\n"
        '  "trainerLevel": int or null,\n'
        '  "startDate": string or null,\n'
        '  "totalXp": string or null,\n'
        '  "xpProgress": string or null,\n'
        '  "team": string or null,\n'
        '  "trainerName": string or null,\n'
        '  "stardust": string or null,\n'
        '  "pokeCoins": string or null,\n'
        '  "pokemonStorage": string or null,\n'
        '  "itemStorage": string or null,\n'
        '  "pokemonCaught": string or null,\n'
        '  "shinyCount": int or null,\n'
        '  "legendaryCount": int or null,\n'
        '  "mythicalCount": int or null,\n'
        '  "shadowCount": int or null,\n'
        '  "purifiedCount": int or null,\n'
        '  "luckyCount": int or null,\n'
        '  "hundoCount": int or null,\n'
        '  "featuredPokemon": [{"name": "Mewtwo", "cp": 4178, "isShiny": true, "isLegendary": true}],\n'
        '  "premiumItems": [{"name": "Master Ball", "count": 1}]\n'
        "}\n"
    )
    parts.append({"text": prompt_text})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        # Fallback model check
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
        response = requests.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"Gemini Vision API error ({response.status_code}): {response.text}")

    res_json = response.json()
    try:
        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw_text)
    except Exception as e:
        logger.error(f"Failed to parse Gemini response JSON: {e}")
        return {"raw": raw_text if 'raw_text' in locals() else "Parsing error"}

def generate_sales_description_groq(account_data: Dict[str, Any]) -> str:
    """
    Generates a high-converting Telegram sales description using Groq LLM (Llama 3.3 70B).
    Falls back gracefully to Gemini if GROQ_API_KEY is not provided.
    """
    prompt = f"""You are a professional Pokémon GO Account Appraiser and Sales copywriter. Your job is to format the extracted account data into a highly appealing, professional, clean, and factual sales description for Telegram.

CRITICAL INSTRUCTIONS:
1. ONLY include fields and statistics that have non-null, non-empty values in the provided data.
2. Omit missing or null metrics completely. Do NOT print "N/A" or "None".
3. Do NOT wrap your output in markdown code blocks (like ```). Output raw formatted text directly.

Structured Account Data:
{json.dumps(account_data, indent=2)}

Target Telegram Format to Output:
🔥 POKÉMON GO ACCOUNT ON SALE 🔥

⚡ LEVEL {account_data.get('trainerLevel', 'PRO')} ACCOUNT ⚡

━━━━━━━━━━━━━━━━━━

🏆 ACCOUNT OVERVIEW

━━━━━━━━━━━━━━━━━━
⭐ Trainer Level: {account_data.get('trainerLevel', 'N/A')}
📅 Start Date: {account_data.get('startDate', 'N/A')}
⚡ Stardust: {account_data.get('stardust', 'N/A')}
🪙 PokéCoins: {account_data.get('pokeCoins', 'N/A')}
🎒 Pokémon Storage: {account_data.get('pokemonStorage', 'N/A')}
🎁 Item Storage: {account_data.get('itemStorage', 'N/A')}

━━━━━━━━━━━━━━━━━━

✨ COLLECTION STATS

━━━━━━━━━━━━━━━━━━
🌈 Shiny Pokémon: {account_data.get('shinyCount', 0)}
👑 Legendary Pokémon: {account_data.get('legendaryCount', 0)}
💎 Mythical Pokémon: {account_data.get('mythicalCount', 0)}
🔥 Shadow Pokémon: {account_data.get('shadowCount', 0)}
🎯 100% IV (Hundo) Pokémon: {account_data.get('hundoCount', 0)}

━━━━━━━━━━━━━━━━━━

💥 WHY BUY THIS ACCOUNT?

━━━━━━━━━━━━━━━━━━
✅ Verified High-Level Pokémon GO Account
✅ Rare Shiny & Legendary Collection
✅ Instant Handover & 100% Safe

🔥 ACCOUNT ON SALE — SERIOUS BUYERS ONLY! 🔥
📌 Complete screenshot proof included.
"""

    groq_key = CONFIG["GROQ_API_KEY"]
    if groq_key:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "You are a professional Pokémon GO Account Appraiser and Sales copywriter."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }
            res = requests.post(url, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                result = res.json()
                content = result["choices"][0]["message"]["content"]
                if content and content.strip():
                    return content.strip()
        except Exception as e:
            logger.error(f"Groq API call failed: {e}. Falling back to Gemini.")

    # Fallback to Gemini for text generation
    gemini_key = CONFIG["GEMINI_API_KEY"]
    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            content = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            return content.strip()

    raise RuntimeError("Both Groq API and Gemini API calls failed. Please check your API keys.")

# ==========================================
# TELEGRAM BOT HANDLERS
# ==========================================
bot = None
last_receipt_msg_id = {}
active_downloads = {}
debounce_timers = {}

def announce_transaction_to_group(bot_instance: telebot.TeleBot, message: str) -> None:
    group_id = get_group_chat_id()
    if not group_id or not bot_instance:
        return
    try:
        bot_instance.send_message(group_id, message, parse_mode="Markdown")
        logger.info(f"Announced to group {group_id}: {message[:50]}...")
    except Exception as e:
        logger.error(f"Failed to announce to group {group_id}: {e}")

def setup_bot_handlers(bot_instance: telebot.TeleBot):

    @bot_instance.message_handler(commands=['start'])
    def cmd_start(msg):
        user_id = str(msg.from_user.id)
        username = msg.from_user.username or msg.from_user.first_name or "Trainer"
        user = get_or_create_user(user_id, username)

        welcome_text = (
            f"👋 *Welcome to the Pokémon GO Description Writer Bot!* 👋\n\n"
            f"I generate premium, high-converting Pokémon GO account sale listings from your in-game screenshots using OCR, Vision AI, and Groq LLM!\n\n"
            f"🎁 *Your Balance:* You have *{user['free_trials_remaining']}* free trial generations!\n\n"
            f"🚀 *How to use:* \n"
            f"1. Upload one or more screenshots of your Pokémon GO account.\n"
            f"2. I will queue them up.\n"
            f"3. Send /generate when you are ready.\n\n"
            f"Send /help to see all commands!"
        )
        bot_instance.reply_to(msg, welcome_text, parse_mode="Markdown")

    @bot_instance.message_handler(commands=['help'])
    def cmd_help(msg):
        user_id = str(msg.from_user.id)
        is_admin = user_id == str(CONFIG["ADMIN_ID"])

        help_text = (
            "📖 *POKÉMON GO BOT COMMAND GUIDE* 📖\n\n"
            "⚡ *Core Commands:*\n"
            "• /generate - Analyze your uploaded screenshots and write your description\n"
            "• /balance - Check your available coins and free trials\n"
            "• /subscription - Check your active subscription details\n"
            "• /history - View your previously generated account summaries\n"
            "• /buy - Find out how to purchase coins or a subscription plan\n"
            "• /help - Display this command guide\n\n"
            "💼 *Subscription Plans:*\n"
            "• 1 Day • 3 Days • 7 Days • 31 Days • 365 Days\n"
            "Subscriptions give you *Unlimited Generations*!\n\n"
            "🪙 *Coin Rates:*\n"
            "After free trials are used up, each generation costs *4 Coins*.\n\n"
        )
        if is_admin:
            help_text += (
                "🛡️ *Admin Commands:*\n"
                "• `/addcoins <user_id> <amount>`\n"
                "• `/removecoins <user_id> <amount>`\n"
                "• `/addsub <user_id> <plan>`\n"
                "• `/removesub <user_id>`\n"
                "• `/userinfo <user_id>`\n"
                "• `/setgroup <group_id>`\n\n"
            )
        help_text += "📌 *Just upload your screenshots directly to get started!*"
        bot_instance.reply_to(msg, help_text, parse_mode="Markdown")

    @bot_instance.message_handler(commands=['balance'])
    def cmd_balance(msg):
        user_id = str(msg.from_user.id)
        user = get_or_create_user(user_id)
        text = (
            "🪙 *YOUR BALANCE* 🪙\n\n"
            f"• *Free Trials Remaining:* `{user['free_trials_remaining']}` generations\n"
            f"• *Coins Balance:* `{user['coins']}` coins\n\n"
            "💡 _Note: After free trials are exhausted, generating a description costs 4 coins._"
        )
        bot_instance.reply_to(msg, text, parse_mode="Markdown")

    @bot_instance.message_handler(commands=['subscription'])
    def cmd_subscription(msg):
        user_id = str(msg.from_user.id)
        user = get_or_create_user(user_id)
        active = is_subscription_active(user.get("subscription_expiry"))
        expiry = user.get("subscription_expiry", "None") or "None"

        text = (
            "📅 *SUBSCRIPTION STATUS* 📅\n\n"
            f"• *Status:* {'🟢 *ACTIVE (Unlimited Access)*' if active else '🔴 *INACTIVE*'}\n"
            f"• *Expires on:* `{expiry}`\n\n"
            "To activate or renew, send /buy."
        )
        bot_instance.reply_to(msg, text, parse_mode="Markdown")

    @bot_instance.message_handler(commands=['buy'])
    def cmd_buy(msg):
        user_id = str(msg.from_user.id)
        text = (
            "🪙 *COINS & SUBSCRIPTIONS PRESETS* 🪙\n\n"
            "Need unlimited access or more coins to generate sales copy? Select a premium plan:\n\n"
            "📦 *Subscription Plans (Unlimited Generations):*\n"
            "• 🌟 *1 Day Access:* $1.99\n"
            "• 🌟 *3 Days Access:* $3.99\n"
            "• 🌟 *7 Days Access:* $6.99\n"
            "• 🔥 *31 Days Access:* $14.99\n"
            "• 👑 *365 Days Access:* $59.99\n\n"
            "🪙 *Coin Packs:*\n"
            "• 🎒 *Starter (10 Coins):* $0.99\n"
            "• ⚔️ *Pro (50 Coins):* $3.99\n"
            "• 🏆 *Elite (200 Coins):* $12.99\n\n"
            "💬 *How to Purchase:*\n"
            f"Please contact our administrator with your *User ID* (`{user_id}`) to buy coins or a subscription."
        )
        bot_instance.reply_to(msg, text, parse_mode="Markdown")

    @bot_instance.message_handler(commands=['history'])
    def cmd_history(msg):
        user_id = str(msg.from_user.id)
        history = get_history(user_id)
        if not history:
            bot_instance.reply_to(msg, "📭 You haven't generated any descriptions yet! Upload screenshots and send /generate to start.")
            return

        latest = history[0]["description"]
        bot_instance.send_message(msg.chat.id, f"📂 *GENERATION HISTORY* ({len(history)} items):\n\nListing your latest generation below:", parse_mode="Markdown")
        bot_instance.send_message(msg.chat.id, latest)

    @bot_instance.message_handler(commands=['setgroup'])
    def cmd_setgroup(msg):
        user_id = str(msg.from_user.id)
        if user_id != str(CONFIG["ADMIN_ID"]):
            bot_instance.reply_to(msg, "❌ *Access Denied:* Admin only command.", parse_mode="Markdown")
            return

        parts = msg.text.strip().split()
        target_group = str(msg.chat.id)
        if len(parts) > 1:
            target_group = parts[1]
        elif msg.chat.type == "private":
            bot_instance.reply_to(msg, "💡 Usage: `/setgroup <group_id>` or send `/setgroup` inside a Telegram Group.", parse_mode="Markdown")
            return

        set_group_chat_id(target_group)
        bot_instance.reply_to(msg, f"✅ *Telegram group successfully linked!*\n\n• Group ID: `{target_group}`", parse_mode="Markdown")

    # Admin commands: /addcoins, /removecoins, /addsub, /removesub, /userinfo
    @bot_instance.message_handler(commands=['addcoins', 'removecoins', 'addsub', 'removesub', 'userinfo'])
    def cmd_admin_actions(msg):
        user_id = str(msg.from_user.id)
        if user_id != str(CONFIG["ADMIN_ID"]):
            bot_instance.reply_to(msg, "❌ *Access Denied:* Admin permissions required.", parse_mode="Markdown")
            return

        parts = msg.text.strip().split()
        cmd = parts[0].lower()

        try:
            if cmd == "/addcoins":
                if len(parts) < 3:
                    bot_instance.reply_to(msg, "Usage: `/addcoins <user_id> <amount>`", parse_mode="Markdown")
                    return
                target_id, amount = parts[1], int(parts[2])
                updated_user = add_coins(target_id, amount)
                bot_instance.reply_to(msg, f"✅ Added *{amount}* coins to user `{target_id}`.", parse_mode="Markdown")
                announce_transaction_to_group(
                    bot_instance,
                    f"🔔 *TRANSACTION COMPLETED* 🔔\n\n💰 Added *{amount}* Coins to user `{target_id}`.\n✨ New Balance: *{updated_user['coins']}* Coins."
                )

            elif cmd == "/removecoins":
                if len(parts) < 3:
                    bot_instance.reply_to(msg, "Usage: `/removecoins <user_id> <amount>`", parse_mode="Markdown")
                    return
                target_id, amount = parts[1], int(parts[2])
                updated_user = remove_coins(target_id, amount)
                bot_instance.reply_to(msg, f"✅ Removed *{amount}* coins from user `{target_id}`.", parse_mode="Markdown")

            elif cmd == "/addsub":
                if len(parts) < 3:
                    bot_instance.reply_to(msg, "Usage: `/addsub <user_id> <plan>` (1d, 3d, 7d, 31d, 365d)", parse_mode="Markdown")
                    return
                target_id, plan = parts[1], parts[2]
                expiry = add_subscription(target_id, plan)
                bot_instance.reply_to(msg, f"✅ Subscription *{plan}* granted to `{target_id}`. Expires: `{expiry}`", parse_mode="Markdown")
                announce_transaction_to_group(
                    bot_instance,
                    f"🔔 *SUBSCRIPTION ACTIVATED* 🔔\n\n🎉 Plan *{plan.upper()}* granted to user `{target_id}`.\n📅 Valid Until: `{expiry}`."
                )

            elif cmd == "/removesub":
                if len(parts) < 2:
                    bot_instance.reply_to(msg, "Usage: `/removesub <user_id>`", parse_mode="Markdown")
                    return
                target_id = parts[1]
                remove_subscription(target_id)
                bot_instance.reply_to(msg, f"✅ Subscription revoked for user `{target_id}`.", parse_mode="Markdown")

            elif cmd == "/userinfo":
                target_id = parts[1] if len(parts) > 1 else user_id
                target_user = get_or_create_user(target_id)
                active = is_subscription_active(target_user.get("subscription_expiry"))
                text = (
                    f"👤 *USER INFORMATION* 👤\n\n"
                    f"• *User ID:* `{target_user['id']}`\n"
                    f"• *Username:* @{target_user.get('username', 'None')}\n"
                    f"• *Coins:* `{target_user['coins']}`\n"
                    f"• *Free Trials:* `{target_user['free_trials_remaining']}`\n"
                    f"• *Subscription:* {'🟢 Active' if active else '🔴 Inactive'}\n"
                    f"• *Expiry:* `{target_user.get('subscription_expiry') or 'None'}`\n"
                    f"• *Generations:* `{target_user['descriptions_generated']}`"
                )
                bot_instance.reply_to(msg, text, parse_mode="Markdown")

        except Exception as e:
            bot_instance.reply_to(msg, f"❌ Error: {str(e)}")

    @bot_instance.message_handler(commands=['generate'])
    def cmd_generate(msg):
        user_id = str(msg.from_user.id)
        queue = get_queue(user_id)
        if not queue:
            bot_instance.reply_to(msg, "❌ *No screenshots in queue!*\n\nPlease upload one or more screenshots first, then send /generate.", parse_mode="Markdown")
            return

        user = get_or_create_user(user_id)
        active_sub = is_subscription_active(user.get("subscription_expiry"))
        free_trials = user.get("free_trials_remaining", 0) > 0
        has_coins = user.get("coins", 0) >= CONFIG["GENERATION_COST"]

        if not active_sub and not free_trials and not has_coins:
            bot_instance.reply_to(
                msg,
                f"❌ *Insufficient Balance!*\n\n• Current Coins: `{user.get('coins', 0)}`\n• Required: `{CONFIG['GENERATION_COST']}` coins per generation.\nSend /buy to top-up!",
                parse_mode="Markdown"
            )
            return

        bot_instance.reply_to(msg, f"⚙️ *Processing {len(queue)} screenshot(s)...*\nRunning OCR, Vision AI & Groq description writer. Please wait 5-10 seconds.", parse_mode="Markdown")

        try:
            file_paths = [q["file_path"] for q in queue if os.path.exists(q["file_path"])]
            
            # 1. OCR / Vision Analysis via Gemini
            parsed_data = analyze_screenshots_gemini(file_paths)

            # 2. Description Generation via Groq (with Gemini fallback)
            description = generate_sales_description_groq(parsed_data)

            # 3. Save History & Deduct Coins
            add_history(user_id, len(queue), description)

            # 4. Reply to user
            bot_instance.send_message(msg.chat.id, description)

            # 5. Clear queue
            clear_queue(user_id)

        except Exception as e:
            logger.error(f"Error executing /generate for user {user_id}: {e}")
            bot_instance.reply_to(msg, f"❌ *Generation Failed:* {str(e)}", parse_mode="Markdown")

    @bot_instance.message_handler(content_types=['photo'])
    def handle_photo(msg):
        user_id = str(msg.from_user.id)
        try:
            # Download highest resolution photo
            photo = msg.photo[-1]
            file_info = bot_instance.get_file(photo.file_id)
            downloaded_file = bot_instance.download_file(file_info.file_path)

            file_filename = f"{user_id}_{int(time.time()*1000)}.png"
            local_path = os.path.join(CONFIG["TEMP_DIR"], file_filename)

            with open(local_path, 'wb') as f:
                f.write(downloaded_file)

            add_to_queue(user_id, local_path)

            # Debounced response timer
            if user_id in debounce_timers:
                debounce_timers[user_id].cancel()

            def send_debounced_confirm():
                q = get_queue(user_id)
                bot_instance.send_message(
                    msg.chat.id,
                    f"✅ Screenshot received successfully!\n\n"
                    f"• Total screenshots in queue: *{len(q)}*\n"
                    f"• Upload more if needed, or send /generate when ready!",
                    parse_mode="Markdown"
                )

            timer = Timer(2.0, send_debounced_confirm)
            debounce_timers[user_id] = timer
            timer.start()

        except Exception as e:
            logger.error(f"Failed handling photo upload for {user_id}: {e}")
            bot_instance.reply_to(msg, "❌ Failed to process screenshot. Please try uploading again.")

# ==========================================
# MAIN ENTRYPOINT
# ==========================================
if __name__ == "__main__":
    token = CONFIG["BOT_TOKEN"]
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set in environment or .env file.")
        logger.warning("Please set TELEGRAM_BOT_TOKEN=your_token in .env to run the Python bot live.")
        sys.exit(1)

    logger.info("Initializing Python Telegram Bot (telebot)...")
    bot = telebot.TeleBot(token, parse_mode=None)
    setup_bot_handlers(bot)

    logger.info("🚀 Python Telegram Bot is running and polling for messages...")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Bot runtime exception: {e}")
