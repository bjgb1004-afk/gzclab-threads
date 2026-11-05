"""한글폭탄(새 게임 앱) 개발 일지 글. 11/3·11/5 두 편 뒤로 2026-11-06부터 30일간 매일 19:07 KST.

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
POST_TIME = (19, 7)   # 2026-11-03 유저 요청: 매일 저녁 7시. :07은 정각 혼잡 회피
STORE = ("https://play.google.com/store/apps/details?id=kr.gzclab.hangulbomb"
         "&referrer=utm_source%3Dthreads%26utm_medium%3Dsocial%26utm_campaign%3Ddevlog")
LEAD = "구글 플레이에서 '한글폭탄' 검색해도 나옴:"
LIMIT = 500
D = datetime.date
TAG = "\n\n#한글게임"
POSTS = [
    # 이미 나간 글(기록용). due_post는 날짜가 지나 다시 고르지 않는다.
    {"date": D(2026, 11, 3), "key": "launch", "text": None, "done": True},
    {"date": D(2026, 11, 5), "key": "core", "text": None, "done": True},
    # ---- 11/6부터 30일, 매일 19:07 ----
    {"date": D(2026, 11, 6), "key": "d01-charge", "text": """단어를 만들었는데 안 터지는 게임을 만들었음.

한글폭탄은 가로나 세로로 단어가 완성되면 청록색으로 충전만 됨.
터지는 건 내가 터뜨리기 버튼을 누를 때.

그래서 한 판 내내 고민함. 지금 터뜨릴까, 더 모을까.

너라면 바로 터뜨리는 쪽임, 끝까지 모으는 쪽임?"""},
    {"date": D(2026, 11, 7), "key": "d02-length", "text": """한글폭탄 점수는 단어 길이가 정함.

두 글자 20점, 네 글자 80점.
충전된 단어 옆에 글자를 더 붙이면 단어가 자람.
'사과' 옆에 '나무'를 붙이면 '사과나무'가 되는 식.

두 글자 단어에 글자를 붙여서 더 길게 만들 수 있는 거, 제일 먼저 떠오르는 거 하나 댓글로 줘봐."""},
    {"date": D(2026, 11, 8), "key": "d03-multiplier", "text": """한 번에 많이 터뜨릴수록 배수가 붙음.

2단어 ×1.5
3단어 ×2
4단어 ×2.5
6단어 ×3.5

문제는 6단어 모으는 동안 판이 꽉 찬다는 거.

몇 단어 모였을 때 터뜨리는 게 제일 낫다고 봄?"""},
    {"date": D(2026, 11, 9), "key": "d04-streak", "text": """한글폭탄에서 제일 아까운 순간.

조각을 놓을 때마다 단어가 자라면 연속(Streak)이 쌓이고 배수가 올라감.
근데 한 번이라도 단어를 못 만들면 0으로 돌아감.

10연속 쌓다가 한 번 실수해서 날리면 진짜 허탈함.

게임하다 제일 허탈했던 순간 있음?"""},
    {"date": D(2026, 11, 10), "key": "d05-sweep", "text": """터뜨리면 주변 글자도 같이 청소됨.

2~3단어를 터뜨리면 상하좌우,
4단어 이상이면 대각선까지 묻힌 글자를 쓸어냄.
4단어를 모으면 사라지는 글자가 2배.

판이 지저분해졌을 때 한 방에 정리되는 맛으로 만들었음.

정리 안 된 판 보면 못 참는 편임?"""},
    {"date": D(2026, 11, 11), "key": "d06-cross", "text": """가로 단어랑 세로 단어가 한 글자를 같이 쓰면 둘 다 점수를 받음.

십자말풀이처럼 겹치게 쌓으면 한 글자로 두 번 버는 셈.

어릴 때 신문 십자말풀이 해본 적 있음?
해봤으면 이 게임 금방 감 잡음."""},
    {"date": D(2026, 11, 12), "key": "d07-danger", "text": """한글폭탄에는 위험선이 있음.

블록이 위험선에 닿으면 그 자리에서 자동으로 폭발함.
모아둔 거 원하는 타이밍에 못 터뜨리고 강제로 터지는 거라 손해임.

욕심부리다 자동 폭발 당하는 게 이 게임의 국룰 같음.

욕심부리다 망하는 타입임, 안전하게 가는 타입임?"""},
    {"date": D(2026, 11, 13), "key": "fb1", "feedback": True, "text": None, "fallback": """한글폭탄 스테이지 모드는 끝이 없음.

스테이지마다 완성해야 할 미션 단어가 주어지고, 블록 개수는 정해져 있음.
올라갈수록 미션 단어가 늘고, 길어지고, 조각은 빨라짐.

