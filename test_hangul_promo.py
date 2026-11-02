"""한글폭탄 개발 일지 글 검증."""

import datetime
import json

import hangul_promo as hp
import tick
import weekly_check as wc

KST = hp.KST


def at(m, d, h, mi):
    return datetime.datetime(2026, m, d, h, mi, tzinfo=KST)


def test_all_posts_fit_and_are_not_auto_reply_targets():
    for p in hp.POSTS:
        t = hp.body(p)
        assert t and len(t) <= hp.LIMIT, p["key"]
        assert "구 이름 남겨줘" not in t          # 댓글은 사람이 단다
        assert "댓글" in "\n".join(t.splitlines()[-3:])   # 끝에 댓글 요청이 하나 있어야 한다


def test_schedule_is_tue_thu_at_1807():
    assert all(p["date"].weekday() in (1, 3) for p in hp.POSTS)
    assert hp.due_post(at(11, 3, 18, 6), []) is None
    assert hp.due_post(at(11, 3, 18, 7), [])["key"] == "launch"
    assert hp.due_post(at(11, 3, 19, 0), [{"id": "hangul-launch"}]) is None
    assert hp.due_post(at(11, 4, 18, 7), []) is None


def test_feedback_post_falls_back_instead_of_inventing():
    p = next(p for p in hp.POSTS if p.get("feedback"))
    assert p["text"] is None and hp.body(p) == p["fallback"]


def test_night_slot_skipped_on_hangul_day_only():
    pub = at(11, 3, 18, 8).astimezone(datetime.timezone.utc).isoformat()
    q = [{"id": "hangul-launch", "status": "published", "published_at": pub}]
    assert tick.due_slot_start(q, at(11, 3, 21, 7)) is None
    assert tick.due_slot_start(q, at(11, 4, 21, 7)) is not None


def test_weekly_check_ignores_hangul_posts():
    pub = at(11, 5, 18, 8).astimezone(datetime.timezone.utc).isoformat()
    q = [{"id": "hangul-core", "status": "published", "published_at": pub, "insights": {"views": 99999}}]
    assert wc.rows(q) == []


def test_collect_keeps_text_only_and_once_a_day(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "COMMENTS", tmp_path / "c.json")
    qf = tmp_path / "q.json"
    qf.write_text(json.dumps([{"id": "hangul-launch", "post_id": "1"}]), encoding="utf-8")
    monkeypatch.setattr(hp, "QUEUE", qf)
    calls = []

    def fetch(mid, token):
        calls.append(mid)
        return [{"username": "someone", "text": "재밌어요"}, {"username": "gzclab", "text": "고마워"}]

    d = hp.collect(at(11, 4, 10, 0), "t", fetch)
    assert d["hangul-launch"] == ["재밌어요"]
    hp.collect(at(11, 4, 12, 0), "t", fetch)
    assert calls == ["1"]
