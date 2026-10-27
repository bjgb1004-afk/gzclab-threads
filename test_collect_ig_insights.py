"""collect_ig_insights.py 검증. 네트워크는 전부 가짜로 바꾼다."""

import datetime
import json
import pathlib
import tempfile

import collect_ig_insights as ci

UTC = datetime.timezone.utc


def at(hours_ago, now):
    return (now - datetime.timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def sandbox(state=None):
    tmp = pathlib.Path(tempfile.mkdtemp())
    ci.STATE = tmp / "instagram.json"
    ci.STATE.write_text(json.dumps(state or {"published": {}}, ensure_ascii=False), encoding="utf-8")
    return ci.STATE


def envelope(names):
    return {"data": [{"name": n, "values": [{"value": 10 + i}]} for i, n in enumerate(names)]}


# ---------- 거둘 대상 고르기 ----------

def test_due_waits_for_metrics_to_settle():
    now = datetime.datetime.now(UTC)
    state = {"published": {
        "fresh": {"media_id": "A", "at": at(3, now)},
        "ripe": {"media_id": "B", "at": at(25, now)},
    }}
    assert [k for k, _ in ci.due(state, now)] == ["ripe"]


def test_due_skips_already_collected():
    now = datetime.datetime.now(UTC)
    state = {"published": {
        "done": {"media_id": "A", "at": at(48, now), "insights": {"reach": 5}},
        "failed": {"media_id": "B", "at": at(48, now), "insights": {"error": "x"}},
        "todo": {"media_id": "C", "at": at(48, now)},
    }}
    assert [k for k, _ in ci.due(state, now)] == ["todo"]


def test_due_skips_entries_without_media_id():
    now = datetime.datetime.now(UTC)
    state = {"published": {"broken": {"at": at(48, now)}}}
    assert ci.due(state, now) == []


# ---------- 지표 받아오기 ----------

def test_fetch_asks_for_growth_metrics_first(monkeypatch):
    """follows·profile_visits가 우리가 알고 싶은 바로 그 숫자다."""
    asked = []

    def fake_get(path, params, token):
        asked.append(params["metric"])
        return envelope(params["metric"].split(","))

    monkeypatch.setattr(ci, "get", fake_get)
    got = ci.fetch("M1", "tok")
    assert "follows" in asked[0] and "profile_visits" in asked[0]
    assert "follows" in got and "reach" in got


def test_fetch_falls_back_to_core_when_extra_rejected(monkeypatch):
    """지표 하나가 지원 안 되면 응답 전체가 400이다. 그때도 기본 지표는 건져야 한다."""
    calls = []

    def fake_get(path, params, token):
        calls.append(params["metric"])
        if "follows" in params["metric"]:
            raise RuntimeError("HTTP 400 unsupported metric")
        return envelope(params["metric"].split(","))

    monkeypatch.setattr(ci, "get", fake_get)
    got = ci.fetch("M1", "tok")
    assert len(calls) == 2
    assert set(got) == set(ci.CORE)


def test_fetch_raises_when_core_also_fails(monkeypatch):
    monkeypatch.setattr(ci, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 400")))
    try:
        ci.fetch("M1", "tok")
    except RuntimeError:
        pass
    else:
        raise AssertionError("실패가 전달돼야 한다")


def test_fetch_omits_metrics_with_no_data(monkeypatch):
    """값이 없으면 빈 배열이 온다. 0으로 적으면 '측정했는데 0'과 구별이 안 된다."""
    def fake_get(path, params, token):
        return {"data": [{"name": "reach", "values": [{"value": 42}]},
                         {"name": "follows", "values": []}]}

    monkeypatch.setattr(ci, "get", fake_get)
    got = ci.fetch("M1", "tok")
    assert got == {"reach": 42}
    assert "follows" not in got


# ---------- 본체 ----------

def test_main_records_insights(monkeypatch):
    now = datetime.datetime.now(UTC)
    p = sandbox({"published": {"genius-2026-10-20": {"media_id": "M1", "at": at(30, now)}}})
    monkeypatch.setattr(ci, "fetch", lambda m, t: {"reach": 120, "follows": 2})
    monkeypatch.setattr(ci, "record_followers", lambda *a: False)
    ci.main("tok", now)
    saved = json.loads(p.read_text(encoding="utf-8"))["published"]["genius-2026-10-20"]
    assert saved["insights"] == {"reach": 120, "follows": 2}


def test_main_gives_up_after_max_attempts(monkeypatch):
    """삭제된 글은 영원히 같은 이유로 실패한다. 안 끊으면 5분마다 같은 알림이 온다."""
    now = datetime.datetime.now(UTC)
    p = sandbox({"published": {"x": {"media_id": "M1", "at": at(30, now)}}})
    monkeypatch.setattr(ci, "fetch", lambda m, t: (_ for _ in ()).throw(RuntimeError("HTTP 100 deleted")))
    monkeypatch.setattr(ci, "record_followers", lambda *a: False)
    notes = []
    monkeypatch.setattr(ci, "telegram", lambda t: notes.append(t))

    for _ in range(ci.MAX_ATTEMPTS):
        ci.main("tok", now)
    item = json.loads(p.read_text(encoding="utf-8"))["published"]["x"]
    assert "error" in item["insights"]
    assert len(notes) == 1  # 포기할 때 한 번만 알린다
    # 포기한 뒤에는 대상에서 빠진다
    assert ci.due(json.loads(p.read_text(encoding="utf-8")), now) == []


# ---------- 팔로워 수 ----------

def test_record_followers_once_a_day(monkeypatch):
    now = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    sandbox()
    state = ci.load()
    monkeypatch.setattr(ci, "follower_count", lambda t: (235, "gzclab"))
    assert ci.record_followers(state, "tok", now) is True
    assert ci.record_followers(state, "tok", now) is False  # 같은 날 두 번 안 적는다
    assert list(state["followers"].values()) == [235]
    # 다음 날은 적는다
    assert ci.record_followers(state, "tok", now + datetime.timedelta(days=1)) is True
    assert len(state["followers"]) == 2


def test_record_followers_uses_kst_day(monkeypatch):
    """UTC로 날짜를 세면 한국 시간 자정 전후로 하루가 어긋난다."""
    monkeypatch.setattr(ci, "follower_count", lambda t: (1, "x"))
    sandbox()
    state = ci.load()
    ci.record_followers(state, "tok", datetime.datetime(2026, 10, 27, 20, 0, tzinfo=UTC))
    assert list(state["followers"]) == ["2026-10-28"]  # KST로는 이미 28일


# ---------- 토큰 ----------

def test_error_text_hides_token(monkeypatch):
    """예외 문구가 로그와 텔레그램으로 나간다. 토큰이 섞이면 안 된다."""
    import urllib.error, io

    def boom(url, timeout=0):
        raise urllib.error.HTTPError(url, 400, "Bad", {},
                                     io.BytesIO(b'{"error":"bad token SECRETTOKEN"}'))

    monkeypatch.setattr(ci.urllib.request, "urlopen", boom)
    try:
        ci.get("me", {"fields": "id"}, "SECRETTOKEN")
    except RuntimeError as e:
        assert "SECRETTOKEN" not in str(e)
        assert "***" in str(e)
    else:
        raise AssertionError("예외가 나야 한다")