해본 사람은 몇 스테이지까지 갔는지 댓글로 알려줘.
어디서 막히는지 보고 난이도 참고함."""},
    {"date": D(2026, 11, 14), "key": "d08-dict", "text": """한글폭탄은 아무 단어나 안 받아줌.

국립국어원 한국어기초사전에서 고른 명사 8,642개만 인정함.
그래서 신조어나 줄임말은 안 됨.

사전에 없어서 안 될 것 같은데 꼭 넣고 싶은 단어 하나만 댓글로 말해봐."""},
    {"date": D(2026, 11, 15), "key": "d09-english", "text": """단어를 만들면 그 자리에서 영어 뜻이 뜸.

6,445개 단어에 영어 뜻을 붙여놨음.
한 판 끝나면 '익힌 단어'로 그 판에서 만든 단어를 모아서 보여줌.

놀다 보면 영어 단어가 따라오는 구조.

영어로 뜻 물어보면 의외로 헷갈리는 한국어 단어, 뭐가 있을까?"""},
    {"date": D(2026, 11, 16), "key": "d10-lang", "text": """한글폭탄은 10개 언어로 나옴.

한국어, 영어, 일본어, 중국어(간체·번체), 스페인어, 포르투갈어, 베트남어, 인도네시아어, 태국어.
설명이랑 메뉴는 그 나라 말로, 만드는 단어는 전부 한글.

한국어 배우는 외국인 친구한테 보여주면 어떤 반응일 것 같음?"""},
    {"date": D(2026, 11, 17), "key": "d11-arirang", "text": """한글폭탄 배경음악에 아리랑이랑 도라지 타령이 들어감.

민요를 게임 리듬에 맞게 빠르게 새로 편곡했음.
한글 게임이니까 한국 노래는 꼭 넣고 싶었음.

민요 중에 게임 음악으로 바꾸면 신날 것 같은 곡 있음?"""},
    {"date": D(2026, 11, 18), "key": "d12-polka", "text": """한글폭탄 배경음악에는 외국 민요도 있음.

핀란드 이반 폴카, 멕시코 라 쿠카라차, 그리고 직접 만든 폴카 한 곡.
게임 안에서 다음 곡으로 넘길 수 있음.

게임할 때 음악 켜고 하는 편임, 끄고 하는 편임?"""},
    {"date": D(2026, 11, 19), "key": "d13-control", "text": """한글폭탄 조작은 세 개가 전부임.

좌우로 쓸어서 옮기고
화면 탭해서 돌리고
아래로 쓸어서 빨리 내림.

설명 안 읽고 바로 해도 되게 만들려고 했는데, 처음 해보고 헷갈렸던 거 있으면 댓글로 말해줘."""},
    {"date": D(2026, 11, 20), "key": "fb2", "feedback": True, "text": None, "fallback": """한글폭탄은 회원가입이 없음.

기록은 휴대폰 안에만 저장되고, 인터넷 없이도 할 수 있음.
연결이 필요한 건 광고 나올 때뿐.

게임 깔았는데 회원가입부터 하라고 하면 바로 지우는 편임?"""},
    {"date": D(2026, 11, 21), "key": "d14-endless", "text": """무한 모드는 블록이 꼭대기에 닿을 때까지 계속됨.

점수가 오를수록 조각이 빨리 떨어짐.
어느 순간 손이 판단을 못 따라가는 구간이 옴.

이런 게임 하면 보통 몇 분 버티는 편임?"""},
    {"date": D(2026, 11, 22), "key": "d15-stage", "text": """스테이지 모드는 '남은 블록'이 핵심임.

미션 단어는 정해져 있는데 쓸 수 있는 블록 개수가 한정돼 있음.
아무 데나 쌓으면 미션 다 못 채우고 블록이 먼저 떨어짐.

퍼즐은 시간 제한 있는 게 좋음, 횟수 제한 있는 게 좋음?"""},
    {"date": D(2026, 11, 23), "key": "d16-board", "text": """한글폭탄 판은 가로 9칸, 세로 16줄임.

그 안에서 가로로도 세로로도 단어가 됨.
같은 조각이라도 어느 방향으로 세우느냐에 따라 만들어지는 단어가 달라짐.

단어 만들 때 가로파임, 세로파임?"""},
    {"date": D(2026, 11, 24), "key": "d17-three", "text": """한글폭탄 하다 보면 세 글자 단어가 제일 많이 나옴.

두 글자는 쉽게 만들어지고, 네 글자는 노려야 나오고.
세 글자가 딱 중간이라 그런 듯.

제일 좋아하는 세 글자 단어 하나만 댓글로 줘봐. 명사로."""},
    {"date": D(2026, 11, 25), "key": "d18-score", "text": """한글폭탄 무한 모드 최고 기록 모아보려고 함.

점수 오를수록 조각이 빨라져서 어느 순간 손이 못 따라감.
그때 터뜨릴지 버틸지가 기록을 가름.

