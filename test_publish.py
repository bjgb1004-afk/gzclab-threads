"""Self-check: run `python test_publish.py`. No network, no framework."""

import json
import pathlib
import tempfile

import publish

publish.TOKEN = "fake"


def run_once(queue_items):
    tmp = pathlib.Path(tempfile.mkdtemp()) / "queue.json"
    tmp.write_text(json.dumps(queue_items, ensure_ascii=False), encoding="utf-8")
    publish.QUEUE = tmp

    calls = []
    publish.publish = lambda text, reply_to=None: calls.append((text, reply_to)) or "id-1"
    publish.telegram = lambda text: calls.append(("telegram", text))

    code = publish.main()
    return code, calls, json.loads(tmp.read_text(encoding="utf-8"))


# link present -> body post, then reply carrying a lead line + the link
code, calls, queue = run_once(
    [
        {"id": "a", "status": "published", "text": "old"},
        {"id": "b", "status": "pending", "text": "본문", "link": "https://x"},
        {"id": "c", "status": "pending", "text": "다음"},
    ]
)
assert code == 0, code
assert calls[0] == ("본문", None), calls
assert calls[1] == (f"{publish.REPLY_LINES[1]}\nhttps://x", "id-1"), calls  # published 1건 -> 인덱스 1
assert queue[1]["status"] == "published" and queue[1]["post_id"] == "id-1", queue
assert queue[2]["status"] == "pending", "only one post per run"

# per-post reply overrides the rotation
code, calls, _ = run_once([{"id": "a", "status": "pending", "text": "본문", "link": "https://x", "reply": "직접 쓴 멘트"}])
assert calls[1] == ("직접 쓴 멘트\nhttps://x", "id-1"), calls

# no link -> no reply
code, calls, _ = run_once([{"id": "a", "status": "pending", "text": "링크없음"}])
assert code == 0
assert len([c for c in calls if c[0] != "telegram"]) == 1, calls

# slot empty -> pick a different format from the last published, not the queue head
publish.current_slot = lambda: "night"  # night 글이 없는 큐 -> fallback 경로로 들어간다
code, calls, _ = run_once(
    [
        {"id": "top5-a", "status": "published", "text": "어제", "published_at": "2026-09-23T22:07:00+00:00"},
        {"id": "top5-b", "status": "pending", "slot": "am", "text": "또 TOP5"},
        {"id": "talk-1", "status": "pending", "slot": "pm", "text": "잡담"},
    ]
)
assert calls[0][0] == "잡담", calls  # 슬롯이 비어도 TOP5 연속은 피한다


# empty queue -> non-zero exit and a warning
code, calls, _ = run_once([{"id": "a", "status": "published", "text": "done"}])
assert code == 1
assert any(c[0] == "telegram" and "큐가 비었" in c[1] for c in calls), calls

print("ok")
