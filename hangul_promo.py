"""한글폭탄(새 게임 앱) 개발 일지 글. 주 2회 화·목 18:07 KST, 4주(2026-11-03 ~ 11-26).

광고처럼 보이지 않게 '만드는 사람 이야기'로 쓴다. 매 글 끝에 질문 하나만 둔다.
댓글은 사람(계정 주인)이 직접 단다 — auto_reply 대상이 되지 않게 reply_mode를 달지 않고
"구 이름 남겨줘"도 쓰지 않는다.

하루 글 수는 늘리지 않는다: 이 글이 나간 날은 밤 슬롯(21:07)을 비운다(tick.due_slot_start).
조회수 실험 리포트(weekly_check)에서는 이 글을 뺀다 — 로또 글 실험과 섞이면 비교가 흐려진다.

의견 반영 글(feedback=True)은 실제 댓글을 근거로 써야 한다. 그날까지 본문(text)이 채워지지
않았으면 지어내지 않고 fallback 글을 올린다. 댓글은 collect()가 매일 모아 hangul_comments.json에
남긴다(본문만, 닉네임은 남기지 않는다 — 공개 저장소다).
"""

import datetime
import json
import pathlib
import sys

import publish

KST = datetime.timezone(datetime.timedelta(hours=9))
HERE = pathlib.Path(__file__).parent
QUEUE = HERE / "queue.json"
COMMENTS = HERE / "hangul_comments.json"
POST_TIME = (18, 7)
STORE = ("https://play.google.com/store/apps/details?id=kr.gzclab.hangulbomb"
         "&referrer=utm_source%3Dthreads%26utm_medium%3Dsocial%26utm_campaign%3Ddevlog")
LEAD = "구글 플레이에서 '한글폭탄' 검색해도 나옴:"
LIMIT = 500
D = datetime.date

POSTS = [
    {"date": D(2026, 11, 3), "key": "launch", "text": """로또 앱 만들던 사람이 한글 게임을 만들었음.

한글폭탄. 구글 플레이 승인 남.

떨어지는 글자 조각을 쌓아서 가로나 세로로 단어를 만들면 그 자리가 충전됨.
근데 바로 안 터짐. 옆에 글자를 더 붙이면 두 글자가 세 글자, 네 글자로 자람.
터뜨리기 버튼을 누르면 모아둔 단어가 한꺼번에 터짐.

회원가입 없고, 인터넷 없어도 됨.

혼자 만든 거라 아직 거친 데가 많을 거임.
해보고 첫인상 한마디만 댓글로 남겨줘. 전부 읽고 고칠 거 고침."""},
    {"date": D(2026, 11, 5), "key": "core", "text": """한글폭탄에서 제일 고민되는 순간은 이거임.

지금 터뜨릴까, 더 모을까.

두 글자 단어는 20점, 네 글자는 80점.
한 번에 터뜨리는 단어가 많을수록 점수 배수가 붙음.
근데 욕심내서 모으다 블록이 꼭대기에 닿으면 끝.

무한 모드는 점수 오를수록 조각이 빨라지고,
스테이지 모드는 미션 단어를 정해진 블록 개수 안에 만들어야 함.

1판 해보고 제일 불편했던 점 하나만 댓글로 알려줘.
조작이든 글자든 속도든 다 좋음."""},
    {"date": D(2026, 11, 10), "key": "feedback1", "feedback": True, "text": None,
     "fallback": """한글폭탄 스테이지 모드는 끝이 없음.

스테이지마다 만들어야 할 미션 단어가 나옴.
블록 개수는 정해져 있어서 아무 데나 쌓으면 모자람.
올라갈수록 미션 단어가 늘고, 길어지고, 조각은 빨라짐.

조작은 세 개가 전부임.
좌우로 쓸어서 옮기고, 화면 탭해서 돌리고, 아래로 쓸어서 빨리 내림.

스테이지 몇 단계까지 갔는지 댓글로 남겨줘.
어디서 막히는지 보고 난이도 참고할 거임."""},
    {"date": D(2026, 11, 12), "key": "words", "text": """한글폭탄은 아무 단어나 인정하지 않음.

국립국어원 한국어기초사전에서 고른 명사 8,642개만 됨.
단어를 만들면 영어 뜻도 그 자리에서 보여줌(6,445개).
한국어 배우는 사람한테도 쓸모 있게 만들고 싶었음.

근데 사전에 없어서 아쉬운 단어가 분명 있을 거임.
게임에 넣었으면 하는 단어 하나씩 댓글로 남겨줘.
모아서 다음 업데이트 때 검토함."""},
    {"date": D(2026, 11, 17), "key": "feedback2", "feedback": True, "text": None,
     "fallback": """한글폭탄은 10개 언어로 나옴.

한국어, 영어, 일본어, 중국어(간체·번체), 스페인어, 포르투갈어, 베트남어, 인도네시아어, 태국어.
설명이랑 메뉴는 그 나라 말로 나오고, 만드는 단어는 전부 한글임.

한국어 배우는 외국인 친구한테 보여주면 어떤 반응일지 궁금함.
주변에 한국어 공부하는 사람 있으면 어떤 언어 쓰는지 댓글로 알려줘.
다음 언어 추가할 때 참고함."""},
    {"date": D(2026, 11, 19), "key": "music", "text": """한글폭탄 배경음악은 전부 새로 편곡한 거임.

아리랑, 도라지 타령, 이반 폴카, 라 쿠카라차, 그리고 창작 폴카 하나.
민요를 게임 리듬에 맞게 빠르게 바꿨음.
게임 안에서 다음 곡으로 넘길 수 있음.

다음에 넣을 노래 고르는 중임.
듣고 싶은 나라 민요 있으면 댓글로 알려줘."""},
    {"date": D(2026, 11, 24), "key": "challenge", "text": """한글폭탄 무한 모드 최고 기록 모아보려고 함.

점수 오를수록 조각이 빨라져서 어느 순간 손이 못 따라감.
그때 터뜨릴지 버틸지가 기록을 가름.

최고 점수 화면 캡처해서 댓글에 올려줘.
높은 점수는 다음 글에서 닉네임으로 소개함."""},
    {"date": D(2026, 11, 26), "key": "feedback3", "feedback": True, "text": None,
     "fallback": """한글폭탄은 짧게 끊어서 하는 게임으로 만들었음.

인터넷 없어도 되고, 회원가입 없이 기록은 휴대폰 안에만 남음.
출퇴근 지하철이나 잠깐 쉬는 시간에 하기 좋게.

언제 제일 많이 하게 되는지 댓글로 알려줘.
그 시간에 맞춰서 다음 기능 정할 거임."""},
]


