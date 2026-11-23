import datetime
import json

import auto_reply
import site_promo as sp

KST = sp.KST
UTC = datetime.timezone.utc


def at(d, h, m, mon=11):
    return datetime.datetime(2026, mon, d, h, m, tzinfo=KST)


def test_each_series_14_days_no_gap_fit_and_question():
    for series, posts in sp.POSTS.items():
        days = [p["date"] for p in posts]
        start = days[0]
        assert len(days) == 14 and days == [start + datetime.timedelta(i) for i in range(14)], series
        assert len({p["key"] for p in posts}) == 14, series
        for p in posts:
            t = sp.body(series, p)
            assert len(t) <= sp.LIMIT, (series, p["key"], len(t))
            assert "?" in p["text"].splitlines()[-1] or "줘" in p["text"].splitlines()[-1], (series, p["key"])
            assert "http" not in t and "#" not in t and t == p["text"]
            assert sp.link_text(series, p).splitlines()[-1].startswith(sp.SERIES[series]["link"])


def test_hjone_at_dawn_from_nov24():
    assert sp.HJONE_POSTS[0]["date"] == datetime.date(2026, 11, 24)
    assert sp.due(at(24, 5, 6), []) is None
    s, p = sp.due(at(24, 5, 7), [])
    assert (s, p["key"]) == ("hjone", "intro")
    assert sp.link_text(s, p).endswith("utm_campaign%3Dpromo")


def test_times_and_once_per_day():
    assert sp.due(at(23, 20, 6), []) is None
    s, p = sp.due(at(23, 20, 7), [])
    assert (s, p["key"]) == ("kstock", "intro")
    q = [{"id": "kstock-intro"}]
    assert sp.due(at(23, 21, 6), q) is None
    assert sp.due(at(23, 21, 7), q)[0] == "golmok"
    q.append({"id": "golmok-intro"})
    assert sp.due(at(23, 22, 7), q)[0] == "jobapp"
    q.append({"id": "jobapp-intro"})
    assert sp.due(at(23, 23, 59), q) is None
    # 90분 넘게 늦으면 건너뜀(루프가 끊겼다 살아나도 몰아서 안 나감)
    assert sp.due(at(23, 21, 40), []) [0] == "golmok"
    assert sp.due(at(23, 23, 40), []) is None
    # 다음 날은 다음 글
    assert sp.due(at(24, 20, 10), q)[1]["key"] == "today"


def test_missed_day_is_not_backfilled():
    assert sp.due(at(25, 20, 10), [])[1]["key"] == "13f"
    assert sp.due(datetime.datetime(2026, 12, 7, 20, 10, tzinfo=KST), []) is None


def test_gap_after_another_post(tmp_path, monkeypatch):
    now = at(28, 21, 10)  # 토요일 로또 결과 글과 겹치는 시간대
    just = (now - datetime.timedelta(minutes=5)).astimezone(UTC).isoformat()
    queue = [{"id": "kstock-room", "status": "published", "published_at": at(28, 20, 7).isoformat()},
             {"id": "picks-1252-result", "status": "published", "published_at": just}]
    qf = tmp_path / "queue.json"
    qf.write_text(json.dumps(queue), encoding="utf-8")
    monkeypatch.setattr(sp, "QUEUE", qf)
    sent = []
    replies = []
    monkeypatch.setattr(sp.publish, "publish",
                        lambda text, reply_to=None: (replies if reply_to else sent).append(text) or "pid")
    monkeypatch.setattr(sp.publish, "telegram", lambda msg: None)
    sp.run_auto(now)
    assert sent == []
    sp.run_auto(now + datetime.timedelta(minutes=15))
    assert len(sent) == 1 and "경찰과 도둑" in sent[0] and "http" not in sent[0]
    assert replies == ["골목 놀이터 바로가기\nhttps://golmok-play.gzclab.workers.dev/gyeongdo"]
    ids = [q["id"] for q in json.loads(qf.read_text(encoding="utf-8"))]
    assert ids[-1] == "golmok-gyeongdo-bots"
    sp.run_auto(now + datetime.timedelta(minutes=40))
    assert len(sent) == 1  # 같은 날 두 번 안 나감


def test_not_auto_reply_targets():
    now = at(24, 23, 0).astimezone(UTC)
    q = [{"id": f"{s}-{p['key']}", "status": "published", "text": sp.body(s, p), "post_id": "x",
          "published_at": now.isoformat()} for s, ps in sp.POSTS.items() for p in ps]
    assert auto_reply.targets(q, now) == []


def test_link_goes_in_first_reply():
    assert all(sp.publish.link_ok(f"{s}-x") for s in sp.SERIES)
