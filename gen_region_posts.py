"""글이 한 번도 안 나간 시군구의 TOP3 글을 찍어 queue.json 앞쪽(아침 슬롯)에 꽂는다.

왜 필요했나 (2026-10-26 조회수 실측):
  지역 글은 이 계정 최고 성과다 — 김포 21,607 / 의정부 7,483 / 경기 광주 7,244.
  그런데 손으로 쓴 68편이 거의 다 수도권이고, 그게 다 나가서 gen_posts.recycle()이
  같은 글을 다시 돌리고 있었다. 반면 district_replies.json에는 215개 시군구가 이미
  커밋돼 있고 그중 126곳은 글이 한 번도 안 나갔다. 새 소재가 없던 게 아니라 안 쓰고 있었다.

  gen_district_posts.py는 districts.json(미커밋, Actions에 없음)이 필요해서 러너에서
  못 돈다. 이쪽은 커밋된 district_replies.json만 쓰므로 Actions에서 그냥 돈다.

TOP5가 아니라 TOP3인 이유: district_replies.json이 지역당 3곳만 갖고 있다. 5곳을 쓰려면
districts.json이 필요하다. 없는 2줄을 지어내는 것보다 제목을 TOP3로 쓰는 게 맞다.

본문의 숫자와 한 줄 분석은 district_replies.json 원문을 그대로 쓴다 — auto_reply가 댓글에
답으로 보내는 것과 같은 텍스트라야, 글을 보고 댓글 단 사람이 같은 숫자를 받는다.

1위 배출횟수가 큰 지역부터 내보낸다. 숫자가 큰 동네가 반응이 크고(노원구 1위 52회),
표본이 작은 동네는 뒤로 밀려 자연히 나중에 나간다.

실행: python gen_region_posts.py --dry          (미리보기, 큐를 건드리지 않는다)
      python gen_region_posts.py --dry -n 3     (3편만)
      python gen_region_posts.py                (전부 큐 앞쪽에 꽂는다)
      python gen_region_posts.py -n 20          (상위 20편만)
"""

import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 '—' 출력 시 죽는 것 방지

HERE = pathlib.Path(__file__).parent
QUEUE = HERE / "queue.json"
REPLIES = HERE / "district_replies.json"

LIMIT = 500  # Threads 본문 글자 제한
# 랜딩을 거쳐야 미리보기에 복권명당 아이콘이 뜨고 ?c= 값이 Play Console referrer로 넘어간다.
# Play 링크를 직접 달면 구글플레이 기본 아이콘이 뜬다(gen_district_posts.py와 같은 이유).
APP = "https://gzclab.com/lottomap/?c=top5"

# auto_reply.targets()가 "구 이름 남겨줘"가 든 글만 댓글 대상으로 잡는다. 빠지면 댓글이
# 와도 답이 안 달린다 — 이 글 종류의 댓글 엔진이 그것이다.
# 실제로 가장 많이 나갔던 문구 세 개를 그대로 돌려 쓴다(각 19~20편).
ASKS = (
    "여기 없는 동네는 댓글에 구 이름 남겨줘. 바로 찾아서 답 달아줌.",
    "댓글에 구 이름 남겨줘. 전국 다 갖고 있어서 어디 말해도 답 감.",
    "우리 동네 어딘지 궁금하면 댓글에 구 이름 남겨줘. 기다릴 필요 없음.",
)
assert all("구 이름 남겨줘" in a for a in ASKS), "auto_reply가 대상에서 놓친다"

# 꼬리말. 매 글 같은 문장이 반복되면 그게 제일 큰 봇 티다.
TAILS = (
    "다음은 어느 동네 올릴지 댓글 보고 정함. 팔로우해두고 찜해놔.",
    "전국 다 돌 예정. 우리 동네 순서 놓치기 싫으면 팔로우.",
    "이런 거 매일 하나씩 올림. 이어서 볼 사람은 팔로우.",
)

SIDO = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종시", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주")

_TOP1 = re.compile(r"^1\. (.+?)(?: \((.+?)\))? — 1등 (\d+)회$", re.M)
_ROWS = re.compile(r"^\d+\. .+$", re.M)


