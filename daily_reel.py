"""매일 1게임 릴스 (2026-11-05 유저 요청).

스레드에서 터진 글(일요일 흐름 정리 4~17천, 수요일 중간 점검 1.7만)의 공통점은 "번호를 그냥 주는 글"이 아니라
"닉네임 남기면 네 번호를 답글로 줌"이었다. 인스타도 같은 구조로: 3초 훅 → 오늘의 1게임 공개 → 댓글·팔로우 유도.

앱 녹화 영상을 쓰지 않는다. 바탕 영상은 회차·천재가 바뀌어도 그대로라 자막과 화면이 어긋났다(534회 건).
번호를 화면에 직접 그리면 날마다 맞는 번호가 나오고, 사람이 다시 녹화할 일이 없다.

장면 (1080x1920, 30fps, 약 13초)
  0~3초   훅: "아르키메데스가 뽑은 / 1249회 번호" + 방식 한 줄. 공 6개는 '?'로 가려 둔다(끝까지 보게 하는 장치)
  3~6.6초 공이 하나씩 열린다(0.6초 간격, 튀어나오는 효과)
  ~9.5초  '오늘의 1게임'으로 잠깐 멈춘다
  ~13초   행동 유도: 댓글에 닉네임 → 네 1게임 답글 / 팔로우하면 매일 1게임
글자는 위 285px·아래 350px 밖(인스타 UI와 4:5 피드 자르기, social-media-skills 기준)에만 둔다.
"""

import datetime
import pathlib
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

import band_gen as bg
import cards as C
import lotto_gen as g

RW, RH, FPS = 1080, 1920, 30
KINDS = ("genius", "band")   # 이 모듈이 영상을 만드는 소재(평일 천재, 주말 번호대)
OUT = pathlib.Path(__file__).parent / "reels"
HOOK_SEC, STEP_SEC, HOLD_SEC, CTA_SEC = 3.0, 0.6, 2.9, 3.5
POP = (1.28, 1.16, 1.06, 1.0)          # 공이 열릴 때 크기 변화(프레임마다)
BALL_R, BALL_GAP, BALL_Y = 74, 14, 900


def josa(name):
    """'이/가'. 이름 끝 글자에 받침이 있으면 '이'."""
    ch = name[-1]
    if "가" <= ch <= "힣":
        return "이" if (ord(ch) - 0xAC00) % 28 else "가"
    return "이"


def today_game(kind, day):
    """(훅 1줄, 훅 2줄, 방식 설명, 번호 6개, 회차)."""
    draw_no = g.upcoming_draw_no(datetime.datetime.combine(day, datetime.time(12), C.KST))
    if kind == "genius":
        gi = g.GENIUSES[day.weekday()]
        nums = g.genius_games(gi["id"], draw_no)[0]
        return f"{gi['name']}{josa(gi['name'])} 뽑은", f"{draw_no}회 번호", gi["how"].replace("5게임", "1게임"), list(nums), draw_no
    games = bg.generate_daily_band_games(day.isoformat())
    return ("다섯 구간 중 하나를 비우고", f"뽑은 {draw_no}회 번호", "번호대 분석 · 저고 비율까지 맞춤",
            list(games[0]["numbers"]), draw_no)


def background():
    im = Image.new("RGB", (RW, RH), C.BG_TOP)
    d = ImageDraw.Draw(im)
    for y in range(RH):
        t = y / (RH - 1)
        d.line([(0, y), (RW, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(C.BG_TOP, C.BG_BOTTOM)))
    return im


def center(d, y, text, f, fill, stroke=0):
    w = d.textbbox((0, 0), text, font=f, stroke_width=stroke)[2]
    d.text(((RW - w) // 2, y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=(120, 14, 6))


def ball(d, cx, cy, r, n=None):
    if n is None:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255), outline=(255, 227, 176), width=6)
        f = C.font(int(r * 1.05), "black")
        t = "?"
        col = C.BG_BOTTOM
    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=C.ball_color(n))
        f = C.font(int(r * 0.95), "black")
        t = f"{n:02d}"
        col = C.WHITE
    bb = d.textbbox((0, 0), t, font=f)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]), t, font=f, fill=col)


def frame(lines, nums, opened, scale_last=1.0, label=None, cta=False):
    im = background()
    d = ImageDraw.Draw(im)
    l1, l2, how = lines
    center(d, 330, l1, C.font(92, "black"), C.WHITE, stroke=3)
    center(d, 450, l2, C.font(120, "black"), C.WHITE, stroke=4)
    center(d, 610, how, C.font(44, "bold"), C.CREAM)
    step = BALL_R * 2 + BALL_GAP
    x0 = RW // 2 - (step * 6 - BALL_GAP) // 2 + BALL_R
    for i in range(6):
        r = BALL_R
        if i == opened - 1:
            r = int(BALL_R * scale_last)
        ball(d, x0 + i * step, BALL_Y, r, nums[i] if i < opened else None)
    if label:
        center(d, BALL_Y + BALL_R + 60, label, C.font(54, "bold"), C.WHITE)
    if cta:
        d.rounded_rectangle([80, 1170, RW - 80, 1530], radius=40, fill=(255, 255, 255))
        center(d, 1215, "댓글에 '번호'라고 남기면", C.font(66, "black"), C.INK)
        center(d, 1305, "이번 주 1게임 답글로 줌", C.font(66, "black"), C.BG_BOTTOM)
        center(d, 1420, "팔로우하면 매일 1게임 올라옴", C.font(44, "bold"), C.MUTED)
    return im


def build(kind, day, out=None):
    l1, l2, how, nums, draw_no = today_game(kind, day)
    lines = (l1, l2, how)
    out = pathlib.Path(out) if out else OUT / f"daily-{kind}-{day.isoformat()}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        seq = []   # (파일, 초)

        def add(im, sec):
            p = td / f"f{len(seq):03d}.png"
            im.save(p)
            seq.append((p, sec))

        add(frame(lines, nums, 0, label="번호는 3초 뒤 공개"), HOOK_SEC)
        for k in range(1, 7):
            for s in POP:
                add(frame(lines, nums, k, s), 1 / FPS)
            add(frame(lines, nums, k), STEP_SEC - len(POP) / FPS)
        add(frame(lines, nums, 6, label="오늘의 1게임"), HOLD_SEC)
        add(frame(lines, nums, 6, label="오늘의 1게임", cta=True), CTA_SEC)
        lst = td / "list.txt"
        body = "".join(f"file '{p}'\nduration {sec:.4f}\n" for p, sec in seq) + f"file '{seq[-1][0]}'\n"
        lst.write_text(body, encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                        "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(out)],
                       check=True, capture_output=True)
    return out, nums, draw_no


def total_sec():
    return HOOK_SEC + 6 * STEP_SEC + HOLD_SEC + CTA_SEC


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    day = datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.date.today()
    print(build(sys.argv[1] if len(sys.argv) > 1 else "genius", day))
