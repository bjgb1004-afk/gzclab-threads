"""스레드 조회수 하락 대응 실험(2026-11-02 시작)의 1주 뒤 점검.

무엇을 바꿨나(이 파일이 실험의 정의다):
  - 수요일 18:07 "번호 중간 점검" 글(midweek.py)이 수요일 밤 슬롯 글을 대신한다. 하루 글 수는 그대로.
무엇을 비교하나:
  - 기준 주: 2026-10-28 ~ 11-03 (바로 직전 7일, 수~화)
  - 실험 주: 2026-11-04 ~ 11-10 (같은 요일 구성)
  - 하락 추세 보정: 기준 주 직전 주(10-21 ~ 10-27)도 같이 본다. 추세가 원래 -N%/주였다면 그만큼은 실험 효과가 아니다.
언제 나가나: REPORT_AT(2026-11-12 09:07 KST) 이후 첫 틱에 한 번. 마지막 글의 24시간 성적이 다 모인 뒤다.
무엇을 보내나: 텔레그램 요약 + reports/threads-check-2026-11-12.md (저장소에 남는다).

숫자만 보여주고 결론은 보수적으로 쓴다. 글 수천 개짜리 실험이 아니라 한 주 대 한 주 비교라서,
일요일 대박 글 한두 개가 합계를 흔든다 — 합계보다 중간값과 '상위 3개 제외 평균'을 같이 본다.
"""

import datetime
import json
import pathlib
import statistics
import sys

import publish

HERE = pathlib.Path(__file__).parent
QUEUE = HERE / "queue.json"
STATE = HERE / "experiment.json"
REPORTS = HERE / "reports"
KST = datetime.timezone(datetime.timedelta(hours=9))

D = datetime.date
WINDOWS = {
    "추세 확인(직전 주)": (D(2026, 10, 21), D(2026, 10, 27)),
    "기준 주": (D(2026, 10, 28), D(2026, 11, 3)),
    "실험 주": (D(2026, 11, 4), D(2026, 11, 10)),
}
REPORT_AT = datetime.datetime(2026, 11, 12, 9, 7, tzinfo=KST)
SAME = 0.15   # 이 이내 차이는 '비슷함'으로 본다


def kind(post_id):
    for p in ("picks-", "band-", "spitto-", "winner-", "draw-", "top5-", "talk-", "auto-"):
        if post_id.startswith(p):
            return p.rstrip("-")
    return post_id.split("-")[0]


def rows(queue):
    out = []
    for x in queue:
        i = x.get("insights") or {}
        if x.get("status") != "published" or not x.get("published_at") or "views" not in i:
            continue
        if x["id"].startswith("hangul-"):   # 한글폭탄 글은 로또 글 실험과 따로 본다
            continue
        t = datetime.datetime.fromisoformat(x["published_at"]).astimezone(KST)
        out.append({"id": x["id"], "kind": kind(x["id"]), "date": t.date(), "views": i["views"],
                    "likes": i.get("likes", 0), "replies": i.get("replies", 0),
                    "reposts": i.get("reposts", 0)})
    return out


def summarize(rs, lo, hi):
    sel = [r for r in rs if lo <= r["date"] <= hi]
    if not sel:
        return None
    v = sorted((r["views"] for r in sel), reverse=True)
    total = sum(v)
    rest = v[3:] or v
    days = (hi - lo).days + 1
    return {
        "posts": len(sel), "per_day": round(len(sel) / days, 1), "total": total,
        "mean": round(total / len(v)), "median": round(statistics.median(v)),
        "mean_ex_top3": round(sum(rest) / len(rest)),
        "likes_1k": round(sum(r["likes"] for r in sel) / total * 1000, 1) if total else 0,
        "replies_1k": round(sum(r["replies"] for r in sel) / total * 1000, 1) if total else 0,
        "by_kind": {k: (len(g), round(sum(r["views"] for r in g) / len(g)))
                    for k in sorted({r["kind"] for r in sel})
                    for g in [[r for r in sel if r["kind"] == k]]},
    }


def change(new, old):
    return None if not old else (new - old) / old


def pct(x):
    return "-" if x is None else f"{x * 100:+.0f}%"


