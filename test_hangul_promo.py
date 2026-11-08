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
        if p.get("done"):
            continue
        assert t and len(t) <= hp.LIMIT, p["key"]
        assert "구 이름 남겨줘" not in t          # 댓글은 사람이 단다
        tail = "\n".join(t.replace(hp.TAG, "").splitlines()[-3:])
        assert "?" in tail or "댓글" in tail, p["key"]   # 끝에 대화를 여는 질문이 있어야 한다


def test_schedule_is_daily_1907_for_30_days():
    live = [p for p in hp.POSTS if hp.body(p)]
    assert len(live) == 30
    days = [p["date"] for p in live]
    assert days == [days[0] + datetime.timedelta(i) for i in range(30)]   # 빠진 날 없이 매일
    assert hp.due_post(at(11, 6, 19, 6), []) is None
    assert hp.due_post(at(11, 6, 19, 7), [])["key"] == "d01-charge"
    assert hp.due_post(at(11, 6, 20, 0), [{"id": "hangul-d01-charge"}]) is None
    assert hp.due_post(at(11, 3, 19, 7), []) is None          # 이미 나간 날은 다시 안 고른다


def test_one_topic_tag_per_post():
    for p in hp.POSTS:
        t = hp.body(p)
        if t:
            assert t.count("#") == 1 and t.endswith("#한글게임")


def test_no_pm_or_night_slot_after_chatter_stopped():
    """잡담 글을 끈 뒤(2026-11-08) 슬롯은 아침 하나. 아침 글이 나갔으면 점심·밤엔 아무것도 안 나간다."""
    pub = at(11, 11, 9, 9).astimezone(datetime.timezone.utc).isoformat()
    q = [{"id": "top5-x", "status": "published", "published_at": pub}]
    assert tick.due_slot_start(q, at(11, 11, 12, 7)) is None
    assert tick.due_slot_start(q, at(11, 11, 21, 7)) is None


def test_feedback_post_falls_back_instead_of_inventing():
    p = next(p for p in hp.POSTS if p.get("feedback"))
    assert p["text"] is None and hp.body(p) == p["fallback"] + hp.TAG


def test_night_slot_skipped_on_hangul_day_only():
    pub = at(11, 6, 19, 8).astimezone(datetime.timezone.utc).isoformat()
    q = [{"id": "hangul-d01-charge", "status": "published", "published_at": pub}]
    assert tick.due_slot_start(q, at(11, 6, 21, 7)) is None
    assert tick.due_slot_start(q, at(11, 7, 21, 7)) is not None


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
