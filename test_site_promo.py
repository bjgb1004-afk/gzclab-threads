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


def test_hjone_at_dawn_from_nov25():
    assert sp.HJONE_POSTS[0]["date"] == datetime.date(2026, 11, 25)
    assert sp.due(at(25, 5, 6), []) is None
    s, p = sp.due(at(25, 5, 7), [])
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


JOBS = {"regions": {"007001": "서울특별시", "007004": "인천광역시"}, "items": [
    {"id": "1", "sido": "007001", "org": "성동문화재단", "title": "직원 채용", "jobType": "일반정규직", "emp": "regular",
     "income": "3000만원 이상", "incomeWon": 30000000, "incomeBound": "min", "end": "2026-11-25", "url": "https://job.cleaneye.go.kr/a?idx=1"},
    {"id": "2", "sido": "007004", "org": "인천광역시서해구시설공단", "title": "시설관리", "jobType": "기간제", "emp": "contract",
     "income": "4000만원 이상", "incomeWon": 40000000, "incomeBound": "min", "end": "2026-11-25", "url": "https://job.cleaneye.go.kr/a?idx=2"},
    {"id": "3", "sido": "007001", "org": "임원", "title": "사장", "jobType": "임원", "emp": "contract",
     "income": "1억원 이상", "incomeWon": 100000000, "incomeBound": "min", "end": "2026-11-24", "url": "u"},
    {"id": "4", "sido": "007001", "org": "지난공고", "title": "x", "jobType": "일반정규직", "emp": "regular",
     "income": "3500만원 이상", "incomeWon": 35000000, "incomeBound": "min", "end": "2026-11-20", "url": "u"},
]}


def test_pick_job_closest_deadline_regular_first_and_skips_used():
    today = datetime.date(2026, 11, 25)
    assert sp.pick_job(JOBS, today)["id"] == "1"
    assert sp.pick_job(JOBS, today, {"1"})["id"] == "2"
    assert sp.pick_job(JOBS, today, {"1", "2"}) is None


def test_real_post_numbers_and_honest_assumptions():
    today = datetime.date(2026, 11, 25)
    t = sp.real_post(JOBS["items"][0], JOBS, today)
    assert "서울특별시 성동문화재단" in t and "오늘 마감" in t
    assert "최소 월 250만 원" in t and "시급 약 11,960원" in t and "1,640원 높음" in t
    assert "주 40시간(월 209시간)으로 잡으면" in t and "http" not in t and len(t) <= sp.LIMIT
    t2 = sp.real_post(JOBS["items"][1], JOBS, today, 1)
    assert "인천광역시 인천광역시" not in t2
    assert sp.real_link_text(JOBS["items"][0]).startswith("원문 공고\nhttps://job.cleaneye.go.kr/a?idx=1")


def _run(monkeypatch, tmp_path, now, fetch):
    qf = tmp_path / "queue.json"
    qf.write_text(json.dumps([{"id": "kstock-myreplay"}, {"id": "golmok-deulsseok"}]), encoding="utf-8")
    monkeypatch.setattr(sp, "QUEUE", qf)
    monkeypatch.setattr(sp, "fetch_jobs", fetch)
    out = {"post": [], "reply": [], "tg": []}
    monkeypatch.setattr(sp.publish, "publish",
                        lambda text, reply_to=None: out["reply" if reply_to else "post"].append(text) or "pid")
    monkeypatch.setattr(sp.publish, "telegram", lambda m: out["tg"].append(m))
    sp.run_auto(now)
    return out, json.loads(qf.read_text(encoding="utf-8"))


def test_real_day_uses_public_job_and_records_it(monkeypatch, tmp_path):
    out, q = _run(monkeypatch, tmp_path, at(25, 22, 7), lambda: JOBS)
    assert "성동문화재단" in out["post"][0] and out["reply"][0].startswith("원문 공고")
    assert q[-1]["id"] == "jobapp-convert" and q[-1]["job_id"] == "1"


def test_real_day_falls_back_to_feature_post(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("down")
    out, q = _run(monkeypatch, tmp_path, at(25, 22, 7), boom)
    assert out["post"][0].startswith("일급 100,620원") and "job_id" not in q[-1] and out["tg"]
