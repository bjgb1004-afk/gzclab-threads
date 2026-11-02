"""수요일 중간 점검 글 검증."""

import datetime

import lotto_gen as g
import midweek as mw
import tick

KST = g.KST
STATS = {"latest": [16, 18, 27, 36, 38, 42], "carry_rate": 65}


def at(day, h, m, mon=11):
    return datetime.datetime(2026, mon, day, h, m, tzinfo=KST)


def post(draw, day, nums):
    return {"id": f"picks-{draw}-{day}", "text": "제목\n이번 주 15개: " + " ".join(f"{n:02d}" for n in nums) + "\n끝"}


A = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
B = [3, 5, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]


def test_week_sets_reads_fifteen_lists_only():
    q = [post(1249, "mon", A), post(1249, "tue", B), {"id": "picks-1249-wed", "text": "5게임 형식"}, post(1248, "mon", A)]
    assert [d for d, _ in mw.week_sets(q, 1249)] == ["mon", "tue"]


def test_overlap_needs_two_posts():
    assert mw.overlap([("mon", set(A))]) is None
    assert mw.overlap([("mon", set(A)), ("tue", set(B))]) == [3, 5, 15]


def test_post_has_hook_ask_and_stays_in_limit():
    t = mw.build_post(1249, STATS, [("mon", set(A)), ("tue", set(B))])
    assert t.splitlines()[0] == "1249회 번호 중간 점검"
    assert "구 이름 남겨줘" not in t          # combo 모드: 지역 질문이 아니다
    assert "03 · 05 · 15" in t and "월·화" in t
    assert len(t) <= mw.LIMIT


def test_post_without_overlap_data_skips_that_block():
    t = mw.build_post(1249, STATS, [("mon", set(A))])
    assert "다 같이 고른" not in t


def test_due_only_wednesday_evening():
    assert not mw.due(at(4, 18, 6))           # 수 18:06
    assert mw.due(at(4, 18, 7))
    assert not mw.due(at(5, 19, 0))           # 목
    assert not mw.due(at(3, 19, 0))           # 화


def test_wednesday_night_slot_is_skipped_once_midweek_posted():
    """하루 글 수 유지: 수요일 밤 슬롯 글을 이 글이 대신한다."""
    now = at(4, 21, 7)
    mid = {"id": "picks-1249-mid", "status": "published",
           "published_at": at(4, 18, 8).astimezone(datetime.timezone.utc).isoformat()}
    assert tick.due_slot_start([mid], now) is None
    assert tick.due_slot_start([], now) is not None            # 안 나갔으면 평소대로
    other = {"id": "picks-1249-mid", "status": "published",
             "published_at": at(28, 18, 8, mon=10).astimezone(datetime.timezone.utc).isoformat()}
    assert tick.due_slot_start([other], now) is not None        # 지난주 글은 해당 없음
