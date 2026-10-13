"""특정 회차 글(기본 1245회 흐름 정리)의 댓글에 내가 단 번호가 몇 등이었는지 집계한다.

실행: python check_comment_wins.py [회차]   (기본 1245)
THREADS_TOKEN 환경변수 또는 key.txt의 'Threads 사용자토큰' 값을 쓴다. 조회만 하고 아무것도 올리지 않는다.
"""
import collections, json, os, re, sys

import auto_reply as ar
import lotto_picks as lp
import publish

sys.stdout.reconfigure(encoding="utf-8")
HERE = lp.HERE
NUMS = re.compile(r"((?:\d{2}[ ,·]+){5}\d{2})")


def token():
    t = os.environ.get("THREADS_TOKEN")
    if t:
        return t
    m = re.search(r"Threads 사용자토큰\s*\n(\S+)", (HERE / "key.txt").read_text(encoding="utf-8"))
    return m.group(1)


def parse_reply(text):
    """내 답글 텍스트 → (닉네임, 번호 6개) 또는 None."""
    m = NUMS.search(text)
    if not m:
        return None
    nums = sorted(int(x) for x in re.findall(r"\d{2}", m.group(1)))
    return (text.split("아 ")[0], nums) if len(nums) == 6 else None


def main(draw_no):
    queue = json.loads((HERE / "queue.json").read_text(encoding="utf-8"))
    post = next(p for p in queue if p["id"] == f"picks-{draw_no}-stats")
    publish.TOKEN = tok = token()
    win, bonus = lp.fetch_winning(draw_no)
    print(f"{draw_no}회 당첨번호 {win} + 보너스 {bonus}")
    items = ar.conversation(post["post_id"], tok)
    mine = [i for i in items if i["username"] == ar.ME]
    rows = []
    for i in mine:
        r = parse_reply(i["text"])
        if r:
            rows.append((r[0], r[1], len(set(r[1]) & set(win)), lp.rank_of(r[1], win, bonus)))
    print(f"댓글 전체 {len(items)}개 / 내가 단 답글 {len(mine)}개 / 번호 읽힌 것 {len(rows)}개")
    print("일치 개수별:", dict(sorted(collections.Counter(r[2] for r in rows).items())))
    print("등수별:", dict(sorted(collections.Counter(r[3] for r in rows if r[3]).items())) or "당첨(5등 이상) 없음")
    for user, nums, hit, rank in sorted(rows, key=lambda r: (-r[2], r[0]))[:10]:
        print(f"  {user:20} {' '.join(f'{n:02d}' for n in nums)}  {hit}개 일치" + (f" → {rank}등" if rank else ""))
    (HERE / f"comment_wins_{draw_no}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1245)
