"""Self-check: run `python test_instagram.py`. No network, no framework."""

import instagram

# ---------- 2단계 발행: 컨테이너 → 발행 ----------
calls = []


def fake_api(path, params, method="POST"):
    calls.append((path, params))
    if path.endswith("/media"):
        return {"id": "container-1"}
    return {"id": "post-1"}


instagram.api = fake_api
instagram.time.sleep = lambda s: None

post_id = instagram.publish_image("https://x/y.jpg", "본문", user_id="123", token="t")
assert post_id == "post-1", post_id
assert calls[0][0] == "123/media" and calls[0][1]["image_url"] == "https://x/y.jpg"
assert calls[1][0] == "123/media_publish" and calls[1][1]["creation_id"] == "container-1"

# 토큰이나 계정이 비면 조용히 실패하지 말고 바로 죽어야 한다
try:
    instagram.publish_image("https://x/y.jpg", "본문", user_id="", token="")
    raise AssertionError("빈 자격증명인데 통과했다")
except RuntimeError as e:
    assert "IG_USER_ID" in str(e)

# ---------- 캡션 ----------
cap = instagram.caption(["첫 줄", "둘째 줄"])
assert cap.startswith("첫 줄"), cap
assert instagram.LINK_LINE in cap, "바이오 링크 안내가 빠지면 유입이 0이 된다"
assert "http" not in cap, "캡션 링크는 클릭이 안 되므로 주소를 적지 않는다"
assert cap.endswith(instagram.TAGS)

try:
    instagram.caption(["가" * 2300])
    raise AssertionError("한도를 넘겼는데 통과했다")
except RuntimeError as e:
    assert "한도" in str(e)

# 글에 쓰면 안 되는 표현은 캡션에도 쓰면 안 된다(스토어 심사 기준과 같은 선)
for banned in ("예측", "적중률", "확률 높"):
    assert banned not in cap, banned

print("ok")