def kst(now):
    return now.astimezone(KST)


def post_id_of(key):
    return f"hangul-{key}"


def body(p):
    """그날 올릴 본문. 의견 반영 글이 아직 안 써졌으면 fallback."""
    return p["text"] if p.get("text") else p.get("fallback")


def due_post(now, queue):
    local = kst(now)
    if (local.hour, local.minute) < POST_TIME:
        return None
    done = {q["id"] for q in queue}
    for p in POSTS:
        if p["date"] == local.date() and post_id_of(p["key"]) not in done and body(p):
            return p
    return None


def run_auto(now, dry=False):
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    p = due_post(now, queue)
    if not p:
        return 0
    text = body(p)
    used_fallback = p.get("feedback") and not p.get("text")
    if dry:
        print(text)
        return 0
    try:
        pid = publish.publish(text)
    except Exception as e:
        publish.telegram(f"❌ 한글폭탄 글 발행 실패 ({p['key']})\n{e}")
        raise
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    queue.append({"id": post_id_of(p["key"]), "status": "published", "slot": "hangul", "text": text,
                  "post_id": pid,
                  "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                  **({"fallback": True} if used_fallback else {})})
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        publish.publish(f"{LEAD}\n{STORE}", reply_to=pid)
    except Exception as e:
        publish.telegram(f"⚠️ 한글폭탄 본문은 올랐는데 링크 답글 실패\n{e}")
    return 0


def posted_today(queue, now):
    today = kst(now).date()
    for q in queue:
        if q["id"].startswith("hangul-") and q.get("published_at"):
            if kst(datetime.datetime.fromisoformat(q["published_at"])).date() == today:
                return True
    return False


def collect(now, token, fetch=None):
    """한글폭탄 글에 달린 남의 댓글 본문을 모은다. 의견 반영 글을 쓸 근거다. 하루 한 번."""
    if fetch is None:
        import auto_reply
        fetch = auto_reply.conversation
    data = json.loads(COMMENTS.read_text(encoding="utf-8")) if COMMENTS.exists() else {}
    today = kst(now).date().isoformat()
    if data.get("_collected") == today:
        return data
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    changed = False
    for q in queue:
        if not (q["id"].startswith("hangul-") and q.get("post_id")):
            continue
        try:
            items = fetch(q["post_id"], token)
        except Exception as e:   # 하나 실패로 5분마다 알림이 오면 안 된다. 다음 날 다시 모은다
            print(f"한글폭탄 댓글 수집 실패 {q['id']}: {e}", file=sys.stderr)
            continue
        texts = [i["text"] for i in items if i.get("username") != "gzclab" and i.get("text")]
        if data.get(q["id"]) != texts:
            data[q["id"]] = texts
            changed = True
    data["_collected"] = today
    COMMENTS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for p in POSTS:
        t = body(p)
        print(f"== {p['date']} {p['key']} {'(의견 반영 전 fallback)' if p.get('feedback') and not p.get('text') else ''} {len(t)}자")
        print(t)
        print()
