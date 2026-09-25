# 스레드 댓글 자동 답글 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "댓글에 구 이름 남겨줘" 형 발행글에 달린 댓글에서 지역명을 읽어, 그 구의 1등 판매점 TOP3를 자동 답글로 단다.

**Architecture:** 답글 문장은 로컬에서 미리 구워 `district_replies.json`으로 커밋한다(`districts.json`은 계속 비공개). GitHub Actions가 10분마다 `conversation` API로 각 글의 댓글 트리를 통째로 받아, 내 답글이 안 달린 댓글만 골라 답한다. 이미 답한 댓글 목록은 API 응답에서 그대로 읽히므로 상태 파일이 없다.

**Tech Stack:** Python 3 표준 라이브러리만 (`urllib`, `json`, `datetime`). 기존 `publish.py`의 `publish()`/`telegram()` 재사용. 프레임워크 없는 assert 자기점검.

**Spec:** `docs/superpowers/specs/2026-09-25-threads-auto-reply-design.md`

## Global Constraints

- 외부 의존성 추가 금지. 표준 라이브러리만 쓴다 (기존 `publish.py`, `collect_insights.py`와 동일)
- 답글에 Play 링크를 넣지 않는다
- 답글 본문 500자 이내 (Threads 제한)
- `districts.json`은 커밋하지 않는다 (`.gitignore`에 등록돼 있음)
- 내 계정 사용자명은 `gzclab`
- 하루 답글 상한 50건, 1회 실행 상한 10건
- 대상은 최근 7일 내 발행글
- 테스트는 네트워크를 타지 않는다. `python test_auto_reply.py`로 실행되고 마지막에 `ok`를 찍는다
- 커밋 메시지는 한글, 기존 형식(`feat:`, `fix:`, `chore:`, `docs:`)을 따른다

---

### Task 1: 답글 문장 굽기 (`bake_replies.py`)

**Files:**
- Create: `bake_replies.py`
- Create: `district_replies.json` (생성물, 커밋함)
- Read: `gen_district_posts.py:28-50` (`where`, `name`, `hook` 재사용)

**Interfaces:**
- Produces: `district_replies.json` — `{"서울 노원구": "1. 스파 (상계동) — 1등 52회\n2. ...\n\n1위가 2위의 6배임. ..."}`. 키는 `districts.json`의 키와 같은 `"<시도> <구>"` 형식. 값은 순위 3줄 + 빈 줄 + 격차 문장 한 줄. 닉네임과 인사말은 들어 있지 않다(런타임에 붙인다).

- [ ] **Step 1: 생성기를 쓴다**

`bake_replies.py`:

```python
"""districts.json -> district_replies.json. 로컬에서 가끔 돌리고 결과를 커밋한다.

Actions에는 districts.json이 없다(.gitignore). 답글에 필요한 건 완성된 문장뿐이라
미리 구워서 올린다. 새 시도를 추가했을 때만 다시 돌리면 된다.

실행: python bake_replies.py
"""

import json
import pathlib

from gen_district_posts import hook, name, where

HERE = pathlib.Path(__file__).parent
# 런타임에 "<닉>아 <구> 1등 많이 나온 집 뽑아왔어!\n\n"가 앞에 붙는다. 닉이 30자여도
# 500자를 넘지 않도록 본문은 400자로 제한한다.
BODY_LIMIT = 400


def body(stores):
    """TOP3 + 격차 한 줄. 격차 문장은 본문 글과 같은 hook()을 써서 서로 어긋나지 않게 한다."""
    lines = []
    for i, s in enumerate(stores[:3], 1):
        spot = f" ({where(s)})" if where(s) else ""
        lines.append(f"{i}. {name(s)}{spot} — 1등 {s['first']}회")
    return "\n".join(lines) + "\n\n" + hook(stores)


def main():
    districts = json.loads((HERE / "districts.json").read_text(encoding="utf-8"))
    out = {}
    for district, stores in districts.items():
        # 본문 글과 같은 기준으로 거른다. 1위가 2회짜리면 답글로 내줄 게 없다.
        if len(stores) < 3 or stores[0]["first"] < 3:
            continue
        text = body(stores)
        assert len(text) <= BODY_LIMIT, f"{district} {len(text)}자 초과"
        out[district] = text

    path = HERE / "district_replies.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(out)}개 구 저장 -> {path.name} ({path.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 돌려서 결과를 확인한다**

Run: `python bake_replies.py`
Expected: `NNN개 구 저장 -> district_replies.json (NNKB)` — 구 개수는 200 안팎, 크기는 100KB 미만.

assert가 터지면 그 구의 상호명이 비정상적으로 길다는 뜻이다. 해당 구를 출력해 확인하고, 데이터가 실제로 이상하면 `name()`을 고치지 말고 그 구만 건너뛴다(`continue`).

- [ ] **Step 3: 샘플을 눈으로 본다**

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "import json;d=json.load(open('district_replies.json',encoding='utf-8'));print(d['서울 노원구'])"
```
Expected: 순위 3줄, 빈 줄, 격차 문장 한 줄. 상호명에 열린 괄호가 남아 있지 않아야 한다.

