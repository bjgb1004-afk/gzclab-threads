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


# link present -> body post, then reply carrying the link
code, calls, queue = run_once(
    [
        {"id": "a", "status": "published", "text": "old"},
        {"id": "b", "status": "pending", "text": "본문", "link": "https://x"},
        {"id": "c", "status": "pending", "text": "다음"},
    ]
)
assert code == 0, code
assert calls[0] == ("본문", None), calls
assert calls[1] == ("https://x", "id-1"), calls
assert queue[1]["status"] == "published" and queue[1]["post_id"] == "id-1", queue
assert queue[2]["status"] == "pending", "only one post per run"

# no link -> no reply
code, calls, _ = run_once([{"id": "a", "status": "pending", "text": "링크없음"}])
assert code == 0
assert len([c for c in calls if c[0] != "telegram"]) == 1, calls

# empty queue -> non-zero exit and a warning
code, calls, _ = run_once([{"id": "a", "status": "published", "text": "done"}])
assert code == 1
assert any(c[0] == "telegram" and "큐가 비었" in c[1] for c in calls), calls

print("ok")
