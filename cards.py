"""인스타 카드(JPEG) 렌더러. 평일 하루 2장 — 천재 번호, 무작위 번호 되짚어보기.

인스타그램 API는 JPEG만 받고(PNG 거부) 피드 최대 비율이 4:5라 1080x1350으로 낸다.
색과 글꼴 크기는 Play 스토어 스크린샷(assets/images/screenshots)에서 뽑아 맞췄다.
같은 계정에 섞여 나가도 따로 놀지 않게 하기 위한 것이다.

번호는 lotto_gen에서 가져온다. 천재 번호는 (회차, 천재)로 고정이라 앱·스레드·인스타가
모두 같은 번호를 내야 한다 — 여기서 따로 뽑으면 안 된다.
"""

import datetime
import pathlib

from PIL import Image, ImageDraw, ImageFont

import band_gen as bg
import lotto_gen as g
import replay as rp

HERE = pathlib.Path(__file__).parent
OUT = HERE / "cards"

W, H = 1080, 1350  # 4:5. 인스타 피드가 받는 가장 긴 세로 비율

# 스토어 스크린샷에서 뽑은 그라데이션 양끝. 위가 밝고 아래로 갈수록 진해진다.
BG_TOP = (252, 94, 67)
BG_BOTTOM = (199, 22, 11)
CREAM = (255, 227, 176)   # 보조 헤드라인
WHITE = (255, 255, 255)
CARD_BG = (255, 255, 255)
INK = (34, 30, 28)
MUTED = (122, 114, 110)

# 로또 공 색(동행복권 표기와 같은 구간)
BALL = ((10, (251, 196, 60)), (20, (90, 160, 232)), (30, (233, 90, 86)),
        (40, (140, 140, 148)), (45, (90, 190, 130)))

FONT_DIR = "/usr/share/fonts/opentype/noto"
# Actions 러너에는 CJK 글꼴이 없을 수 있다. 워크플로에서 fonts-noto-cjk를 깔고,
# 그래도 없으면 여기서 바로 죽게 둔다 — 글자가 두부(□)로 나간 카드가 발행되는 것보다 낫다.
FONT_CANDIDATES = (
    f"{FONT_DIR}/NotoSansCJK-Black.ttc",
    f"{FONT_DIR}/NotoSansCJK-Bold.ttc",
    f"{FONT_DIR}/NotoSansCJK-Regular.ttc",
)
# 러너에 CJK 글꼴이 없으면(또는 apt 설치가 실패하면) 저장소에 든 이 파일로 떨어진다.
# 굵기 구분은 사라지지만 카드는 나간다.
FONT_FALLBACK = str(HERE / "assets" / "NotoSansKR-Bold.otf")


def font(size, weight="bold"):
    want = {"black": 0, "bold": 1, "regular": 2}[weight]
    order = ([FONT_CANDIDATES[want]]
             + [f for i, f in enumerate(FONT_CANDIDATES) if i != want]
             + [FONT_FALLBACK])
    for path in order:
        if pathlib.Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    raise RuntimeError("한글 글꼴을 찾지 못했습니다 — fonts-noto-cjk를 설치하세요")


def ball_color(n):
    for hi, c in BALL:
        if n <= hi:
            return c
    return BALL[-1][1]


