"""Self-check: run `python test_collect_insights.py`. No network, no framework."""

import json
import pathlib
import tempfile

import collect_insights as ci

ci.TOKEN = "fake"


def run_once(queue_items, fetch_return=None):
    tmp = pathlib.Path(tempfile.mkdtemp()) / "queue.json"
    tmp.write_text(json.dumps(queue_items, ensure_ascii=False), encoding="utf-8")
    ci.QUEUE = tmp

    calls = []
    ci.fetch = lambda media_id, token: calls.append(media_id) or (fetch_return or {"views": 10})

    ci.main()
    return calls, json.loads(tmp.read_text(encoding="utf-8"))


OLD = "2020-01-01T00:00:00+00:00"

# published >=24h ago, no insights yet -> fetched and recorded
calls, queue = run_once([{"id": "a", "status": "published", "post_id": "m1", "published_at": OLD}])
assert calls == ["m1"], calls
assert queue[0]["insights"] == {"views": 10}, queue

# already has insights -> not re-fetched
calls, _ = run_once([{"id": "a", "status": "published", "post_id": "m1", "published_at": OLD, "insights": {"views": 5}}])
assert calls == [], calls

# pending (no post_id) -> skipped
calls, _ = run_once([{"id": "a", "status": "pending", "published_at": OLD}])
assert calls == [], calls

# published <24h ago -> skipped, metrics not settled yet
import datetime
recent = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
calls, _ = run_once([{"id": "a", "status": "published", "post_id": "m1", "published_at": recent}])
assert calls == [], calls

# fetch fails -> alerted via telegram, not silently swallowed, insights left unset
tmp = pathlib.Path(tempfile.mkdtemp()) / "queue.json"
tmp.write_text(json.dumps([{"id": "a", "status": "published", "post_id": "m1", "published_at": OLD}]), encoding="utf-8")
ci.QUEUE = tmp
alerts = []
ci.telegram = lambda text: alerts.append(text)
ci.fetch = lambda media_id, token: (_ for _ in ()).throw(RuntimeError("boom"))
ci.main()
queue = json.loads(tmp.read_text(encoding="utf-8"))
assert "insights" not in queue[0], queue
assert alerts and "insights 수집 실패" in alerts[0], alerts

print("ok")
