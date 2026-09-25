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

print("ok")
