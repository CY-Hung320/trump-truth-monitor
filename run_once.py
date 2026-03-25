"""
GitHub Actions 入口：持續迴圈檢查新貼文。
每 2 分鐘檢查一次，運行 50 分鐘後自動結束，
讓下一個排程的 GitHub Actions job 接手。
"""

import time
import logging
from monitor import run_once

log = logging.getLogger(__name__)

MAX_RUNTIME = 50 * 60  # 50 分鐘（留 10 分鐘緩衝給下一輪）
POLL_INTERVAL = 120     # 每 2 分鐘

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log.info("啟動監控迴圈，間隔 %d 秒，最長運行 %d 分鐘", POLL_INTERVAL, MAX_RUNTIME // 60)

    start = time.time()
    while time.time() - start < MAX_RUNTIME:
        try:
            run_once()
        except Exception as e:
            log.exception("執行發生錯誤: %s", e)
        elapsed = time.time() - start
        remaining = MAX_RUNTIME - elapsed
        if remaining < POLL_INTERVAL:
            break
        time.sleep(POLL_INTERVAL)

    log.info("本輪結束，已運行 %.1f 分鐘", (time.time() - start) / 60)
