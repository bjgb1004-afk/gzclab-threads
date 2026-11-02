"""실험 점검 리포트 검증. 숫자 계산과 '언제 보내는가'만 본다."""

import datetime

import weekly_check as wc

KST = wc.KST
D = datetime.date


def rec(pid, day, views, likes=1, replies=0):
    t = datetime.datetime(day.year, day.month, day.day, 9, 7, tzinfo=KST).astimezone(datetime.timezone.utc)
    return {"id": pid, "status": "published", "published_at": t.isoformat(),
            "insights": {"views": views, "likes": likes, "replies": replies, "reposts": 0}}


def week(start, views, prefix="top5"):
    return [rec(f"{prefix}-x{i}", start + datetime.timedelta(i % 7), v) for i, v in enumerate(views)]


def test_not_sent_before_report_time_and_only_once():
    now = datetime.datetime(2026, 11, 11, 23, 0, tzinfo=KST)
    assert wc.run(now, queue=[], state={}, write=False) is None
    late = datetime.datetime(2026, 11, 12, 9, 8, tzinfo=KST)
    assert wc.run(late, queue=[], state={"reported": True}, write=False) is None
    assert wc.run(late, queue=[], state={}, write=False) is not None


def test_summary_excludes_top3_and_counts_per_day():
    s = wc.summarize(wc.rows(week(D(2026, 10, 28), [10000, 9000, 8000, 100, 200, 300, 400])),
                     D(2026, 10, 28), D(2026, 11, 3))
    assert s["posts"] == 7 and s["per_day"] == 1.0
    assert s["median"] == 400 and s["mean_ex_top3"] == 250


def test_verdict_needs_both_median_and_ex_top3_to_agree():
    base = {"median": 400, "mean_ex_top3": 400}
    up = {"median": 600, "mean_ex_top3": 600}
    mixed = {"median": 600, "mean_ex_top3": 380}
    assert "올랐습니다" in wc.verdict(None, base, up)
    assert "비슷합니다" in wc.verdict(None, base, mixed)
    assert "떨어졌습니다" in wc.verdict(None, base, {"median": 200, "mean_ex_top3": 200})
    assert "판단할 수 없습니다" in wc.verdict(None, base, None)


def test_report_includes_trend_and_midweek_post():
    q = (week(D(2026, 10, 21), [500] * 7) + week(D(2026, 10, 28), [400] * 7) + week(D(2026, 11, 4), [700] * 7)
         + [rec("picks-1249-mid", D(2026, 11, 4), 3000, 20, 9), rec("picks-1249-stats", D(2026, 11, 1), 4700)])
    t = wc.report_text(wc.rows(q))
    assert "picks-1249-mid 3,000회" in t and "직전 주 → 기준 주" in t and "하루 글 수" in t
