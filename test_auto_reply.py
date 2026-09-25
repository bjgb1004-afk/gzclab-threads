"""Self-check: run `python test_auto_reply.py`. No network, no framework."""

import auto_reply

KEYS = ["서울 노원구", "서울 중구", "부산 중구", "대구 중구", "경기 성남시"]
KEYS3 = ["경기 용인시 기흥구", "경기 용인시 수지구", "경기 용인시 처인구", "세종시"]

# 구 이름만
assert auto_reply.match("노원구", KEYS) == ("hit", "서울 노원구")
# 시도까지
assert auto_reply.match("서울 노원구요", KEYS) == ("hit", "서울 노원구")
# 붙여 쓴 경우
assert auto_reply.match("서울노원구", KEYS) == ("hit", "서울 노원구")
# 접미사 뗀 축약
assert auto_reply.match("노원", KEYS) == ("hit", "서울 노원구")
# 문장 속에 섞여도
assert auto_reply.match("저 노원구 사는데 궁금해요 ㅋㅋ", KEYS) == ("hit", "서울 노원구")
# 여러 시도에 있는 이름 -> 전체 키를 선택지로 돌려준다
assert auto_reply.match("중구", KEYS) == ("ambiguous", ["대구 중구", "부산 중구", "서울 중구"])
# 같은 시 아래 여러 구
assert auto_reply.match("용인", KEYS3) == (
    "ambiguous", ["경기 용인시 기흥구", "경기 용인시 수지구", "경기 용인시 처인구"])
assert auto_reply.match("기흥구", KEYS3) == ("hit", "경기 용인시 기흥구")
# 시도가 곧 키인 세종
assert auto_reply.match("세종시 궁금", KEYS3) == ("hit", "세종시")
# 시도를 함께 말하면 모호하지 않다
assert auto_reply.match("부산 중구", KEYS) == ("hit", "부산 중구")
# 광역만
assert auto_reply.match("서울", KEYS) == ("need_gu", "서울")
# 지역명 없음
assert auto_reply.match("ㅋㅋㅋ", KEYS) == (None, None)
assert auto_reply.match("여기 가봤어요", KEYS) == (None, None)

REPLIES = {"서울 노원구": "1. 스파 (상계동) — 1등 52회\n\n1위가 2위의 6배임."}

# 확정 -> 닉을 부르고 본문을 붙인다
msg = auto_reply.compose("hit", "서울 노원구", "chloekim83", REPLIES, True)
assert msg.startswith("chloekim83아 노원구 1등 많이 나온 집 뽑아왔어!"), msg
assert "1. 스파 (상계동) — 1등 52회" in msg, msg
assert "play.google.com" not in msg, "답글에는 링크를 넣지 않는다"

# 동명이구 -> 되묻기. 선택지를 그대로 보여준다
msg = auto_reply.compose("ambiguous", ["대구 중구", "부산 중구", "서울 중구"], "u1", REPLIES, True)
assert "서울 중구" in msg and "부산 중구" in msg and "대구 중구" in msg, msg

# 광역만 -> 되묻기
msg = auto_reply.compose("need_gu", "서울", "u1", REPLIES, True)
assert "구" in msg, msg

# 되묻기 금지 상황에서는 되묻지 않는다
assert auto_reply.compose("ambiguous", ["서울 중구", "부산 중구"], "u1", REPLIES, False) is None
assert auto_reply.compose("need_gu", "서울", "u1", REPLIES, False) is None
# 확정은 되묻기 금지와 무관하게 답한다
assert auto_reply.compose("hit", "서울 노원구", "u1", REPLIES, False) is not None

# 매칭 실패 -> 침묵
assert auto_reply.compose(None, None, "u1", REPLIES, True) is None
# 구운 데이터에 없는 구 -> 침묵
assert auto_reply.compose("hit", "경기 성남시 분당구", "u1", REPLIES, True) is None