- [ ] **Step 4: 커밋**

```bash
git add bake_replies.py district_replies.json
git commit -m "feat: 구별 답글 문장을 미리 구워 커밋한다 (Actions에는 districts.json이 없다)"
```

---

### Task 2: 지역명 매칭 (`auto_reply.py`의 `match`)

**Files:**
- Create: `auto_reply.py` (이 태스크에서는 `match`와 상수만)
- Create: `test_auto_reply.py`

**Interfaces:**
- Consumes: `district_replies.json`의 키 목록 (Task 1)
- Produces: `match(text, keys) -> (kind, value)`
  - `("hit", "서울 노원구")` — 한 곳으로 확정
  - `("ambiguous", ["대구", "부산", "서울"])` — 같은 구 이름이 여러 시도에 있음. 값은 정렬된 시도 이름 리스트
  - `("need_gu", "서울")` — 광역만 말했음
  - `(None, None)` — 지역명 없음

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_auto_reply.py`:

```python
"""Self-check: run `python test_auto_reply.py`. No network, no framework."""

import auto_reply

KEYS = ["서울 노원구", "서울 중구", "부산 중구", "대구 중구", "경기 성남시"]

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
# 여러 시도에 있는 이름
assert auto_reply.match("중구", KEYS) == ("ambiguous", ["대구", "부산", "서울"])
# 시도를 함께 말하면 모호하지 않다
assert auto_reply.match("부산 중구", KEYS) == ("hit", "부산 중구")
# 광역만
assert auto_reply.match("서울", KEYS) == ("need_gu", "서울")
# 지역명 없음
assert auto_reply.match("ㅋㅋㅋ", KEYS) == (None, None)
assert auto_reply.match("여기 가봤어요", KEYS) == (None, None)

