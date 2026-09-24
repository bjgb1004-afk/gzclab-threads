"""Publish one queued post to Threads, then drop a short lead line + its link in the first reply.

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
# 댓글에 링크만 던지면 광고로 읽힌다. 한 마디 붙이고 링크를 단다.
# 매번 같은 문구면 그것도 봇 티가 나서 발행 순서대로 돌려 쓴다.
REPLY_LINES = (
    "동네별로 1등 많이 나온 집 지도에 다 찍어놨음. 여기서 확인:",
    "내 주변 명당 어딘지 바로 보고 싶으면 이걸로 보면 됨:",
    "전국 판매점 1등 횟수 정리해둔 앱임. 무료:",
    "지도 켜고 가까운 순으로 보면 편함:",
)
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
    # 슬롯 글이 떨어졌을 때 그냥 맨 앞을 집으면 TOP5가 하루 세 번 나간다(큐 앞쪽이 전부
    # TOP5라서). 같은 종류 연속이 제일 빨리 질리게 만드니, 직전 발행과 종류가 다른 걸 집는다.
    # 큐 순서 != 발행 순서(새 글이 앞에 붙는다). 직전 발행은 시각으로만 알 수 있다.
    done = [p for p in queue if p.get("published_at")]
    last = max(done, key=lambda p: p["published_at"])["id"].split("-")[0] if done else None
    post = next(
        (p for p in pending if p.get("slot") == slot),
        next((p for p in pending if p["id"].split("-")[0] != last), pending[0]),
    )
    try:
        post_id = publish(post["text"])
        if post.get("link"):
            done = sum(1 for p in queue if p.get("status") == "published")
            lead = post.get("reply") or REPLY_LINES[done % len(REPLY_LINES)]
            publish(f"{lead}\n{post['link']}", reply_to=post_id)
    except Exception as e:
        detail = e.read().decode()[:300] if hasattr(e, "read") else str(e)
        telegram(f"❌ 스레드 발행 실패\n{post['id']}\n{detail}")
        raise

    post["status"] = "published"
    post["post_id"] = post_id
    post["published_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
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