# conversation 응답 모양: 내 글(root) 아래 댓글들, 그 아래 내 답글들
ITEMS = [
    {"id": "c1", "username": "u1", "text": "노원구", "replied_to": {"id": "root"}},
    {"id": "r1", "username": "gzclab", "text": "이미 답함", "replied_to": {"id": "c1"}},
    {"id": "c2", "username": "u2", "text": "중구", "replied_to": {"id": "root"}},
    {"id": "c3", "username": "gzclab", "text": "내 링크 답글", "replied_to": {"id": "root"}},
    {"id": "c4", "username": "u3", "text": "몰라", "replied_to": {"id": "q1"}},
]
MY_IDS = {"r1", "c3", "q1"}

picked = auto_reply.pick(ITEMS, MY_IDS)
ids = [i["id"] for i, _ in picked]
assert "c1" not in ids, "이미 내 답글이 달린 댓글은 건너뛴다"
assert "c3" not in ids, "내 댓글은 건너뛴다"
assert "c2" in ids, ids
assert "c4" in ids, ids

flags = {i["id"]: ok for i, ok in picked}
assert flags["c2"] is True, "일반 댓글에는 되묻기 허용"
assert flags["c4"] is False, "내 답글에 달린 댓글에는 되묻지 않는다"

import datetime

NOW = datetime.datetime(2026, 9, 25, tzinfo=datetime.timezone.utc)
QUEUE = [
    {"id": "top5-a", "status": "published", "post_id": "1",
     "text": "...댓글에 구 이름 남겨줘. 다음 글에 올림.",
     "published_at": "2026-09-24T00:00:00+00:00"},
    {"id": "top5-old", "status": "published", "post_id": "2",
     "text": "...댓글에 구 이름 남겨줘.",
     "published_at": "2026-09-01T00:00:00+00:00"},
    {"id": "talk-a", "status": "published", "post_id": "3",
     "text": "...여기 가본 집 있음?",
     "published_at": "2026-09-24T00:00:00+00:00"},
    {"id": "top5-b", "status": "pending", "text": "...댓글에 구 이름 남겨줘."},
]
got = [p["id"] for p in auto_reply.targets(QUEUE, NOW)]
assert got == ["top5-a"], got

import json as _json
import pathlib as _pathlib
import tempfile

import publish

publish.TOKEN = "fake"  # main()이 conversation()에 넘기는 값. 네트워크는 타지 않는다.

tmp = _pathlib.Path(tempfile.mkdtemp())
(tmp / "queue.json").write_text(_json.dumps([
    {"id": "top5-a", "status": "published", "post_id": "m1",
     "text": "...댓글에 구 이름 남겨줘.",
     "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
]), encoding="utf-8")
(tmp / "district_replies.json").write_text(
    _json.dumps({"서울 노원구": "1. 스파 (상계동) 1등 52회"}), encoding="utf-8"
)
auto_reply.HERE = tmp
auto_reply.REPLIES = tmp / "district_replies.json"

TODAY = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
auto_reply.conversation = lambda media_id, token: [
    {"id": "c1", "username": "u1", "text": "노원구", "replied_to": {"id": "m1"}, "timestamp": TODAY},
    {"id": "c2", "username": "u2", "text": "ㅋㅋ", "replied_to": {"id": "m1"}, "timestamp": TODAY},
]
auto_reply.telegram = lambda text: None
posted = []
auto_reply.send = lambda text, reply_to: posted.append((text, reply_to)) or "new-id"

assert auto_reply.main() == 0
assert len(posted) == 1, posted  # 지역명 있는 댓글에만 답한다
assert posted[0][1] == "c1", posted
assert "노원구" in posted[0][0], posted

# 하루 상한: 오늘 내가 단 답글이 DAILY_CAP 이상이면 멈춘다
posted.clear()
auto_reply.conversation = lambda media_id, token: (
    [{"id": f"mine{i}", "username": "gzclab", "text": "x", "replied_to": {"id": "m1"}, "timestamp": TODAY}
     for i in range(auto_reply.DAILY_CAP)]
    + [{"id": "c9", "username": "u9", "text": "노원구", "replied_to": {"id": "m1"}, "timestamp": TODAY}]
)
assert auto_reply.main() == 0
assert posted == [], "상한에 걸리면 답글을 달지 않는다"

print("ok")
