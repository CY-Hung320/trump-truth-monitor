"""
Trump Truth Social Monitor
自動監控川普在 Truth Social 上的新發言，翻譯成中文後傳送到 Telegram。

使用 Playwright 無頭瀏覽器載入 Truth Social 頁面，
攔截瀏覽器內部的 API 回應來取得貼文資料，繞過 Cloudflare 保護。
"""

import os
import time
import logging
import html
import re
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright
from deep_translator import GoogleTranslator
from dotenv import load_dotenv

load_dotenv()

# ── 設定 ──────────────────────────────────────────────
TRUMP_PROFILE_URL = "https://truthsocial.com/@realDonaldTrump"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "120"))

STATE_FILE = Path(__file__).parent / "last_seen_id.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── 工具函式 ──────────────────────────────────────────


def strip_html(text: str) -> str:
    """移除 HTML 標籤並還原 HTML entities。"""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def load_last_seen_id() -> str | None:
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip() or None
    return None


def save_last_seen_id(post_id: str) -> None:
    STATE_FILE.write_text(post_id)


def fetch_posts_via_playwright() -> list[dict]:
    """使用 Playwright 載入川普的 Truth Social 頁面，攔截 API 回應取得貼文。"""
    posts = []

    def handle_response(response):
        url = response.url
        if "/api/v1/accounts/" in url and "/statuses" in url:
            try:
                data = response.json()
                if isinstance(data, list):
                    posts.extend(data)
            except Exception:
                pass

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            page.on("response", handle_response)

            page.goto(TRUMP_PROFILE_URL, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(5000)

            browser.close()
    except Exception as e:
        log.error("Playwright 抓取失敗: %s", e)

    return posts


def filter_new_posts(posts: list[dict], since_id: str | None) -> list[dict]:
    """篩選出 since_id 之後的新貼文。"""
    if not since_id:
        return posts
    return [p for p in posts if p["id"] > since_id]


def translate_to_chinese(text: str) -> str:
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target="zh-TW").translate(text)
    except Exception as e:
        log.error("翻譯失敗: %s", e)
        return f"[翻譯失敗] {text}"


def send_telegram_message(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("Telegram 傳送失敗: %s", e)
        return False


def format_message(post: dict, translated: str) -> str:
    original = strip_html(post.get("content", ""))
    created_at = post.get("created_at", "未知時間")
    post_url = post.get("url") or post.get("uri", "")

    media_lines = []
    for attachment in post.get("media_attachments", []):
        media_type = attachment.get("type", "unknown")
        media_url = attachment.get("url", "")
        if media_url:
            media_lines.append(f"  [{media_type}] {media_url}")

    media_section = ""
    if media_lines:
        media_section = "\n\n📎 <b>附件:</b>\n" + "\n".join(media_lines)

    reblog_section = ""
    reblog = post.get("reblog")
    if reblog:
        reblog_text = strip_html(reblog.get("content", ""))
        reblog_translated = translate_to_chinese(reblog_text)
        reblog_author = reblog.get("account", {}).get("display_name", "未知")
        reblog_section = (
            f"\n\n🔁 <b>轉發自 {reblog_author}:</b>\n"
            f"{reblog_text}\n"
            f"<b>中文翻譯:</b> {reblog_translated}"
        )

    msg = (
        f"🇺🇸 <b>川普 Truth Social 新貼文</b>\n"
        f"🕐 {created_at}\n"
        f"{'─' * 30}\n\n"
        f"<b>原文:</b>\n{original}\n\n"
        f"<b>中文翻譯:</b>\n{translated}"
        f"{media_section}"
        f"{reblog_section}"
        f"\n\n🔗 {post_url}"
    )
    return msg


def process_posts(posts: list[dict]) -> str | None:
    posts = sorted(posts, key=lambda p: p["id"])
    latest_id = None

    for post in posts:
        content = strip_html(post.get("content", ""))
        if not content and not post.get("reblog"):
            log.info("跳過空白貼文 %s", post["id"])
            latest_id = post["id"]
            continue

        log.info("處理貼文 %s: %s", post["id"], content[:60])
        translated = translate_to_chinese(content)
        message = format_message(post, translated)

        if len(message) > 4096:
            message = message[:4090] + "\n..."

        if send_telegram_message(message):
            log.info("已傳送貼文 %s 到 Telegram", post["id"])
        else:
            log.warning("傳送貼文 %s 失敗", post["id"])

        latest_id = post["id"]
        time.sleep(1)

    return latest_id


def run_once() -> None:
    last_seen = load_last_seen_id()
    log.info("檢查新貼文 (上次: %s)", last_seen or "首次執行")

    all_posts = fetch_posts_via_playwright()
    if not all_posts:
        log.info("未取得任何貼文")
        return

    log.info("取得 %d 則貼文，篩選新貼文中...", len(all_posts))
    posts = filter_new_posts(all_posts, last_seen)

    if not posts:
        log.info("沒有新貼文")
        # 即使沒有新的，也更新 last_seen 確保首次執行後不會洗版
        if last_seen is None and all_posts:
            newest = max(all_posts, key=lambda p: p["id"])
            save_last_seen_id(newest["id"])
            log.info("首次執行，記錄最新貼文 ID: %s（不傳送）", newest["id"])
        return

    log.info("發現 %d 則新貼文", len(posts))

    if last_seen is None:
        # 首次執行，只傳送最新一則
        posts = [max(posts, key=lambda p: p["id"])]
        log.info("首次執行，僅傳送最新一則貼文")

    latest_id = process_posts(posts)
    if latest_id:
        save_last_seen_id(latest_id)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error(
            "請在 .env 檔案中設定 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID\n"
            "詳見 README.md 的設定步驟。"
        )
        return

    log.info("啟動 Trump Truth Social Monitor (Playwright 模式)")
    log.info("輪詢間隔: %d 秒", POLL_INTERVAL)

    while True:
        try:
            run_once()
        except Exception as e:
            log.exception("執行發生錯誤: %s", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