def load(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_queue(queue):
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bare(district):
    """'서울 노원구' -> '노원구'. 시도 접두어만 떼고 나머지는 그대로."""
    s = district.strip()
    for p in SIDO:
        if s.startswith(p + " "):
            return s[len(p) + 1:]
    return s


def posted_districts(queue):
    """지역 글이 이미 나간(또는 큐에 있는) 지역의 제목 첫 줄 모음.

    제목으로 비교하는 이유: 손으로 쓴 68편의 id 규칙이 일정하지 않고('top5-경기-김포시',
    'top5-경기-용인시-기흥구'), 제목에는 지역명이 반드시 들어간다.
    """
    return [p["text"].splitlines()[0] for p in queue if p.get("text")]


def wins_of(body):
    """그 지역 1위의 1등 횟수. 못 읽으면 None."""
    m = _TOP1.search(body)
    return int(m.group(3)) if m else None


def missing(queue, replies):
    """글이 한 번도 안 나간 지역을 1위 배출횟수 큰 순으로. [(횟수, 지역, 본문), ...]"""
    heads = posted_districts(queue)
    out = []
    for district, body in replies.items():
        # 제목에 '서울 노원구'로 들어갔든 '노원구'로 들어갔든 이미 나간 것으로 본다.
        if any(district in h or bare(district) in h for h in heads):
            continue
        wins = wins_of(body)
        if wins is None:  # 1위 줄을 못 읽으면 숫자를 지어내지 않고 건너뛴다
            continue
        out.append((wins, district, body))
    # 횟수 같으면 지역명 순 — 돌릴 때마다 순서가 바뀌면 안 된다.
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def build(district, body, idx):
    """지역 글 한 편. 숫자와 한 줄 분석은 district_replies.json 원문 그대로 쓴다."""
    rows = _ROWS.findall(body)
    if not rows:
        return None
    # 본문 끝의 한 줄 분석("1위가 52회인데 2위가 8회. 6배 차이 남.")을 그대로 가져온다.
    # 판매점 줄(_ROWS)만 빼고 남는 산문이 그것이다. "숫자로 시작하지 않는 줄"로 걸러선 안
    # 된다 — 저 분석 문장이 '1위가'로 시작해서 통째로 사라진다(실제로 그렇게 날렸다).
    # 성과 좋았던 지역 글(김포 21,607 / 의정부 7,483)에는 전부 이 줄이 있었다.
    note = [l.strip() for l in body.splitlines()
            if l.strip() and not re.match(r"^\d+\. ", l.strip())]
    lines = [
        f"{district}에서 로또 1등 제일 많이 나온 판매점 TOP{len(rows)}",
        "",
        ASKS[idx % len(ASKS)],  # 접힘 앞 — 이 줄이 댓글을 만든다
        "",
        *rows,
    ]
    if note:
        lines += ["", " ".join(note)]
    lines += ["", TAILS[idx % len(TAILS)]]
    text = "\n".join(lines)
    if len(text) <= LIMIT:
        return text
    # 지역당 3줄이라 넘칠 일이 거의 없지만, 넘치면 분석 줄부터 뺀다(꼬리말보다 먼저 뺀다 -
    # 팔로우 유도가 이 글 종류의 유일한 전환 장치다).
    joined = " ".join(note)
    text = "\n".join([l for l in lines if l != joined])
    return text if len(text) <= LIMIT else None


def entry_id(district):
    return "region-" + district.replace(" ", "-")


def generate(limit=None):
    """[(지역, 큐 항목)] — 큐에 꽂지는 않는다."""
    queue = load(QUEUE, [])
    replies = load(REPLIES, {})
    todo = missing(queue, replies)
    if limit is not None:
        todo = todo[:limit]
    out = []
    for idx, (_wins, district, body) in enumerate(todo):
        text = build(district, body, idx)
        if text is None:
            print(f"건너뜀(형식 불일치): {district}", file=sys.stderr)
            continue
        out.append((district, {
            "id": entry_id(district),
            "status": "pending",
            "slot": "am",
            "text": text,
            "link": APP,
        }))
    return out


def main(argv):
    dry = "--dry" in argv
    limit = int(argv[argv.index("-n") + 1]) if "-n" in argv else None
    made = generate(limit)
    if not made:
        print("새로 만들 지역이 없음 — 215곳 전부 글이 나갔다")
        return 0

    if dry:
        for district, item in made:
            print("=" * 60)
            print(item["text"])
            print(f"--- {len(item['text'])}자  [{item['id']}]")
        print(f"\n총 {len(made)}편 (큐는 건드리지 않음)")
        return 0

    queue = load(QUEUE, [])
    have = {p["id"] for p in queue}
    fresh = [item for _d, item in made if item["id"] not in have]
    if not fresh:
        print("이미 큐에 다 들어있음")
        return 0
    # 앞쪽에 꽂는다. publish.main()은 큐 순서에서 처음 만나는 am 글을 집으므로, 새 지역이
    # 재활용된 옛 글보다 먼저 나간다.
    save_queue(fresh + queue)
    print(f"✅ {len(fresh)}편을 큐 앞쪽에 꽂았다. 첫 글: {fresh[0]['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
