"""
川普 Truth Social 貼文監控 → 翻譯中文 → 發送 Telegram
（GitHub Actions 版本 — 單次執行）
"""

import cloudscraper
import requests
import json
import os
import re
from datetime import datetime
from deep_translator import GoogleTranslator

# ===== 從環境變數讀取設定 =====
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TRUMP_ACCOUNT_ID = "107780257626128497"

SENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_posts.json")


def load_sent_posts():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_sent_posts(sent_ids):
    with open(SENT_FILE, "w") as f:
        json.dump(sorted(sent_ids), f, indent=2)


def fetch_latest_truths():
    url = f"https://truthsocial.com/api/v1/accounts/{TRUMP_ACCOUNT_ID}/statuses"
    params = {"limit": 10, "exclude_replies": True}
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[錯誤] 取得貼文失敗: {e}")
        return []


def clean_html(html_text):
    text = re.sub(r"<br\s*/?>", "\n", html_text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    return text.strip()


def translate_to_chinese(text):
    if not text:
        return ""
    try:
        translated = GoogleTranslator(source="en", target="zh-TW").translate(text)
        return translated or text
    except Exception as e:
        print(f"[錯誤] 翻譯失敗: {e}")
        return text


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        print("[成功] Telegram 訊息已發送")
        return True
    except requests.RequestException as e:
        print(f"[錯誤] Telegram 發送失敗: {e}")
        return False


def format_message(post, translated_text):
    original_text = clean_html(post.get("content", ""))
    created_at = post.get("created_at", "")
    post_url = post.get("url", "") or post.get("uri", "")

    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, AttributeError):
        time_str = created_at

    reblog = post.get("reblog")
    if reblog:
        reblog_author = reblog.get("account", {}).get("display_name", "Unknown")
        original_text = clean_html(reblog.get("content", ""))
        translated_text = translate_to_chinese(original_text)
        msg = (
            f"🔄 <b>川普轉發了 {reblog_author} 的貼文</b>\n"
            f"🕐 {time_str}\n\n"
            f"📝 原文:\n{original_text}\n\n"
            f"🇹🇼 中文翻譯:\n{translated_text}"
        )
    else:
        msg = (
            f"🔔 <b>川普最新 Truth Social 貼文</b>\n"
            f"🕐 {time_str}\n\n"
            f"📝 原文:\n{original_text}\n\n"
            f"🇹🇼 中文翻譯:\n{translated_text}"
        )

    if post_url:
        msg += f"\n\n🔗 <a href='{post_url}'>查看原文</a>"

    media = post.get("media_attachments", [])
    if media:
        msg += f"\n\n📎 包含 {len(media)} 個附件"
        for m in media:
            preview_url = m.get("preview_url") or m.get("url")
            if preview_url:
                msg += f"\n{preview_url}"

    return msg


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 開始檢查川普 Truth Social...")

    sent_ids = load_sent_posts()
    posts = fetch_latest_truths()

    if not posts:
        print("[資訊] 無法取得貼文")
        return

    posts.sort(key=lambda p: p.get("created_at", ""))

    new_count = 0
    for post in posts:
        post_id = post.get("id", "")
        if post_id in sent_ids:
            continue

        content = clean_html(post.get("content", ""))
        reblog = post.get("reblog")
        if reblog:
            content = clean_html(reblog.get("content", ""))

        if not content:
            sent_ids.add(post_id)
            continue

        translated = translate_to_chinese(content)
        message = format_message(post, translated)

        if send_telegram_message(message):
            sent_ids.add(post_id)
            new_count += 1

    save_sent_posts(sent_ids)
    print(f"[完成] 發送了 {new_count} 則新貼文，共追蹤 {len(sent_ids)} 則")


if __name__ == "__main__":
    main()