def gradient():
    im = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(
            round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return im


def center(d, y, text, f, fill):
    w = d.textbbox((0, 0), text, font=f)[2]
    d.text(((W - w) // 2, y), text, font=f, fill=fill)
    return d.textbbox((0, 0), text, font=f)[3]


def draw_balls(d, cx, y, nums, r=34, gap=14):
    """번호 6개를 가로로. cx는 중심 x."""
    step = r * 2 + gap
    total = step * len(nums) - gap
    x = start = cx - total // 2
    f = font(int(r * 1.0), "bold")
    for n in nums:
        d.ellipse([x, y, x + r * 2, y + r * 2], fill=ball_color(n))
        t = f"{n:02d}"
        bb = d.textbbox((0, 0), t, font=f)
        d.text((x + r - bb[2] / 2, y + r - bb[3] / 2 - bb[1] / 2), t, font=f, fill=WHITE)
        x += step
    return start


def panel(im, d, top, height, pad=56):
    d.rounded_rectangle([pad, top, W - pad, top + height], radius=36, fill=CARD_BG)
    return top + height


def footer(d):
    f = font(30, "bold")
    t = "복권명당 · 로또 당첨확인 · 명당 지도"
    w = d.textbbox((0, 0), t, font=f)[2]
    d.text(((W - w) // 2, H - 72), t, font=f, fill=(255, 255, 255, 220))


# ---------- 카드 1: 천재들의 한수 ----------

def genius_card(draw_no, genius_id):
    gi = g.GENIUS_BY_ID[genius_id]
    games = g.genius_games(genius_id, draw_no)
    im = gradient()
    d = ImageDraw.Draw(im)

    center(d, 70, f"{draw_no}회 · {gi['name']}", font(58, "black"), WHITE)
    center(d, 150, gi["how"], font(32, "bold"), CREAM)

    top = 226
    panel(im, d, top, 900)
    y = top + 70
    letters = "ABCDE"
    fl = font(36, "bold")
    for i, game in enumerate(games):
        start = draw_balls(d, W // 2 + 26, y, game)
        d.text((start - 76, y + 16), letters[i], font=fl, fill=MUTED)
        y += 162
    center(d, top + 830, "앱에서 뽑아도 같은 번호가 나옵니다", font(27, "regular"), MUTED)

    footer(d)
    return im


# ---------- 카드 2: 무작위 번호 되짚어보기 ----------

def replay_card(nums, res, label="오늘의 무작위 번호"):
    im = gradient()
    d = ImageDraw.Draw(im)

    center(d, 70, label, font(52, "black"), WHITE)
    center(d, 146, f"{res['from']}회부터 {res['to']}회까지 돌려봤습니다", font(30, "bold"), CREAM)

    top = 226
    panel(im, d, top, 900)

    draw_balls(d, W // 2, top + 64, nums, r=44, gap=18)

    y = top + 236
    d.line([(140, y), (W - 140, y)], fill=(235, 231, 228), width=3)

    if res["hits"]:
        center(d, y + 46, f"{res['hits']}번 당첨", font(76, "black"), INK)
        rows = [(f"{r}등", f"{res['by_rank'][r]}번") for r in sorted(res["by_rank"])]
        ry = y + 182
        fk, fv = font(34, "regular"), font(36, "bold")
        for k, v in rows:
            d.text((190, ry), k, font=fk, fill=MUTED)
            vb = d.textbbox((0, 0), v, font=fv)[2]
            d.text((W - 190 - vb, ry - 2), v, font=fv, fill=INK)
            ry += 66
        d.line([(190, ry + 10), (W - 190, ry + 10)], fill=(235, 231, 228), width=2)
        d.text((190, ry + 40), "받았을 돈", font=fk, fill=MUTED)
        amt = rp.won(res["gross"])
        ab = d.textbbox((0, 0), amt, font=font(46, "black"))[2]
        d.text((W - 190 - ab, ry + 26), amt, font=font(46, "black"), fill=(210, 48, 32))
    else:
        center(d, y + 90, "한 번도 등수에 못 들었습니다", font(50, "black"), INK)

    center(d, top + 834, "지나간 회차 성적이라 다음 회차와는 무관합니다", font(25, "regular"), MUTED)
    footer(d)
    return im


# ---------- 무작위 번호 (날짜로 고정) ----------

def daily_random(day):
    """그날의 번호 1게임. 앱 번호대 분석의 A게임을 쓴다 — 앱에서 같은 날 열어도 같은 번호다.

    예전에는 여기서 따로 뽑았는데, 그러면 카드에 찍힌 번호를 앱에서 확인할 방법이 없다.
    """
    return bg.generate_daily_band_games(day.isoformat(), 1)[0]["numbers"]


def save_jpg(im, name):
    OUT.mkdir(exist_ok=True)
    p = OUT / f"{name}.jpg"
    im.convert("RGB").save(p, "JPEG", quality=90, optimize=True, progressive=False)
    return p


# ---------- 카드 3: 번호대 분석 ----------

def band_card(date_key, games):
    im = gradient()
    d = ImageDraw.Draw(im)
    center(d, 70, "오늘의 번호대 분석", font(56, "black"), WHITE)
    center(d, 150, "한 구간은 비우고 · 한 구간 최대 3개 · 저고 2:4 / 3:3 / 4:2", font(26, "bold"), CREAM)

    top = 226
    panel(im, d, top, 900)
    y = top + 62
    fs = font(24, "regular")
    for i, gm in enumerate(games):
        start = draw_balls(d, W // 2 + 26, y, gm["numbers"], r=32, gap=12)
        d.text((start - 70, y + 14), "ABCDE"[i], font=font(34, "bold"), fill=MUTED)
        d.text((start, y + 76), f"{gm['band_pattern']} · 저고 {gm['low_high']}", font=fs, fill=MUTED)
        y += 162
    center(d, top + 834, "통계 참고용이며 당첨 확률을 높여주지 않습니다", font(25, "regular"), MUTED)
    footer(d)
    return im


# ---------- 하루치 카드 만들기 ----------

KST = datetime.timezone(datetime.timedelta(hours=9))
KINDS = ("genius", "replay", "band")


def card_name(kind, day):
    """파일명. instagram_publish가 같은 이름으로 주소를 만들므로 여기 한 곳에서만 정한다."""
    if kind == "genius":
        draw_no = g.upcoming_draw_no(datetime.datetime.combine(day, datetime.time(12), KST))
        return f"genius-{draw_no}-{g.GENIUSES[day.weekday()]['id']}"
    if kind in ("replay", "band"):
        return f"{kind}-{day.isoformat()}"
    raise ValueError(kind)


def build_one(kind, day, draws=None):
    """카드 한 장. 이미 있으면 다시 그리지 않는다 — tick이 5분마다 부른다."""
    name = card_name(kind, day)
    out = OUT / f"{name}.jpg"
    if out.exists():
        return out
    draws = draws if draws is not None else rp.fetch_draws()
    if kind == "genius":
        draw_no = g.upcoming_draw_no(datetime.datetime.combine(day, datetime.time(12), KST))
        im = genius_card(draw_no, g.GENIUSES[day.weekday()]["id"])
    elif kind == "replay":
        nums = daily_random(day)
        im = replay_card(nums, rp.replay(nums, draws))
    else:
        key = day.isoformat()
        im = band_card(key, bg.generate_daily_band_games(key))
    return save_jpg(im, name)


def build_day(day, draws=None):
    """그날 쓸 카드를 전부. 천재 시리즈는 월~금만 있다."""
    draws = draws if draws is not None else rp.fetch_draws()
    kinds = KINDS if day.weekday() < 5 else tuple(k for k in KINDS if k != "genius")
    return [build_one(k, day, draws) for k in kinds]


if __name__ == "__main__":
    import sys

    argv = sys.argv[1:]
    days = 1
    if "--build" in argv:
        i = argv.index("--build")
        days = int(argv[i + 1]) if i + 1 < len(argv) else 1
    start = datetime.date.today()
    draws = rp.fetch_draws()
    out = []
    for n in range(days):
        out += build_day(start + datetime.timedelta(days=n), draws)
    print(f"{len(out)}장 생성 -> {OUT}")
    for p in out:
        print(" ", p.name)
