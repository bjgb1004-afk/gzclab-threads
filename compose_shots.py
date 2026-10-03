"""앱 원본 캡처 → 스토어 스크린샷(1080x1920) + 인스타 카드(1080x1350).

치수는 기존 store-shot-01.png에서 직접 재서 맞췄다. 새로 만든 것이 기존 7장 사이에
섞여도 티가 나지 않아야 한다.

  캔버스 1080x1920 / 배경 그라데이션 (252,94,67) → (199,22,11)
  헤드라인 1줄 y 79~133 흰색, 2줄 y 150~204 크림(255,227,176), 글자 높이 55
  목업 카드 x 125~954(폭 830) · y 268~1875(높이 1608) · 모서리 반경 29

원본 캡처는 1080 폭이라 830으로 줄이면 높이가 1600 안팎이 되어 카드에 거의 딱 맞는다.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).parent
SRC = HERE / "shots"
OUT = HERE / "composed"

W, H = 1080, 1920
BG_TOP, BG_BOTTOM = (252, 94, 67), (199, 22, 11)
CREAM = (255, 227, 176)
WHITE = (255, 255, 255)

CARD_X, CARD_W = 125, 830
CARD_Y, CARD_H = 268, 1608
RADIUS = 29

LINE1_Y, LINE2_Y = 79, 150      # 글자 윗변
LINE_H = 55                      # 글자 높이(대문자 기준)

IG_W, IG_H = 1080, 1350          # 인스타 4:5

FONT_DIR = "/usr/share/fonts/opentype/noto"
FONT_CANDIDATES = (
    f"{FONT_DIR}/NotoSansCJK-Black.ttc",
    f"{FONT_DIR}/NotoSansCJK-Bold.ttc",
    f"{FONT_DIR}/NotoSansCJK-Regular.ttc",
)


def font_for(height, weight=0):
    """글자 높이가 주어진 값이 되도록 폰트 크기를 맞춘다."""
    path = next(p for p in FONT_CANDIDATES[weight:] + FONT_CANDIDATES
                if pathlib.Path(p).exists())
    size = int(height * 1.35)
    for _ in range(40):
        f = ImageFont.truetype(path, size)
        bb = f.getbbox("가나다ABC")
        h = bb[3] - bb[1]
        if abs(h - height) <= 1:
            return f
        size += 1 if h < height else -1
    return ImageFont.truetype(path, size)


def gradient(w, h):
    im = Image.new("RGB", (w, h), BG_TOP)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(
            round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return im


def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1],
                                           radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0))
    out.putalpha(mask)
    return out


def draw_center(d, y, text, f, fill):
    bb = d.textbbox((0, 0), text, font=f)
    d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], y - bb[1]), text, font=f, fill=fill)


def fit_card(shot, card_w, card_h):
    """캡처를 카드 폭에 맞춰 줄이고, 넘치면 아래를 자른다."""
    s = shot.convert("RGB")
    scale = card_w / s.width
    resized = s.resize((card_w, round(s.height * scale)), Image.LANCZOS)
    if resized.height > card_h:
        resized = resized.crop((0, 0, card_w, card_h))
    elif resized.height < card_h:
        pad = Image.new("RGB", (card_w, card_h), (255, 255, 255))
        pad.paste(resized, (0, 0))
        resized = pad
    return resized


def store_card(shot, line1, line2):
    im = gradient(W, H)
    d = ImageDraw.Draw(im)
    draw_center(d, LINE1_Y, line1, font_for(LINE_H, 0), WHITE)
    draw_center(d, LINE2_Y, line2, font_for(LINE_H, 0), CREAM)
    card = rounded(fit_card(shot, CARD_W, CARD_H), RADIUS)
    im.paste(card, (CARD_X, CARD_Y), card)
    return im


def insta_card(shot, line1, line2):
    """4:5. 캡처 윗부분만 보여주고 아래를 그라데이션으로 흘린다."""
    im = gradient(IG_W, IG_H)
    d = ImageDraw.Draw(im)
    draw_center(d, LINE1_Y, line1, font_for(LINE_H, 0), WHITE)
    draw_center(d, LINE2_Y, line2, font_for(LINE_H, 0), CREAM)
    card_h = IG_H - CARD_Y          # 바닥까지 꽉 채운다
    card = rounded(fit_card(shot, CARD_W, card_h), RADIUS)
    im.paste(card, (CARD_X, CARD_Y), card)
    return im


# 원본 파일명 → (스토어 1줄, 2줄)
SHOTS = {
    "replay-result": ("내 번호가 그동안", "몇 번 당첨됐는지"),
    "replay-picker": ("번호 6개만 고르면", "지난 회차를 전부 돌려봐요"),
    "band-analysis": ("구간을 따져서 뽑는", "오늘의 추천 5게임"),
    "genius-archimedes": ("수학자 다섯 명의 방식으로", "뽑은 번호 5게임"),
    "genius-fibonacci": ("황금비로 뽑는", "피보나치의 번호"),
    "genius-pascal": ("파스칼 삼각형에서", "꺼낸 번호"),
    "genius-euler": ("자연상수 e를 읽어", "만든 번호"),
    "genius-gauss": ("여섯 번호의 합을", "평균에 맞춘 조합"),
}


def main():
    OUT.mkdir(exist_ok=True)
    made = []
    for name, (l1, l2) in SHOTS.items():
        p = SRC / f"{name}.jpg"
        if not p.exists():
            print(f"건너뜀 (원본 없음): {name}")
            continue
        shot = Image.open(p)
        s = store_card(shot, l1, l2)
        sp = OUT / f"store-{name}.png"
        s.save(sp, "PNG", optimize=True)
        made.append(sp)

        i = insta_card(shot, l1, l2)
        ip = OUT / f"ig-{name}.jpg"
        i.convert("RGB").save(ip, "JPEG", quality=90, optimize=True)
        made.append(ip)
    print(f"{len(made)}장 생성 -> {OUT}")
    return made


if __name__ == "__main__":
    for p in main():
        print(" ", p.name)
