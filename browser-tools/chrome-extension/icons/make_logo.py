"""
DragonMeow MangaTranslator — logo generator.
Concept: fox-eared speech bubble (mascot + manga) holding a 文 glyph (translation),
on a teal gradient rounded square (brand color).
Renders at 4x supersample, downscales with LANCZOS for crisp icons.
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 1024  # master canvas size
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- palette ----
TEAL_TOP    = (40, 184, 165)   # #28B8A5
TEAL_BOT    = (12, 104, 96)    # #0C6860
GLYPH_TEAL  = (13, 110, 100)   # #0D6E64
WHITE       = (255, 255, 255)
CREAM       = (255, 252, 246)
EAR_INNER   = (255, 173, 165)  # soft peach/pink
BLUSH       = (255, 158, 150)

def rrect(draw, box, r, **kw):
    draw.rounded_rectangle(box, radius=r, **kw)

# ---------- background: teal vertical gradient, rounded-square masked ----------
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

grad = Image.new("RGB", (1, S))
for y in range(S):
    t = y / (S - 1)
    grad.putpixel((0, y), tuple(
        int(TEAL_TOP[i] + (TEAL_BOT[i] - TEAL_TOP[i]) * t) for i in range(3)))
grad = grad.resize((S, S))

mask = Image.new("L", (S, S), 0)
rrect(ImageDraw.Draw(mask), (0, 0, S - 1, S - 1), r=int(S * 0.205), fill=255)
img.paste(grad, (0, 0), mask)

# subtle top sheen
sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(sheen).ellipse((-S*0.3, -S*0.75, S*1.3, S*0.45),
                              fill=(255, 255, 255, 28))
img.alpha_composite(Image.composite(sheen, Image.new("RGBA", (S, S), (0,0,0,0)), mask))

draw = ImageDraw.Draw(img)

# ---------- geometry ----------
cx = S // 2
# bubble body
bx0, by0, bx1, by1 = int(S*0.165), int(S*0.315), int(S*0.835), int(S*0.735)
br = int(S * 0.16)

# ---------- soft drop shadow ----------
shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(shadow)
rrect(sd, (bx0, by0 + int(S*0.03), bx1, by1 + int(S*0.03)), r=br, fill=(0, 0, 0, 95))
# ear shadows
def ear_pts(cx_e, tip_dx):
    base_y = by0 + int(S*0.045)
    return [(cx_e - int(S*0.105), base_y),
            (cx_e + int(S*0.105), base_y),
            (cx_e + tip_dx, int(S*0.165))]
sd.polygon(ear_pts(int(S*0.325), -int(S*0.05)), fill=(0, 0, 0, 95))
sd.polygon(ear_pts(int(S*0.675), int(S*0.05)), fill=(0, 0, 0, 95))
shadow = shadow.filter(ImageFilter.GaussianBlur(S * 0.022))
img.alpha_composite(shadow)

# ---------- fox ears (drawn before bubble so bubble overlaps their base) ----------
def draw_ear(cx_e, tip_dx):
    base_y = by0 + int(S*0.075)
    outer = [(cx_e - int(S*0.110), base_y),
             (cx_e + int(S*0.110), base_y),
             (cx_e + tip_dx,       int(S*0.165))]
    draw.polygon(outer, fill=CREAM)
    # inner ear
    inner = [(cx_e - int(S*0.055), base_y - int(S*0.010)),
             (cx_e + int(S*0.055), base_y - int(S*0.010)),
             (cx_e + int(tip_dx*0.6), int(S*0.205))]
    draw.polygon(inner, fill=EAR_INNER)

draw_ear(int(S*0.325), -int(S*0.05))
draw_ear(int(S*0.675), int(S*0.05))

# ---------- speech bubble ----------
# tail
tail = [(int(S*0.30), by1 - int(S*0.02)),
        (int(S*0.255), int(S*0.84)),
        (int(S*0.43), by1 - int(S*0.02))]
draw.polygon(tail, fill=WHITE)
rrect(draw, (bx0, by0, bx1, by1), r=br, fill=WHITE)

# ---------- whiskers (cat = 喵) : fan outward toward the bubble edge ----------
wk = max(2, int(S*0.011))
wy = int(S*0.625)
for side in (-1, 1):
    inner_x = cx + side * int(S*0.215)       # loose origin near the cheek
    outer_x = cx + side * int(S*0.330)       # toward the bubble edge
    for k in (-1, 0, 1):
        iy = wy + k * int(S*0.022)           # small inner spread (not a point)
        oy = wy + k * int(S*0.058)           # wider outer spread -> fans out
        draw.line([(inner_x, iy), (outer_x, oy)],
                  fill=GLYPH_TEAL, width=wk, joint="curve")

# ---------- blush cheeks (sit just above the whiskers) ----------
for bxc in (int(S*0.255), int(S*0.745)):
    draw.ellipse((bxc - int(S*0.036), int(S*0.555),
                  bxc + int(S*0.036), int(S*0.555) + int(S*0.050)),
                 fill=BLUSH)

# ---------- 文 glyph ----------
font = ImageFont.truetype("C:/Windows/Fonts/msjhbd.ttc", int(S*0.40), index=0)
draw.text((cx, int(S*0.525)), "文", font=font, fill=GLYPH_TEAL, anchor="mm")

# small translation arrow + "A" hint, top-right of glyph (subtle)
afont = ImageFont.truetype("C:/Windows/Fonts/msjhbd.ttc", int(S*0.13), index=0)

# ---------- export ----------
img.save(os.path.join(HERE, "_master.png"))
for size, name in [(128, "128.png"), (48, "48.png"), (16, "16.png")]:
    img.resize((size, size), Image.LANCZOS).save(os.path.join(HERE, name))
# contact sheet for preview
sheet = Image.new("RGBA", (256 + 128 + 48 + 40, 280), (245, 245, 245, 255))
x = 10
for size in (256, 128, 48, 16):
    ic = img.resize((size, size), Image.LANCZOS)
    sheet.alpha_composite(ic, (x, 10))
    x += size + 10
sheet.save(os.path.join(HERE, "_preview.png"))
print("done")
