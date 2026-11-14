import datetime

import app_features as af
import auto_reply

KST = af.KST


def at(d, h, m, mon=11):
    return datetime.datetime(2026, mon, d, h, m, tzinfo=KST)


def test_daily_14_days_no_gap_and_fit():
    days = [p["date"] for p in af.POSTS]
    assert days == [days[0] + datetime.timedelta(i) for i in range(len(days))] and len(days) == 14
    for p in af.POSTS:
        assert len(p["text"]) <= af.LIMIT, p["key"]
        assert "?" in p["text"].splitlines()[-1] or "댓글" in p["text"].splitlines()[-1], p["key"]


def test_due_at_1207_once():
    assert af.due_post(at(15, 12, 6), []) is None
    assert af.due_post(at(15, 12, 7), [])["key"] == "map"
    assert af.due_post(at(15, 13, 0), [{"id": "feature-map"}]) is None


def test_map_and_ranking_get_district_auto_reply():
    now = datetime.datetime(2026, 11, 16, 5, 0, tzinfo=datetime.timezone.utc)
    q = [{"id": f"feature-{p['key']}", "status": "published", "text": p["text"], "post_id": "x",
          "published_at": now.isoformat()} for p in af.POSTS[:3]]
    ids = [p["id"] for p in auto_reply.targets(q, now)]
    assert ids == ["feature-map", "feature-ranking"]
