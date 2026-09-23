"""Publish one queued post to Threads, then drop its link in the first reply.

Queue lives in queue.json. Each run takes the oldest pending item, publishes it,
marks it published, and commits the file back (the workflow does the commit).
"""

import datetime
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

API = "https://graph.threads.net/v1.0"
QUEUE = pathlib.Path(__file__).with_name("queue.json")


def api(path, params):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{API}/{path}", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def publish(text, reply_to=None):
    params = {"media_type": "TEXT", "text": text, "access_token": TOKEN}
    if reply_to:
        params["reply_to_id"] = reply_to
    container = api("me/threads", params)["id"]
    return api("me/threads_publish", {"creation_id": container, "access_token": TOKEN})["id"]


def telegram(text):
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        return
    body = urllib.parse.urlencode(
        {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text}
    ).encode()
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=30).read()
    except Exception as e:  # notification failure must not fail the run
        print(f"telegram failed: {e}", file=sys.stderr)


def current_slot():
    """KST 기준 아침/점심/저녁. 지역 시리즈만 아침에 나가게 해서 같은 포맷 연속을 막는다."""
    hour = (datetime.datetime.now(datetime.timezone.utc).hour + 9) % 24
    return "am" if hour < 10 else "pm" if hour < 16 else "night"


def main():
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    pending = [p for p in queue if p.get("status") == "pending"]
    if not pending:
        telegram("⚠️ 스레드 큐가 비었습니다. 다음 글이 발행되지 않습니다.")
        return 1

    slot = current_slot()
    # 해당 슬롯 글이 떨어졌으면 아무거나 내보낸다. 거르는 것보다 나가는 게 낫다.
    post = next((p for p in pending if p.get("slot") == slot), pending[0])
    try:
        post_id = publish(post["text"])
        if post.get("link"):
            publish(post["link"], reply_to=post_id)
    except Exception as e:
        detail = e.read().decode()[:300] if hasattr(e, "read") else str(e)
        telegram(f"❌ 스레드 발행 실패\n{post['id']}\n{detail}")
        raise

    post["status"] = "published"
    post["post_id"] = post_id
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    left = len(pending) - 1
    msg = f"✅ 스레드 발행됨 ({post['id']})\nhttps://www.threads.net/@gzclab\n남은 큐: {left}개"
    if left <= 3:
        msg += "\n⚠️ 큐 부족 — 다음 세션에서 채울 것"
    telegram(msg)
    return 0


if __name__ == "__main__":
    TOKEN = os.environ.get("THREADS_TOKEN")
    if not TOKEN:
        print("THREADS_TOKEN 미설정 — 발급 전까지 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    sys.exit(main())
