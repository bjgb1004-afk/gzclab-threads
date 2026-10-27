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


def footer(d, text="@gzclab · 복권명당"):
    """바닥은 계정만. 예전엔 '복권명당 · 로또 당첨확인 · 명당 지도'라는 기능 나열이었는데,
    그건 광고 문구지 콘텐츠가 아니다(2026-10-27)."""
    f = font(34, "bold")
    w = d.textbbox((0, 0), text, font=f)[2]
    d.text(((W - w) // 2, H - 96), text, font=f, fill=(255, 255, 255))


def wrap(d, text, f, maxw):
    """글자 폭 기준 줄바꿈. 한국어는 띄어쓰기 단위로 끊어도 충분히 자연스럽다."""
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def hook_block(d, hook, sub, top=112, size=78, maxw=W - 150):
    """카드 맨 위 훅. 섬네일로 줄여도 읽히는 크기여야 한다 — 피드에서 이 글자가 전부다.

    예전 카드는 맨 위가 '1245회 · 아르키메데스'(회차와 이름)였다. 그건 훅이 아니라
    꼬리표다. 소재가 가진 제일 이상한 사실을 제일 큰 글자로 올린다.
    돌려주는 값은 다음 요소를 놓을 y 좌표.
    """
    f = font(size, "black")
    lines = wrap(d, hook, f, maxw)
    # 세 줄을 넘으면 글자를 줄여 다시 짠다. 넘치는 채로 그리면 패널을 덮는다.
    while len(lines) > 3 and size > 48:
        size -= 8
        f = font(size, "black")
        lines = wrap(d, hook, f, maxw)
    y = top
    for ln in lines:
        center(d, y, ln, f, WHITE)
        y += int(size * 1.18)
    if sub:
        center(d, y + 16, sub, font(44, "bold"), CREAM)
        y += 94
    return y + 36


# ---------- 카드 1: 천재들의 한수 ----------

def genius_card(draw_no, genius_id):
    gi = g.GENIUS_BY_ID[genius_id]
    games = g.genius_games(genius_id, draw_no)
    im = gradient()
    d = ImageDraw.Draw(im)

    top = hook_block(d, gi["how"].replace(" 5게임", ""), f"{draw_no}회 · {gi['name']}")

    rows_h = 104 * len(games)
    panel_h = rows_h + 130
    panel(im, d, top, panel_h)
    y = top + 64
    fl = font(40, "bold")
    for i, game in enumerate(games):
        d.text((112, y + 10), "ABCDE"[i], font=fl, fill=MUTED)
        draw_balls(d, W // 2 + 24, y, game, r=42, gap=16)
        y += 104
    center(d, top + panel_h - 58, "앱에서 뽑아도 같은 번호가 나옵니다", font(28, "regular"), MUTED)

    footer(d)
    return im


# ---------- 카드 2: 무작위 번호 되짚어보기 ----------

def replay_card(nums, res, label="오늘의 무작위 번호"):
    """'놓친 당첨금'은 결과 자체가 훅이다. 번호보다 결과를 먼저, 크게 쓴다."""
    im = gradient()
    d = ImageDraw.Draw(im)

    if res["hits"]:
        hook = f"이 번호, {res['draws']}회를 돌려보니 {res['hits']}번 당첨돼 있었습니다"
    else:
        hook = f"이 번호는 {res['draws']}회 동안 한 번도 안 걸렸습니다"
    top = hook_block(d, hook, label)

    # 패널 높이를 등수 줄 수에 맞춘다. 고정값을 쓰면 2줄짜리 주에 아래가 텅 빈다.
    #   공 148 + 구분선 48 + 등수줄 70n + 합계 116 + 각주 자리 80
    n_rows = len(res["by_rank"]) if res["hits"] else 0
    panel_h = (436 + 70 * n_rows) if res["hits"] else 420
    panel(im, d, top, panel_h)

    draw_balls(d, W // 2, top + 56, nums, r=46, gap=18)
    y = top + 196
    d.line([(140, y), (W - 140, y)], fill=(235, 231, 228), width=3)

    if res["hits"]:
        rows = [(f"{r}등", f"{res['by_rank'][r]}번") for r in sorted(res["by_rank"])]
        ry = y + 44
        fk, fv = font(36, "regular"), font(38, "bold")
        for k, v in rows:
            d.text((190, ry), k, font=fk, fill=MUTED)
            vb = d.textbbox((0, 0), v, font=fv)[2]
            d.text((W - 190 - vb, ry - 2), v, font=fv, fill=INK)
            ry += 70
        d.line([(190, ry + 12), (W - 190, ry + 12)], fill=(235, 231, 228), width=2)
        d.text((190, ry + 46), "받았을 돈", font=fk, fill=MUTED)
        amt = rp.won(res["gross"])
        fa = font(56, "black")
        ab = d.textbbox((0, 0), amt, font=fa)[2]
        d.text((W - 190 - ab, ry + 32), amt, font=fa, fill=(210, 48, 32))
    else:
        center(d, y + 70, "이런 번호도 드뭅니다", font(52, "black"), INK)

    center(d, top + panel_h - 56, "지나간 회차 성적이라 다음 회차와는 무관합니다",
           font(26, "regular"), MUTED)
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
    top = hook_block(d, "다섯 구간 중 한 곳은 일부러 비웠습니다", "오늘의 번호대 분석")

    rows_h = 150 * len(games)
    panel_h = rows_h + 140
    panel(im, d, top, panel_h)
    y = top + 58
    fs = font(26, "regular")
    for i, gm in enumerate(games):
        start = draw_balls(d, W // 2 + 24, y, gm["numbers"], r=34, gap=13)
        d.text((start - 74, y + 16), "ABCDE"[i], font=font(36, "bold"), fill=MUTED)
        d.text((start, y + 80), f"{gm['band_pattern']} · 저고 {gm['low_high']}", font=fs, fill=MUTED)
        y += 150
    center(d, top + panel_h - 58, "통계 참고용이며 당첨 확률을 높여주지 않습니다",
           font(26, "regular"), MUTED)
    footer(d)
    return im


# ---------- 캐러셀 슬라이드 ----------
# 왜 캐러셀인가 (2026-10-27 조사): 도달 1명당 참여가 캐러셀 쪽이 단일 이미지보다 크게
# 높다. 한 장짜리는 넘기면 끝이지만 여러 장이면 넘기는 동작 자체가 체류 시간이 된다.
#
# 세 장으로 고정한다 — 1장 훅(표지), 2장 알맹이, 3장 안내.
# 1장이 표지이자 섬네일이라 여기서 멈추게 하지 못하면 2·3장은 아무도 안 본다.


def hook_slide(hook, sub=None):
    """표지. 글자만 크게. 읽을 거리를 늘리면 섬네일에서 뭉개진다."""
    im = gradient()
    d = ImageDraw.Draw(im)
    f = font(96, "black")
    lines = wrap(d, hook, f, W - 130)
    size = 96
    while len(lines) > 4 and size > 56:
        size -= 8
        f = font(size, "black")
        lines = wrap(d, hook, f, W - 130)
    block = len(lines) * int(size * 1.2)
    y = (H - block) // 2 - (70 if sub else 0)
    for ln in lines:
        center(d, y, ln, f, WHITE)
        y += int(size * 1.2)
    if sub:
        center(d, y + 30, sub, font(46, "bold"), CREAM)
    center(d, H - 150, "넘겨서 번호 보기 →", font(40, "bold"), CREAM)
    footer(d)
    return im


def cta_slide(headline="번호는 매일 올립니다", note=None):
    """마지막 장. 저장·팔로우를 청하고 앱을 알린다. 광고 문구는 여기 한 장에만 둔다."""
    im = gradient()
    d = ImageDraw.Draw(im)
    center(d, 250, headline, font(76, "black"), WHITE)

    top, panel_h = 430, 560
    panel(im, d, top, panel_h)
    y = top + 80
    for line in ("저장해두고 번호 살 때 꺼내 보세요.",
                 "매일 올라오니 팔로우해두면 안 놓칩니다.",
                 "지난 회차로 내 번호 돌려보는 건",
                 "복권명당 앱 '놓친 당첨금'에서 됩니다."):
        center(d, y, line, font(38, "bold"), INK)
        y += 72
    if note:
        center(d, y + 20, note, font(28, "regular"), MUTED)

    center(d, top + panel_h + 70, "프로필 링크에 앱 주소가 있습니다", font(34, "bold"), CREAM)
    footer(d)
    return im


def slide_hook(kind, day, draws=None):
    """소재별 표지 문구 (훅, 보조). 카드 본문과 같은 문장을 쓴다 — 따로 지어내지 않는다."""
    if kind == "genius":
        draw_no = g.upcoming_draw_no(datetime.datetime.combine(day, datetime.time(12), KST))
        gi = g.GENIUS_BY_ID[g.GENIUSES[day.weekday()]["id"]]
        return gi["how"].replace(" 5게임", ""), f"{draw_no}회 · {gi['name']}"
    if kind == "replay":
        nums = daily_random(day)
        res = rp.replay(nums, draws if draws is not None else rp.fetch_draws())
        if res["hits"]:
            return f"{res['draws']}회를 돌려보니 {res['hits']}번 당첨돼 있었습니다", "오늘의 무작위 번호"
        return f"{res['draws']}회 동안 한 번도 안 걸린 번호", "오늘의 무작위 번호"
    return "다섯 구간 중 한 곳은 일부러 비웠습니다", "오늘의 번호대 분석"


def build_slides(kind, day, draws=None):
    """캐러셀 3장의 경로. 이미 있으면 다시 그리지 않는다(tick이 5분마다 부른다)."""
    draws = draws if draws is not None else rp.fetch_draws()
    base = card_name(kind, day)
    body = build_one(kind, day, draws)

    hook_path = OUT / f"{base}-hook.jpg"
    if not hook_path.exists():
        hook, sub = slide_hook(kind, day, draws)
        save_jpg(hook_slide(hook, sub), f"{base}-hook")

    cta_path = OUT / f"{base}-cta.jpg"
    if not cta_path.exists():
        save_jpg(cta_slide(), f"{base}-cta")

    return [OUT / f"{base}-hook.jpg", body, OUT / f"{base}-cta.jpg"]


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
