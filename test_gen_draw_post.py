"""gen_draw_post 자체 점검. 네트워크 없이 build()와 회차 계산만 본다."""

import datetime

import gen_draw_post as g


def store(region, addr, name, shop_id="11100001", mode="자동"):
    return {"region": region, "shpAddr": addr, "shpNm": name, "ltShpId": shop_id, "atmtPsvYnTxt": mode}


def test_latest_draw_is_yesterday_on_sunday():
    # 2026-09-26(토) 추첨 = 1243회. 일요일 새벽에 돌려도 그 회차가 나와야 한다.
    assert g.latest_draw(datetime.date(2026, 9, 27)) == 1243
    assert g.latest_draw(datetime.date(2026, 9, 26)) == 1243
    assert g.latest_draw(datetime.date(2026, 9, 25)) == 1242  # 금요일 = 아직 이전 회차


def test_internet_rows_are_excluded_but_counted():
    post = g.build(1243, [
        store("서울", "서울 영등포구 영중로 2", "로또킹"),
        store("서울", "서울 강남구 테헤란로", "인터넷 복권판매사이트", g.NET_SHOP_ID),
    ])
    assert "인터넷" not in post["text"].split("\n")[4]
    assert "인터넷 1건" in post["text"]
    assert "[서울 영등포구] 로또킹" in post["text"]


def test_same_region_stays_together_and_biggest_first():
    post = g.build(1, [
        store("대전", "대전 중구 대종로", "대전로또"),
        store("경기", "경기 화성시 동탄대로", "프랜드편의점"),
        store("경기", "경기 성남시 분당구", "서현로또"),
    ])
    rows = [l for l in post["text"].split("\n") if l.startswith("[")]
    assert [r.split()[0] for r in rows] == ["[경기", "[경기", "[대전"]


def test_overflow_is_trimmed_under_limit():
    many = [store("경기", f"경기 화성시 아주긴도로이름{i}", f"아주아주긴판매점이름{i}") for i in range(40)]
    post = g.build(1, many)
    assert len(post["text"]) <= g.LIMIT
    assert "외 " in post["text"]


def test_auto_reply_can_target_the_post():
    import auto_reply

    post = g.build(1243, [store("대전", "대전 중구 대종로", "대전로또")])
    post |= {"status": "published", "post_id": "1", "published_at": "2026-09-27T00:00:00+00:00"}
    now = datetime.datetime.fromisoformat("2026-09-27T12:00:00+00:00")
    assert auto_reply.targets([post], now) == [post]


def test_no_physical_store_returns_none():
    assert g.build(1, [store("서울", "서울 강남구 테헤란로", "인터넷", g.NET_SHOP_ID)]) is None


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
