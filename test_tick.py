"""tick.py의 시각 판단만 검증한다. 발행·답글 자체는 각 모듈 테스트가 이미 덮는다."""

import datetime

import tick

KST = tick.KST


def at(kst_str):
    return datetime.datetime.fromisoformat(kst_str).replace(tzinfo=KST).astimezone(
        datetime.timezone.utc
    )


def q(*published_kst, status="pending", prefix="top5"):
    items = [{"id": f"{prefix}-a", "status": status}]
    for i, t in enumerate(published_kst):
        items.append(
            {
                "id": f"{prefix}-{i}",
                "status": "published",
                "published_at": at(t).isoformat(),
            }
        )
    return items


def test_slots():
    # 슬롯 전에는 아무것도 안 나간다.
    assert tick.due_slot_start(q(), at("2026-09-30T06:00")) is None
    # 슬롯 시각이 지났고 그 뒤 발행이 없으면 나간다.
    assert tick.due_slot_start(q(), at("2026-09-30T07:07")) is not None
    assert tick.due_slot_start(q(), at("2026-09-30T11:00")) is not None
    # 같은 슬롯에서 이미 나갔으면 다시 안 나간다 — 5분 루프가 슬롯을 도배하지 않는다.
    assert tick.due_slot_start(q("2026-09-30T07:09"), at("2026-09-30T11:00")) is None
    # 다음 슬롯이 오면 다시 나간다.
    assert tick.due_slot_start(q("2026-09-30T07:09"), at("2026-09-30T12:07")) is not None
    # picks 글은 제 시각에 따로 나가므로 슬롯 발행을 대신하지 않는다.
    assert (
        tick.due_slot_start(q("2026-09-30T21:30", prefix="picks"), at("2026-09-30T21:40"))
        is not None
    )
    # band 글도 같다. 14:07에 나간 게 12:07 슬롯을 먹으면 그날 pm 글이 사라진다.
    assert (
        tick.due_slot_start(q("2026-09-30T14:07", prefix="band"), at("2026-09-30T14:30"))
        is not None
    )


def test_weekly_draw():
    sat_late = at("2026-10-03T23:10")   # 토 23:10
    sun_morning = at("2026-10-04T05:00")
    sun_noon = at("2026-10-04T12:30")
    draw = tick.gen_draw_post.latest_draw(sat_late.astimezone(KST).date())

    assert tick.weekly_draw_due([], sat_late)
    assert tick.weekly_draw_due([], sun_morning)
    # 창 밖: 추첨 전 토요일 낮, 일요일 오후
    assert not tick.weekly_draw_due([], at("2026-10-03T14:00"))
    assert not tick.weekly_draw_due([], sun_noon)
    # 이미 큐에 들어왔으면 API를 더 부르지 않는다.
    assert not tick.weekly_draw_due([{"id": f"draw-{draw}"}], sat_late)


if __name__ == "__main__":
    test_slots()
    test_weekly_draw()
    print("PASS test_tick.py")
