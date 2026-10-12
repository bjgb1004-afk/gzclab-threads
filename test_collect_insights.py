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

# published before published_at tracking existed (old data, field missing) -> skipped, not crashed
calls, _ = run_once([{"id": "a", "status": "published", "post_id": "m1"}])
assert calls == [], calls

# published <24h ago -> skipped, metrics not settled yet
import datetime
recent = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
calls, _ = run_once([{"id": "a", "status": "published", "post_id": "m1", "published_at": recent}])
assert calls == [], calls

# fetch fails -> alerted via telegram, not silently swallowed, insights left unset but attempt counted
tmp = pathlib.Path(tempfile.mkdtemp()) / "queue.json"
tmp.write_text(json.dumps([{"id": "a", "status": "published", "post_id": "m1", "published_at": OLD}]), encoding="utf-8")
ci.QUEUE = tmp
alerts = []
ci.telegram = lambda text: alerts.append(text)
ci.fetch = lambda media_id, token: (_ for _ in ()).throw(RuntimeError("boom"))
ci.main()
queue = json.loads(tmp.read_text(encoding="utf-8"))
assert "insights" not in queue[0] and queue[0]["insights_attempts"] == 1, queue
assert alerts and "insights 수집 실패" in alerts[0], alerts

# 2026-10-13: 글이 삭제돼서(or insights 미지원) fetch가 영원히 같은 이유로 실패하던 사례
# (talk-pm-05, 6일간 매 틱 반복 알림). MAX_ATTEMPTS번째엔 포기하고 더는 건드리지 않는다.
alerts.clear()
for _ in range(ci.MAX_ATTEMPTS):
    ci.main()
queue = json.loads(tmp.read_text(encoding="utf-8"))
assert queue[0]["insights"] == {"error": "boom"}, queue
assert len(alerts) == ci.MAX_ATTEMPTS - 1, alerts  # 첫 시도는 위에서 이미 셌으니 여기선 2번만 더 온다
assert "포기" in alerts[-1], alerts

# 포기한 뒤로는 더 이상 fetch를 부르지 않는다(조용히 영구 제외)
ci.fetch = lambda media_id, token: (_ for _ in ()).throw(AssertionError("다시 불리면 안 됨"))
ci.main()

print("ok")
