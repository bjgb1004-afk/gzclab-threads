"""큐 데이터를 인스타용 JPEG 카드로 굽는다. 글(Threads)과 그림(인스타)을 같은 데이터로 낸다.

인스타 발행 API는 **JPEG만** 받고(PNG 거부), 파일 업로드가 아니라 공개 URL만 받는다.
그래서 여기서 구운 파일을 GitHub Pages에 커밋해 그 URL을 넘긴다.

번호 공 색은 실제 로또 용지와 같다(1~10 노랑 … 41~45 초록). 글꼴·색·레이아웃을 고정해서
로고를 떼도 우리 것으로 보이게 한다 — 카드마다 스타일을 바꾸면 도달이 기억으로 안 쌓인다.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).parent
FONT = HERE / "assets" / "NotoSansKR-Bold.otf"

W, H = 1080, 1350          # 4:5. 인스타 피드에서 세로로 가장 크게 잡히는 비율
BG = (14, 18, 28)
FG = (255, 255, 255)
DIM = (150, 160, 178)
ACCENT = (255, 209, 77)

# 로또 용지와 같은 구간 색. 노랑·초록은 흰 글씨가 안 보여서 글자만 검게 쓴다.
BALLS = (
    (10, (251, 196, 0), (26, 26, 26)),
    (20, (105, 200, 242), FG),
    (30, (255, 114, 114), FG),
    (40, (170, 170, 170), FG),
    (45, (176, 216, 64), (26, 26, 26)),
)


def ball_style(n):
    for hi, fill, text in BALLS:
        if n <= hi:
            return fill, text
    raise ValueError(n)


def font(size):
    return ImageFont.truetype(str(FONT), size)


def canvas():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def draw_balls(d, nums, cy, r=62, gap=16):
    """번호 6개를 가로 한 줄로. 공 크기는 6개가 가로폭에 맞게 정해둔 값이다."""
    total = len(nums) * (2 * r) + (len(nums) - 1) * gap
    x = (W - total) // 2 + r
    f = font(int(r * 0.9))
    for n in nums:
        fill, tc = ball_style(n)
        d.ellipse((x - r, cy - r, x + r, cy + r), fill=fill)
        d.text((x, cy + 2), f"{n:02d}", font=f, fill=tc, anchor="mm")
        x += 2 * r + gap


def footer(d):
    d.text((W // 2, H - 72), "복권명당  ·  @gzclab", font=font(34), fill=DIM, anchor="mm")


def big_number(d, value, unit, cy):
    """카드 한 장에 숫자 하나. 그 숫자가 제일 크다."""
    f_num, f_unit = font(300), font(76)
    wn = d.textlength(value, font=f_num)
    wu = d.textlength(unit, font=f_unit)
    x = (W - (wn + wu + 16)) // 2
    d.text((x, cy), value, font=f_num, fill=ACCENT, anchor="lm")
    d.text((x + wn + 16, cy + 90), unit, font=f_unit, fill=ACCENT, anchor="lm")


def replay_card(nums, hits, draws, net_text, best_text):
    """놓친 당첨금: 이 번호가 지나간 회차에서 몇 번 등수에 들었나."""
    img, d = canvas()
    d.text((W // 2, 150), "이 번호를 1회차부터 전부 돌리면", font=font(48), fill=DIM, anchor="mm")
    big_number(d, str(hits), "번 당첨", 400)
    d.text((W // 2, 600), f"{draws}회 중", font=font(44), fill=DIM, anchor="mm")
    draw_balls(d, nums, 760)
    d.text((W // 2, 960), f"세후 다 합쳐서 {net_text}", font=font(54), fill=FG, anchor="mm")
    d.text((W // 2, 1040), best_text, font=font(44), fill=DIM, anchor="mm")
    d.text((W // 2, 1170), "지나간 회차 기록임. 다음 회차랑은 상관없음", font=font(38), fill=DIM, anchor="mm")
    footer(d)
    return img


def top5_card(district, shops):
    """구별 1등 배출 순위. 1위 숫자가 주인공이다."""
    img, d = canvas()
    d.text((W // 2, 140), district, font=font(84), fill=FG, anchor="mm")
    d.text((W // 2, 230), "1등 제일 많이 나온 집", font=font(46), fill=DIM, anchor="mm")
    big_number(d, str(shops[0]["first"]), "회", 430)
    d.text((W // 2, 640), shops[0]["name"], font=font(66), fill=ACCENT, anchor="mm")
    y = 800
    for i, s in enumerate(shops[1:4], start=2):
        d.text((150, y), f"{i}", font=font(52), fill=DIM, anchor="lm")
        d.text((230, y), s["name"], font=font(52), fill=FG, anchor="lm")
        d.text((W - 150, y), f"{s['first']}회", font=font(52), fill=DIM, anchor="rm")
        y += 100
    d.text((W // 2, 1170), "지금까지 1등 나온 횟수임", font=font(38), fill=DIM, anchor="mm")
    footer(d)
    return img


def picks_card(title, subtitle, games, note="앱에서 뽑은 번호랑 한 자도 안 틀림"):
    """천재 번호·번호대 번호 카드. 게임이 여러 줄이면 그대로 여러 줄로 그린다."""
    img, d = canvas()
    d.text((W // 2, 180), title, font=font(96), fill=FG, anchor="mm")
    d.text((W // 2, 290), subtitle, font=font(48), fill=DIM, anchor="mm")
    rows = games if games and isinstance(games[0], (list, tuple)) else [games]
    y = 450 if len(rows) > 1 else 640
    for row in rows[:5]:
        draw_balls(d, row, y, r=56 if len(rows) > 1 else 72, gap=14)
        y += 140 if len(rows) > 1 else 0
    d.text((W // 2, 1170), note, font=font(44), fill=DIM, anchor="mm")
    footer(d)
    return img


def save(img, path, quality=88):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=quality, optimize=True)
    return path


def main(argv=()):
    """미리보기: python cards.py [출력폴더]"""
    out = pathlib.Path(argv[0]) if argv else HERE / "preview"
    samples = [
        ("replay.jpg", replay_card([2, 11, 25, 35, 38, 41], 21, 1243, "15만원", "제일 잘 나온 건 576회 4등")),
        ("top5.jpg", top5_card("서울 노원구", [
            {"name": "동일복권", "first": 52}, {"name": "로또방", "first": 8},
            {"name": "복권나라", "first": 6}, {"name": "행운상회", "first": 5},
        ])),
        ("picks.jpg", picks_card("아르키메데스", "원주율에서 뽑은 월요일 번호", [
            [3, 18, 19, 27, 30, 38], [1, 24, 25, 29, 38, 41], [6, 9, 11, 31, 37, 39],
            [1, 4, 11, 12, 39, 40], [10, 18, 19, 35, 37, 42],
        ])),
    ]
    for name, img in samples:
        p = save(img, out / name)
        assert p.stat().st_size > 10_000, p          # 빈 그림이 나오면 글꼴부터 깨진 것이다
        assert Image.open(p).size == (W, H)
        print(f"{p}  {p.stat().st_size // 1024}KB")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
