"""產生網站圖示：favicon.svg、favicon-32.png、apple-touch-icon.png（疊放題卡）。
用法：py tools/make_icons.py（需要 Pillow）

三張題卡往右上錯位、偏移量遞增，並逐張多轉一點（越刷越進步）。
favicon.svg 透明底：縫隙用 mask 挖空，顏色隨淺色／深色模式切換（最上面那張淺色模式黑、深色模式白）。
兩個 PNG 不能隨模式換色，一律用淺色模式的配色，與電腦版分頁看到的一致：
favicon-32.png 透明底、比例同 SVG；apple-touch-icon 白色滿版方形（iOS 會把透明處填黑），
圖形縮小留邊，避免被 iOS 切的圓角裁到。
"""
import math, os, sys
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, R = 216, 268, 38                                 # 題卡大小與圓角（512 畫布）
CARDS = [(96, 186, 0), (142, 150, 5), (202, 100, 11)]  # x, y, 旋轉角度，由後往前
GAP = 16                                               # 卡片之間的縫隙（SVG 描邊寬）
CX, CY = 257, 277                                      # 整組的中心，移到畫布中央
SCALE = 1.22                                           # favicon.svg／favicon-32.png：放大填滿畫布
TOUCH_SCALE, TOUCH_BG = 1.0, "#FFFFFF"                 # apple-touch-icon：留邊、白底
CLEAR = f"translate(256 256) scale({SCALE}) translate(-{CX} -{CY})"
LIGHT = ["#ABABAB", "#8A8A8A", "#111111"]              # 淺色模式（PNG 也用這組）
DARK = ["#4A4A4A", "#9A9A9A", "#FFFFFF"]               # 深色模式（只有 SVG）


def svg():
    rect = lambda x, y, a, extra: (f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="{R}" '
                                   f'transform="rotate({a} {x + W / 2:g} {y + H / 2:g})" {extra}/>')
    s = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><style>'
         + "".join(f".c{i}{{fill:{c}}}" for i, c in enumerate(LIGHT))
         + "@media (prefers-color-scheme:dark){" + "".join(f".c{i}{{fill:{c}}}" for i, c in enumerate(DARK)) + "}"
         + "</style><defs>")
    for i in range(len(CARDS) - 1):                    # 第 i 張被它前面的卡片挖出縫隙
        s += ('<mask id="m%d" maskUnits="userSpaceOnUse" x="-200" y="-200" width="900" height="900">'
              '<rect x="-200" y="-200" width="900" height="900" fill="#fff"/>' % i)
        s += "".join(rect(x, y, a, f'fill="#000" stroke="#000" stroke-width="{GAP * 2}"') for x, y, a in CARDS[i + 1:])
        s += "</mask>"
    s += f'</defs><g transform="{CLEAR}">'
    for i, (x, y, a) in enumerate(CARDS):
        s += rect(x, y, a, f'class="c{i}"' + (f' mask="url(#m{i})"' if i < len(CARDS) - 1 else ""))
    return s + "</g></svg>\n"


def rrect(x, y, w, h, r, ang, cx, cy, n=24):
    """圓角矩形的多邊形頂點，繞 (cx, cy) 旋轉 ang 度（順時針，同 SVG）。"""
    pts = []
    for ox, oy, a0 in [(x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)]:
        for i in range(n + 1):
            t = math.radians(a0 + 90 * i / n)
            pts.append((ox + r * math.cos(t), oy + r * math.sin(t)))
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + (px - cx) * c - (py - cy) * s, cy + (px - cx) * s + (py - cy) * c) for px, py in pts]


def png(size, scale, bg):
    """bg=None 為透明底。縫隙做法同 SVG 的 mask：每張卡先把外擴 GAP 的範圍塗回底色，再畫卡片。"""
    S = 8 * size                                       # 8 倍超取樣後縮小
    k = S / 512
    clear = (0, 0, 0, 0) if bg is None else bg
    img = Image.new("RGBA", (S, S), clear)
    d = ImageDraw.Draw(img)                            # 不混色：塗透明會直接挖空
    sc = lambda P: [((256 + scale * (px - CX)) * k, (256 + scale * (py - CY)) * k) for px, py in P]
    for (x, y, a), f in zip(CARDS, LIGHT):
        cx, cy = x + W / 2, y + H / 2
        d.polygon(sc(rrect(x - GAP, y - GAP, W + 2 * GAP, H + 2 * GAP, R + GAP, a, cx, cy)), fill=clear)
        d.polygon(sc(rrect(x, y, W, H, R, a, cx, cy)), fill=f)
    return img.convert("RGBa").resize((size, size), Image.LANCZOS).convert("RGBA")


if __name__ == "__main__":
    open(os.path.join(ROOT, "favicon.svg"), "w", encoding="utf-8", newline="\n").write(svg())
    png(32, SCALE, None).save(os.path.join(ROOT, "favicon-32.png"), optimize=True)
    png(180, TOUCH_SCALE, TOUCH_BG).convert("RGB").save(os.path.join(ROOT, "apple-touch-icon.png"), optimize=True)
    print("已更新 favicon.svg、favicon-32.png、apple-touch-icon.png")
