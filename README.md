# Trump Truth Social Monitor → Telegram

自動監控川普在 Truth Social 上的新發言，翻譯成中文後傳送到你的 Telegram。

## 設定步驟

### 1. 建立 Telegram Bot

1. 在 Telegram 搜尋 **@BotFather**，傳送 `/newbot`
2. 依照指示建立 Bot，取得 **Bot Token**（格式：`123456:ABC-DEF...`）
3. 搜尋 **@userinfobot**，傳送任意訊息，取得你的 **Chat ID**（純數字）
4. **先對你的 Bot 傳送一則訊息**（這樣 Bot 才能回傳訊息給你）

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`，填入你的 Token 和 Chat ID。

### 3. 執行方式

#### 方式 A：本機直接執行

```bash
pip install -r requirements.txt
python monitor.py
```

#### 方式 B：Docker（推薦用於雲端）

```bash
docker compose up -d
```

#### 方式 C：部署到雲端（免費方案）

**Railway.app：**
1. 在 GitHub 建立 repo，推送這個專案
2. 到 [railway.app](https://railway.app) 連結 GitHub repo
3. 在 Railway 設定環境變數 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`
4. 自動部署完成

**Render.com：**
1. 建立 Background Worker 類型的服務
2. 連結 GitHub repo
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python monitor.py`
5. 設定環境變數

**Fly.io：**
```bash
fly launch
fly secrets set TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx
fly deploy
```

## 運作方式

- 每 2 分鐘檢查一次 Truth Social（可透過 `POLL_INTERVAL` 調整）
- 使用 Truth Social 的 Mastodon 相容公開 API
- 使用 Google Translate 翻譯成繁體中文
- 首次執行只傳送最新一則（避免洗版）
- `last_seen_id.txt` 記錄已處理的貼文，重啟不會重複傳送