최고 점수 화면 캡처해서 댓글에 올려줘."""},
    {"date": D(2026, 11, 26), "key": "d19-origin", "text": """한글폭탄은 처음에 웹게임으로 만들었음.

웹으로 먼저 해보고 재밌는지 확인한 다음, 앱으로 처음부터 다시 만들었음.
이름도 원래는 '모아글'이었음.

모아글이랑 한글폭탄 중에 어느 이름이 더 끌림?"""},
    {"date": D(2026, 11, 27), "key": "fb3", "feedback": True, "text": None, "fallback": """'한글폭탄'이라는 이름은 몇 번 바뀌고 나서 정해졌음.

한글팡, 워드팡도 생각했는데 같은 이름 앱이 이미 있었음.
그래서 단어를 모아서 터뜨리는 게임이니까 폭탄으로 감.

이름만 듣고 어떤 게임일 것 같았음?"""},
    {"date": D(2026, 11, 28), "key": "d20-bomb", "text": """'폭'으로 시작하는 단어 몇 개나 떠오름?

폭탄, 폭포, 폭풍…
한글폭탄 하다 보면 이런 식으로 한 글자에서 단어를 이어 붙이게 됨.

'폭'으로 시작하는 단어 중에 남들이 안 떠올릴 것 같은 거 하나 댓글로."""},
    {"date": D(2026, 11, 29), "key": "d21-offline", "text": """한글폭탄은 지하철에서도 끊기지 않음.

인터넷 없이 돌아가게 만들었고, 기록도 휴대폰 안에만 남음.
광고 나올 때만 연결이 필요함.

출퇴근길에 게임 하는 편임, 그냥 멍 때리는 편임?"""},
    {"date": D(2026, 11, 30), "key": "d22-learner", "text": """한국어 배우는 사람한테도 쓸모 있게 만들고 싶었음.

사전 명사만 인정하고, 만든 단어마다 영어 뜻을 보여주고, 메뉴는 10개 언어로 나옴.

주변에 한국어 공부하는 외국인 친구 있으면, 그 친구가 제일 어려워하는 게 뭐임?"""},
    {"date": D(2026, 12, 1), "key": "d23-strategy", "text": """한글폭탄 하면서 찾은 나름의 요령.

2단어 ×1.5, 4단어 ×2.5라서 4단어까지는 모아보는 게 이득임.
4단어를 모으면 청소되는 글자도 2배라 판도 같이 정리됨.
대신 위험선 근처면 욕심 버리는 게 맞음.

너는 몇 단어에서 터뜨림?"""},
    {"date": D(2026, 12, 2), "key": "d24-combo", "text": """한 판이 끝나면 점수 말고도 두 가지를 보여줌.

그 판의 최고 콤보, 그리고 그 판에서 익힌 단어.
점수가 낮아도 단어를 많이 익혔으면 그것도 남는 판이라고 생각했음.

게임 끝나고 점수 말고 보고 싶은 기록 있음?"""},
    {"date": D(2026, 12, 3), "key": "d25-quiz", "text": """글자 순서 섞어놨음. 무슨 단어일까?

글 · 한 · 탄 · 폭

한글폭탄은 이런 식으로 떨어지는 조각을 맞춰서 단어를 만드는 게임임.

답 말고, 너도 섞인 글자로 댓글에 문제 하나 내줘봐."""},
    {"date": D(2026, 12, 4), "key": "fb4", "feedback": True, "text": None, "fallback": """한글폭탄 단어는 길어야 네 글자임.

사전에 두 글자 단어가 제일 많고, 네 글자 단어는 훨씬 적음.
그래서 네 글자 80점이 귀함.

생각나는 네 글자 명사 하나 댓글로 줘봐. 게임에 있는지 확인해봄."""},
    {"date": D(2026, 12, 5), "key": "fb5", "feedback": True, "text": None, "fallback": """한글폭탄 다음 업데이트 후보를 고르는 중임.

새 배경음악, 새 모드, 단어 테마(음식·동물·지명 같은 것).

셋 중에 제일 먼저 보고 싶은 거 하나만 댓글로 골라줘."""},
]

def kst(now):
    return now.astimezone(KST)


def post_id_of(key):
    return f"hangul-{key}"


def body(p):
    """그날 올릴 본문. 의견 반영 글이 아직 안 써졌으면 fallback. 끝에 주제 태그 하나를 붙인다
    (스레드는 태그 하나로 같은 관심사 사람들에게 보여준다 — social-media-skills threads-post)."""
    if p.get("done"):
        return None
    t = p["text"] if p.get("text") else p.get("fallback")
    return t + TAG if t else None


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


def scheduled_today(now):
    """오늘 나갈 한글폭탄 글이 있는가(아직 안 나갔어도)."""
    today = kst(now).date()
    return any(p["date"] == today and body(p) for p in POSTS)


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
