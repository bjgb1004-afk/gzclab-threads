"""Self-check: run `python test_gen_posts.py`. No network, no framework."""

import datetime
import json
import pathlib
import tempfile

import gen_posts as gp

# 가짜 회차. 실제 데이터 없이 모든 틀이 도는지만 본다.
DRAWS = [
    {"no": i, "numbers": sorted({(i * 7 + k * 5) % 45 + 1 for k in range(6)} | {1, 2, 3, 4, 5, 6})[:6],
     "bonus": (i % 45) + 1,
     "prizes": {1: 1_000_000_000 + i, 2: 50_000_000, 3: 1_000_000, 4: 50_000, 5: 5_000}}
    for i in range(1, 400)
]

DAY = datetime.date(2026, 10, 3)

# ---------- 여덟 틀이 전부 500자 안에 들어오고 규칙을 지킨다 ----------
seen_makers = set()
for i in range(8):           # 4일 × 2슬롯 = 틀 8개를 한 바퀴 돈다
    day = DAY + datetime.timedelta(days=i // 2)
    slot = gp.SLOTS[i % 2]
    post = gp.build(day, slot, DRAWS)
    seen_makers.add(post["text"].split("\n", 1)[0])
    assert post["id"] == f"auto-{day}-{slot}"
    assert post["slot"] == slot
    assert len(post["text"]) <= gp.LIMIT, (post["id"], len(post["text"]))
    assert "팔로우" in post["text"].split("\n\n")[1], "둘째 줄은 팔로우 유도여야 한다"
    # "나올 차례"는 금지어로 두지 않는다 — t_cold가 그 통념을 부정하는 문장에 쓴다.
    for banned in ("예측", "적중", "확률 높", "잘 나올"):
        assert banned not in post["text"], (post["id"], banned)

assert len(seen_makers) == 8, f"8슬롯 안에 같은 틀이 두 번 나왔다: {len(seen_makers)}"

# 같은 날·슬롯은 언제 불러도 같은 글 (발행 전후로 글이 바뀌면 안 된다)
assert gp.build(DAY, "pm", DRAWS) == gp.build(DAY, "pm", DRAWS)
assert gp.build(DAY, "pm", DRAWS)["text"] != gp.build(DAY, "night", DRAWS)["text"]

# 번호 답글을 약속하는 글에는 reply_mode가 붙어야 한다 — 없으면 auto_reply가 안 집는다
promised = [gp.build(DAY + datetime.timedelta(days=d), s, DRAWS)
            for d in range(8) for s in gp.SLOTS]
for p in promised:
    if "댓글에 남겨봐" in p["text"]:
        assert p.get("reply_mode") == "replay", p["id"]
        assert "4시간" in p["text"], "4시간 안내 없이 약속하면 못 지킨다"

# 링크는 전부 붙지도, 하나도 안 붙지도 않아야 한다(광고 계정으로 읽히지 않게)
linked = sum(1 for p in promised if p.get("link"))
assert 0 < linked < len(promised), linked

# ---------- 큐 채우기 ----------
with tempfile.TemporaryDirectory() as tmp:
    q = pathlib.Path(tmp) / "queue.json"
    now = datetime.datetime(2026, 10, 3, 5, 0, tzinfo=datetime.timezone.utc)

    # 손으로 쓴 글이 넉넉하면 찍어내지 않는다
    full = [{"id": f"talk-{i}", "status": "pending", "slot": s}
            for s in gp.SLOTS for i in range(gp.KEEP_PENDING)]
    q.write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    assert gp.top_up(now, queue_path=q, draws=DRAWS) == []

    # 마르면 채운다
    q.write_text(json.dumps([{"id": "talk-0", "status": "pending", "slot": "pm"}],
                            ensure_ascii=False), encoding="utf-8")
    added = gp.top_up(now, days=2, queue_path=q, draws=DRAWS)
    assert len(added) == 4, [p["id"] for p in added]          # 2일 × 2슬롯

    # 두 번 불러도 같은 글이 또 들어가지 않는다 (5분마다 불린다)
    assert gp.top_up(now, days=2, queue_path=q, draws=DRAWS) == []
    saved = json.loads(q.read_text(encoding="utf-8"))
    assert len({p["id"] for p in saved}) == len(saved), "id가 겹쳤다"

    # ---------- 아침 지역 글 재활용 ----------
    am = [{"id": f"top5-{i}", "status": st, "slot": "am"}
          for i, st in enumerate(["published", "published", "skipped", "pending"])]
    q.write_text(json.dumps(am, ensure_ascii=False), encoding="utf-8")
    assert gp.recycle(q) == [], "pending이 남아 있으면 건드리지 않는다"

    am[-1]["status"] = "published"
    q.write_text(json.dumps(am, ensure_ascii=False), encoding="utf-8")
    again = gp.recycle(q)
    assert len(again) == 3, [p["id"] for p in again]          # skipped 1편은 그대로
    back = json.loads(q.read_text(encoding="utf-8"))
    assert [p["status"] for p in back] == ["pending", "pending", "skipped", "pending"]
    assert gp.recycle(q) == [], "되돌린 직후엔 다시 돌리지 않는다"

print("ok")