print("ok")
```

- [ ] **Step 2: 돌려서 실패를 확인한다**

Run: `python test_auto_reply.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'auto_reply'`

- [ ] **Step 3: 최소 구현을 쓴다**

`auto_reply.py`:

```python
"""댓글에서 지역명을 읽어 그 구의 TOP3를 답글로 단다.

대상은 "댓글에 구 이름 남겨줘" 형 발행글. 이미 답한 댓글은 conversation 응답에서
바로 걸러지므로 상태 파일이 없다.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
REPLIES = HERE / "district_replies.json"
ME = "gzclab"


def match(text, keys):
    """댓글에서 지역을 고른다. ('hit', 키) / ('ambiguous', 시도들) / ('need_gu', 시도) / (None, None).

    '노원'처럼 접미사를 뗀 축약도 받는다. 다만 한 글자 축약('중구'->'중')은
    아무 문장에나 걸려서 쓰지 않는다.
    """
    # 시도까지 말한 경우가 가장 정확하다. 공백 유무를 모두 본다.
    for key in keys:
        if key in text or key.replace(" ", "") in text:
            return "hit", key

    # 구 이름(과 그 축약) -> 그 이름을 가진 키들
    by_gu = {}
    for key in keys:
        gu = key.split(" ", 1)[1]
        by_gu.setdefault(gu, []).append(key)
        short = gu[:-1]  # 노원구 -> 노원
        if len(short) >= 2:
            by_gu.setdefault(short, []).append(key)

    # 긴 이름부터 본다. '중구'보다 '노원구'가 먼저 걸려야 한다.
    for gu in sorted(by_gu, key=len, reverse=True):
        if gu in text:
            cand = by_gu[gu]
            if len(cand) == 1:
                return "hit", cand[0]
            return "ambiguous", sorted({k.split(" ", 1)[0] for k in cand})

    # 광역만 말한 경우
    for sido in sorted({k.split(" ", 1)[0] for k in keys}):
        if sido in text:
            return "need_gu", sido

    return None, None
```

- [ ] **Step 4: 돌려서 통과를 확인한다**

Run: `python test_auto_reply.py`
Expected: `ok`

`("ambiguous", [...])` 줄에서 실패하면 실제 출력값을 보고 정렬 순서를 확인한다. `sorted()`는 한글 유니코드 순이라 `["대구", "부산", "서울"]`이다.

- [ ] **Step 5: 실제 키로도 확인한다**

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "
import json, auto_reply
keys = list(json.load(open('district_replies.json', encoding='utf-8')))
for t in ['노원구','중구','서울','강남','ㅋㅋ','우리동네 해운대구도 알려줘']:
    print(t, '->', auto_reply.match(t, keys))
"
```
Expected: `노원구 -> ('hit', '서울 노원구')`, `중구 -> ('ambiguous', [...])`, `서울 -> ('need_gu', '서울')`, `ㅋㅋ -> (None, None)`, `강남 -> ('hit', '서울 강남구')`, 해운대구는 `hit`.

`강남`이 `hit`이 아니면 축약 처리에 버그가 있다.

- [ ] **Step 6: 커밋**

```bash
git add auto_reply.py test_auto_reply.py
git commit -m "feat: 댓글에서 지역명 고르기 (동명이구·광역·축약 처리)"
```

---

### Task 3: 답글 본문 만들기

**Files:**
- Modify: `auto_reply.py` (`compose` 추가)
- Modify: `test_auto_reply.py`

**Interfaces:**
- Consumes: `match()` (Task 2), `district_replies.json` (Task 1)
- Produces: `compose(kind, value, username, replies, followup_ok) -> str | None`
  - `replies`는 `district_replies.json`을 읽은 dict
  - `followup_ok`가 False면 되묻기(`ambiguous`/`need_gu`)에 `None`을 돌려준다 — 내 되묻기에 달린 댓글에 또 되묻지 않기 위한 것
  - 답할 것이 없으면 `None`

- [ ] **Step 1: 실패하는 테스트를 추가한다**

`test_auto_reply.py`의 `print("ok")` 앞에 붙인다:

```python
REPLIES = {"서울 노원구": "1. 스파 (상계동) — 1등 52회\n\n1위가 2위의 6배임."}

# 확정 -> 닉을 부르고 본문을 붙인다
msg = auto_reply.compose("hit", "서울 노원구", "chloekim83", REPLIES, True)
assert msg.startswith("chloekim83아 노원구 1등 많이 나온 집 뽑아왔어!"), msg
assert "1. 스파 (상계동) — 1등 52회" in msg, msg
assert "play.google.com" not in msg, "답글에는 링크를 넣지 않는다"

# 동명이구 -> 되묻기
msg = auto_reply.compose("ambiguous", ["대구", "부산", "서울"], "u1", REPLIES, True)
assert "서울" in msg and "부산" in msg and "대구" in msg, msg

# 광역만 -> 되묻기
msg = auto_reply.compose("need_gu", "서울", "u1", REPLIES, True)
assert "구" in msg, msg

# 되묻기 금지 상황에서는 되묻지 않는다
assert auto_reply.compose("ambiguous", ["서울", "부산"], "u1", REPLIES, False) is None
assert auto_reply.compose("need_gu", "서울", "u1", REPLIES, False) is None
# 확정은 되묻기 금지와 무관하게 답한다
assert auto_reply.compose("hit", "서울 노원구", "u1", REPLIES, False) is not None

# 매칭 실패 -> 침묵
assert auto_reply.compose(None, None, "u1", REPLIES, True) is None
# 구운 데이터에 없는 구 -> 침묵
assert auto_reply.compose("hit", "경기 성남시", "u1", REPLIES, True) is None
```

- [ ] **Step 2: 돌려서 실패를 확인한다**

Run: `python test_auto_reply.py`
Expected: FAIL — `AttributeError: module 'auto_reply' has no attribute 'compose'`

- [ ] **Step 3: 구현한다**

`auto_reply.py`의 `match` 아래에 추가:

```python
def compose(kind, value, username, replies, followup_ok):
    """답글 본문. 답할 것이 없으면 None."""
    if kind == "hit":
        body = replies.get(value)
        if not body:  # 1위가 2회짜리라 굽는 단계에서 걸러진 구
            return None
        gu = value.split(" ", 1)[1]
        return f"{username}아 {gu} 1등 많이 나온 집 뽑아왔어!\n\n{body}"
    if not followup_ok:
        return None
    if kind == "ambiguous":
        return f"{username}아 그 이름이 {'/'.join(value)}에 다 있어 ㅋㅋ 어디 말하는 거야?"
    if kind == "need_gu":
        return f"{username}아 구까지 말해주면 바로 뽑아줄게. ({value} 어느 구?)"
    return None
```

- [ ] **Step 4: 돌려서 통과를 확인한다**

Run: `python test_auto_reply.py`
Expected: `ok`

- [ ] **Step 5: 실제 데이터로 길이를 확인한다**

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "
import json, auto_reply
r = json.load(open('district_replies.json', encoding='utf-8'))
worst = max(r, key=lambda k: len(auto_reply.compose('hit', k, 'a'*30, r, True)))
m = auto_reply.compose('hit', worst, 'a'*30, r, True)
print(worst, len(m))
print(m)
"
```
Expected: 길이가 500 미만. 넘으면 Task 1의 `BODY_LIMIT`을 낮추고 다시 굽는다.

- [ ] **Step 6: 커밋**

```bash
git add auto_reply.py test_auto_reply.py
git commit -m "feat: 답글 본문 생성 (확정·되묻기·침묵)"
```

---

### Task 4: 댓글 고르기 (`pick`)

**Files:**
- Modify: `auto_reply.py` (`pick` 추가)
- Modify: `test_auto_reply.py`

**Interfaces:**
- Produces: `pick(items, my_ids) -> [(item, followup_ok)]`
  - `items`: `conversation` 응답의 `data` 배열. 각 항목은 `{"id", "username", "text", "timestamp", "replied_to": {"id"}}`
  - `my_ids`: 내가 쓴 항목의 id 집합
  - `followup_ok`: 그 댓글에 되묻기를 해도 되는지 (내 답글에 달린 댓글이면 False)

- [ ] **Step 1: 실패하는 테스트를 추가한다**

`test_auto_reply.py`의 `print("ok")` 앞에 붙인다:

```python
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
```

- [ ] **Step 2: 돌려서 실패를 확인한다**

Run: `python test_auto_reply.py`
Expected: FAIL — `AttributeError: module 'auto_reply' has no attribute 'pick'`

- [ ] **Step 3: 구현한다**

`auto_reply.py`의 `compose` 아래에 추가:

```python
def pick(items, my_ids):
    """답할 댓글만 고른다. (항목, 되묻기 허용) 목록.

    이미 답했는지는 conversation 응답만 보고 안다 — 내 답글이 그 댓글을 부모로
    달려 있으면 끝난 것이다. 그래서 상태 파일이 없다.
    """
    answered = {i.get("replied_to", {}).get("id") for i in items if i["username"] == ME}
    out = []
    for item in items:
        if item["username"] == ME or item["id"] in answered:
            continue
        # 내 되묻기에 달린 댓글에 또 되물으면 무한히 돈다. 확정일 때만 답한다.
        followup_ok = item.get("replied_to", {}).get("id") not in my_ids
        out.append((item, followup_ok))
    return out
```

- [ ] **Step 4: 돌려서 통과를 확인한다**

Run: `python test_auto_reply.py`
Expected: `ok`

- [ ] **Step 5: 커밋**

```bash
git add auto_reply.py test_auto_reply.py
git commit -m "feat: 답할 댓글 고르기 (중복·자기 댓글·되묻기 반복 방지)"
```

---

### Task 5: 대상 글 선정과 실행 (`targets`, `main`)

**Files:**
- Modify: `auto_reply.py` (import 추가, `conversation`/`targets`/`send`/`main` 추가)
- Modify: `test_auto_reply.py`

**Interfaces:**
- Consumes: `match()`, `compose()`, `pick()`, `publish.publish()`, `publish.telegram()`
- Produces:
  - `targets(queue, now) -> [post]` — 댓글을 유도한 최근 7일 내 발행글
  - `send(text, reply_to) -> str` — 답글 발행. 테스트에서 갈아끼우는 지점
  - `main() -> int`

- [ ] **Step 1: `targets` 테스트를 추가한다**

`test_auto_reply.py`의 `print("ok")` 앞에 붙인다:

```python
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
```

- [ ] **Step 2: 돌려서 실패를 확인한다**

Run: `python test_auto_reply.py`
Expected: FAIL — `AttributeError: module 'auto_reply' has no attribute 'targets'`

- [ ] **Step 3: 나머지를 구현한다**

`auto_reply.py` 상단 import를 다음으로 바꾼다:

```python
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

import publish
from publish import API, telegram
```

파일 맨 아래에 추가:

```python
DAILY_CAP = 50   # Threads 24시간 250건 중 발행분을 빼도 244건 여유. 폭주가 발행을 죽이지 않게 한다
RUN_CAP = 10     # 한 번 실행에 10건. 밀려도 10분 뒤 이어서 답한다
WINDOW_DAYS = 7  # 이보다 오래된 글의 댓글은 뒤늦게 답해도 의미 없다


def conversation(media_id, token):
    fields = "id,text,username,timestamp,replied_to"
    url = f"{API}/{media_id}/conversation?fields={fields}&access_token={urllib.parse.quote(token)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r).get("data", [])
    except urllib.error.HTTPError as e:
        # publish.py와 같은 이유로 본문을 여기서 읽는다. 안 그러면 로그에 코드만 남는다.
        raise RuntimeError(
            f"conversation {media_id} {e.code}: {e.read().decode(errors='replace')[:300]}"
        ) from None


def targets(queue, now):
    """댓글을 유도한 글 중 최근 7일 내 발행된 것."""
    cut = now - datetime.timedelta(days=WINDOW_DAYS)
    out = []
    for p in queue:
        if p.get("status") != "published" or not p.get("post_id") or not p.get("published_at"):
            continue
        if datetime.datetime.fromisoformat(p["published_at"]) < cut:
            continue
        # 지역을 물어본 글만 대상이다. 잡담 유도 글은 기계가 답할 거리가 없다.
        if "구 이름 남겨줘" in p["text"]:
            out.append(p)
    return out


def send(text, reply_to):
    """답글 발행. 테스트는 이 함수를 갈아끼운다."""
    return publish.publish(text, reply_to=reply_to)


def main():
    queue = json.loads((HERE / "queue.json").read_text(encoding="utf-8"))
    replies = json.loads(REPLIES.read_text(encoding="utf-8"))
    keys = list(replies)
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date().isoformat()

    sent = 0
    for post in targets(queue, now):
        if sent >= RUN_CAP:
            break
        try:
            items = conversation(post["post_id"], publish.TOKEN)
        except Exception as e:
            print(e, file=sys.stderr)
            telegram(f"⚠️ 댓글 조회 실패\n{post['id']}\n{e}")
            continue

        my_ids = {i["id"] for i in items if i["username"] == ME}
        # 하루 상한은 오늘 내가 이미 단 답글 수로 센다. 여기서도 상태 파일이 필요 없다.
        today_mine = sum(
            1 for i in items
            if i["username"] == ME and i.get("timestamp", "").startswith(today)
        )
        if today_mine >= DAILY_CAP:
            telegram(f"⚠️ 자동 답글 하루 상한({DAILY_CAP}건) 도달. 남은 댓글은 내일 답합니다.")
            break

        for item, followup_ok in pick(items, my_ids):
            if sent >= RUN_CAP:
                break
            kind, value = match(item["text"], keys)
            msg = compose(kind, value, item["username"], replies, followup_ok)
            if not msg:
                continue
            try:
                send(msg, item["id"])
                sent += 1
            except Exception as e:
                print(e, file=sys.stderr)
                telegram(f"⚠️ 자동 답글 실패\n{item['id']}\n{e}")

    print(f"답글 {sent}건")
    return 0


if __name__ == "__main__":
    token = os.environ.get("THREADS_TOKEN")
    if not token:
        print("THREADS_TOKEN 미설정 — 아무것도 하지 않음", file=sys.stderr)
        sys.exit(0)
    # publish.py는 TOKEN을 __main__에서만 설정한다. import해서 쓸 때는 직접 넣어야 한다.
    publish.TOKEN = token
    sys.exit(main())
```

- [ ] **Step 4: 돌려서 통과를 확인한다**

Run: `python test_auto_reply.py`
Expected: `ok`

`ImportError: cannot import name 'API' from 'publish'`가 나면 `publish.py:20` 근처의 `API` 상수를 확인한다(모듈 최상단에 있다).

- [ ] **Step 5: main 전체 흐름 테스트를 추가한다**

`test_auto_reply.py`의 `print("ok")` 앞에 붙인다. 네트워크와 파일을 모두 가짜로 바꾼다:

```python
import json as _json
import pathlib as _pathlib
import tempfile

tmp = _pathlib.Path(tempfile.mkdtemp())
(tmp / "queue.json").write_text(_json.dumps([
    {"id": "top5-a", "status": "published", "post_id": "m1",
     "text": "...댓글에 구 이름 남겨줘.",
     "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
]), encoding="utf-8")
(tmp / "district_replies.json").write_text(
    _json.dumps({"서울 노원구": "1. 스파 (상계동) — 1등 52회\n\n한 집 독주."}), encoding="utf-8"
)
auto_reply.HERE = tmp
auto_reply.REPLIES = tmp / "district_replies.json"

auto_reply.conversation = lambda media_id, token: [
    {"id": "c1", "username": "u1", "text": "노원구", "replied_to": {"id": "m1"}, "timestamp": "2026-09-25T00:00:00+0000"},
    {"id": "c2", "username": "u2", "text": "ㅋㅋ", "replied_to": {"id": "m1"}, "timestamp": "2026-09-25T00:00:00+0000"},
]
auto_reply.telegram = lambda text: None
posted = []
auto_reply.send = lambda text, reply_to: posted.append((text, reply_to)) or "new-id"

assert auto_reply.main() == 0
assert len(posted) == 1, posted  # 지역명 있는 댓글에만 답한다
assert posted[0][1] == "c1", posted
assert "노원구" in posted[0][0], posted
```

- [ ] **Step 6: 돌려서 통과를 확인한다**

Run: `python test_auto_reply.py`
Expected: `ok`

`main()`이 `publish.TOKEN`을 참조하는데 테스트에서는 설정되지 않는다. `conversation`을 갈아끼웠으므로 실제로 읽히지 않지만, `AttributeError`가 나면 테스트 위쪽에 `import publish; publish.TOKEN = "fake"`를 추가한다.

- [ ] **Step 7: 커밋**

```bash
git add auto_reply.py test_auto_reply.py
git commit -m "feat: 대상 글 선정과 실행 흐름 (상한·실패 알림 포함)"
```

---

### Task 6: 워크플로와 문서

**Files:**
- Create: `.github/workflows/auto-reply.yml`
- Modify: `SETUP.md`

**Interfaces:**
- Consumes: `auto_reply.py` (Task 5)

- [ ] **Step 1: 워크플로를 쓴다**

`.github/workflows/auto-reply.yml`:

```yaml
name: Auto reply to comments

on:
  schedule:
    # 10분마다. Actions cron은 최소 5분이고 실제로는 더 밀리므로, 답글까지 5~20분
    # 걸린다고 보면 된다. public 저장소라 실행 분 제한은 없다.
    - cron: "*/10 * * * *"
  workflow_dispatch:

jobs:
  reply:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Reply
        env:
          THREADS_TOKEN: ${{ secrets.THREADS_TOKEN }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python auto_reply.py
```

커밋 단계가 없다: 답글 이력은 Threads에 남고 `conversation`으로 다시 읽히므로 저장소에 쓸 것이 없다.

- [ ] **Step 2: `publish.yml`과 형식을 맞춘다**

Run: `diff .github/workflows/publish.yml .github/workflows/auto-reply.yml`

`actions/checkout` 버전이나 python 설정 방식이 다르면 `publish.yml` 쪽에 맞춘다.

- [ ] **Step 3: SETUP.md에 권한을 추가한다**

`SETUP.md`의 "1. 토큰 발급"에서 요청 권한 목록에 `threads_manage_replies`를 추가한다. 목록이 문장으로 적혀 있으면 그 문장에 덧붙인다.

- [ ] **Step 4: SETUP.md "4. 운영"에 항목을 추가한다**

```markdown
- 댓글 자동 답글: "구 이름 남겨줘" 형 글에 달린 댓글에 10분마다 TOP3를 답한다.
  지역명을 못 알아들으면 답하지 않는다(그건 직접 답하면 된다).
  하루 상한 50건, 1회 10건, 최근 7일 글만 본다.
- 새 시도 데이터를 추가했으면 로컬에서 `python bake_replies.py`를 돌리고
  `district_replies.json`을 커밋해야 답글에 반영된다.
```

- [ ] **Step 5: SETUP.md "3. 한도"의 Threads 줄을 고친다**

기존: `- Threads API: 프로필당 24시간 이동 기준 **250건**. 하루 3건이면 1.2%.`

수정:
```markdown
- Threads API: 프로필당 24시간 이동 기준 **250건**. 발행 3건 + 링크답글 3건에
  자동 답글 최대 50건을 더해도 56건으로 한도의 22%다.
```

- [ ] **Step 6: 커밋**

```bash
git add .github/workflows/auto-reply.yml SETUP.md
git commit -m "feat: 자동 답글 워크플로 추가, 운영 문서 갱신"
```

---

### Task 7: 토큰 재발급과 실제 확인

**Files:** 없음 (사람이 하는 작업 + 확인)

이 태스크는 Meta 개발자 콘솔에서 사람이 해야 한다. 앞의 여섯 태스크는 이것 없이 완료할 수 있지만, 이것 없이는 실제로 동작하지 않는다.

- [ ] **Step 1: 권한을 추가하고 토큰을 다시 받는다**

`SETUP.md`의 "1. 토큰 발급"을 다시 수행하되, 권한에 `threads_manage_replies`를 포함한다. 단기 토큰 → 장기 토큰 교환까지 하고 `THREADS_TOKEN` 시크릿을 교체한다.

- [ ] **Step 2: 권한이 붙었는지 확인한다**

Actions에서 `Auto reply to comments`를 수동 실행하고 로그를 본다.

Expected: `답글 N건` (댓글이 없으면 `답글 0건`)

`code 10: Application does not have permission`이 다시 나오면 권한이 안 붙은 것이다. 인증창을 다시 돌려야 한다.

- [ ] **Step 3: 실제 댓글로 확인한다**

**본인 계정이 아닌 계정으로** 대상 글에 `노원구`라고 댓글을 단 뒤 워크플로를 수동 실행한다.

Expected: TOP3 답글이 달린다. 본인 계정으로 달면 `ME` 필터에 걸려 답이 안 나간다.

- [ ] **Step 4: 무인 실행을 확인한다**

수동 실행 성공은 "코드에 버그가 없다"만 증명한다. cron이 실제로 도는지는 따로 봐야 한다.

Run: `gh run list --workflow=auto-reply.yml --limit 5`
Expected: 트리거가 `schedule`인 실행이 `success`로 찍혀 있다.

그 전까지는 "코드는 됐고 무인 실행은 미확인"이라고만 말한다.

- [ ] **Step 5: 유도 문구를 고친다**

지금 문구는 "다음 글에 올림"이라고 약속한다. 자동 답글이 도는 것을 확인한 뒤에 바꾼다.

`gen_district_posts.py`의 `CLOSERS[0]`을 다음으로 바꾼다:

```python
"우리 동네도 궁금하면 댓글에 구 이름 남겨줘. 바로 뽑아줌 (답글 몇 분 걸릴 수 있음).",
```

그다음 큐의 미발행 항목에 같은 치환을 적용한다:

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
import json, pathlib
old = "우리 동네도 궁금하면 댓글에 구 이름 남겨줘. 다음 글에 올림."
new = "우리 동네도 궁금하면 댓글에 구 이름 남겨줘. 바로 뽑아줌 (답글 몇 분 걸릴 수 있음)."
p = pathlib.Path("queue.json")
q = json.loads(p.read_text(encoding="utf-8"))
n = 0
for item in q:
    if item.get("status") == "pending" and old in item["text"]:
        item["text"] = item["text"].replace(old, new)
        n += 1
p.write_text(json.dumps(q, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{n}건 수정")
PY
```
Expected: `23건 수정` 안팎. 발행된 글은 건드리지 않는다 — 이미 나간 글의 약속은 지킬 수 없다.

- [ ] **Step 6: 새 문구가 `targets`에 여전히 걸리는지 확인한다**

`targets()`는 `"구 이름 남겨줘"`로 거른다. 새 문구에도 그 조각이 그대로 있으므로 계속 걸린다.

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "
import json, auto_reply, datetime
q = json.load(open('queue.json', encoding='utf-8'))
now = datetime.datetime.now(datetime.timezone.utc)
print(len([p for p in q if '구 이름 남겨줘' in p['text']]), '건이 자동답글 대상 문구를 갖고 있음')
"
```
Expected: 23 안팎.

- [ ] **Step 7: 커밋**

```bash
git add queue.json gen_district_posts.py
git commit -m "chore: 유도 문구를 '다음 글에 올림'에서 '바로 뽑아줌'으로"
```