def verdict(trend, base, test):
    """중간값과 상위3개 제외 평균이 둘 다 같은 방향으로 움직였을 때만 방향을 말한다."""
    if not (base and test):
        return "측정된 글이 부족해 판단할 수 없습니다."
    med = change(test["median"], base["median"])
    ex3 = change(test["mean_ex_top3"], base["mean_ex_top3"])
    msg = []
    if med is not None and ex3 is not None:
        if med > SAME and ex3 > SAME:
            msg.append("보통 글 성적이 올랐습니다 — 실험 방향이 맞을 가능성이 있습니다.")
        elif med < -SAME and ex3 < -SAME:
            msg.append("보통 글 성적이 더 떨어졌습니다 — 하락이 이어지고 있습니다.")
        else:
            msg.append("보통 글 성적은 비슷합니다(±15% 이내이거나 두 지표가 엇갈림).")
    if trend and base and trend["median"]:
        t = change(base["median"], trend["median"])
        msg.append(f"참고: 직전 주 → 기준 주 중간값 변화 {pct(t)}. 이 추세가 이어졌다면 실험 주도 같은 폭 움직였을 것입니다.")
    msg.append("한 주 대 한 주 비교라서 확정은 아닙니다. 2주 연속 같은 방향이면 믿을 만합니다.")
    return " ".join(msg)


def report_text(rs):
    s = {name: summarize(rs, *w) for name, w in WINDOWS.items()}
    lines = ["스레드 조회수 점검 (실험: 수요일 번호 중간 점검 글)", ""]
    for name, w in WINDOWS.items():
        x = s[name]
        head = f"[{name}] {w[0]:%m/%d}~{w[1]:%m/%d}"
        if not x:
            lines.append(f"{head}: 측정된 글 없음")
            continue
        lines.append(f"{head}: 글 {x['posts']}개(하루 {x['per_day']}) · 합계 {x['total']:,} · 평균 {x['mean']:,} · "
                     f"중간값 {x['median']:,} · 상위3 제외 평균 {x['mean_ex_top3']:,} · "
                     f"조회1천당 좋아요 {x['likes_1k']} 댓글 {x['replies_1k']}")
    b, t = s["기준 주"], s["실험 주"]
    if b and t:
        lines += ["", "기준 주 → 실험 주",
                  f"합계 {pct(change(t['total'], b['total']))} · 평균 {pct(change(t['mean'], b['mean']))} · "
                  f"중간값 {pct(change(t['median'], b['median']))} · 상위3 제외 {pct(change(t['mean_ex_top3'], b['mean_ex_top3']))}",
                  f"하루 글 수 {b['per_day']} → {t['per_day']} (유지 확인)"]
        ks = sorted(set(b["by_kind"]) | set(t["by_kind"]))
        lines.append("종류별 평균 조회수(기준 → 실험): " + " · ".join(
            f"{k} {b['by_kind'].get(k, (0, 0))[1]:,}→{t['by_kind'].get(k, (0, 0))[1]:,}" for k in ks))
    mids = [r for r in rs if r["id"].endswith("-mid") and r["id"].startswith("picks-")]
    sun = [r for r in rs if r["id"].endswith("-stats") and r["id"].startswith("picks-")][-2:]
    if mids:
        lines += ["", "수요일 중간 점검 글: " + " · ".join(f"{r['id']} {r['views']:,}회(좋아요 {r['likes']} 댓글 {r['replies']})" for r in mids[-2:])]
    if sun:
        lines.append("비교용 일요일 흐름 글: " + " · ".join(f"{r['id']} {r['views']:,}회" for r in sun))
    lines += ["", verdict(s["추세 확인(직전 주)"], b, t)]
    return "\n".join(lines)


def run(now, queue=None, state=None, write=True):
    state = state if state is not None else (json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {})
    if state.get("reported") or now.astimezone(KST) < REPORT_AT:
        return None
    queue = queue if queue is not None else json.loads(QUEUE.read_text(encoding="utf-8"))
    text = report_text(rows(queue))
    if write:
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "threads-check-2026-11-12.md").write_text(text + "\n", encoding="utf-8")
        STATE.write_text(json.dumps({**state, "reported": True, "reported_at": now.isoformat(timespec="seconds")},
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        publish.telegram("📊 " + text)
    return text


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--preview" in sys.argv:       # 지금 데이터로 미리 보기. 아무것도 저장·발송하지 않는다
        print(report_text(rows(json.loads(QUEUE.read_text(encoding="utf-8")))))
        sys.exit(0)
    now = datetime.datetime.now(datetime.timezone.utc)
    out = run(now)
    print(out if out else "아직 점검 시각 전이거나 이미 보냈음")
