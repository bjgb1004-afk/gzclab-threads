"""Fetch views/likes/replies for posts published >=24h ago, once each.

24h wait lets metrics settle; the "insights" key check means each post is
only queried once — no repeat re-measurement, no history tracking.
"""

import datetime
import json
import os
import pathlib
import sys
import urllib.request

from publish import telegram

API = "https://graph.threads.net/v1.0"
METRICS = "views,likes,replies,reposts,quotes"
QUEUE = pathlib.Path(__file__).with_name("queue.json")
# 글이 삭제됐거나(THApiException code 100) 그 타입이 insights를 지원 안 하면 fetch가
# 영원히 같은 이유로 실패한다. 재시도 횟수를 안 끊으면 5분마다 같은 실패 알림이 영원히
# 온다(2026-10-13 실제 사례: talk-pm-05, 6일간 매 틱 반복). N번 시도 후 포기한다.
MAX_ATTEMPTS = 3


def fetch(media_id, token):
    url = f"{API}/{media_id}/insights?metric={METRICS}&access_token={token}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    return {m["name"]: m["values"][0]["value"] for m in data["data"]}


def main():
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    due = [
        p for p in queue
        if p.get("status") == "published" and p.get("post_id") and p.get("published_at") and "insights" not in p
        and now - datetime.datetime.fromisoformat(p["published_at"]) >= datetime.timedelta(hours=24)
    ]
    if not due:
        return 0

    changed = False
    for p in due:
        try:
            p["insights"] = fetch(p["post_id"], TOKEN)
            changed = True
        except Exception as e:
            detail = e.read().decode()[:300] if hasattr(e, "read") else str(e)
            attempts = p.get("insights_attempts", 0) + 1
            p["insights_attempts"] = attempts
            changed = True
            if attempts >= MAX_ATTEMPTS:
                p["insights"] = {"error": detail[:200]}  # 이후 due에서 영구히 빠진다
                telegram(f"⚠️ insights 수집 포기({attempts}번 실패)\n{p['id']}\n{detail}")
            else:
                telegram(f"⚠️ insights 수집 실패({attempts}/{MAX_ATTEMPTS})\n{p['id']}\n{detail}")

    if changed:
        QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    TOKEN = os.environ.get("THREADS_TOKEN")
    if not TOKEN:
        print("THREADS_TOKEN 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    sys.exit(main())
