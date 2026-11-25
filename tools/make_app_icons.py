#!/usr/bin/env python3
"""PhoneAudioSink 图标生成器（PC 与安卓共用同一套图形）。

图形：显示器（电脑）→ 三段声波 → 手机，强调"电脑的声音推到手机"。
输出：
  - 安卓各密度 mipmap：ic_launcher / ic_launcher_round / ic_launcher_foreground
  - PC 端 pc/assets/app.ico（多尺寸，每档单独渲染）与 icon_<size>.png
  - 预览图 app-icon-preview.png

用法：
  python tools/make_app_icons.py <android_res_dir> <pc_assets_dir> <preview.png>
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFilter

SS = 4  # 超采样倍数

BG_TOP = (14, 17, 21)
BG_BOT = (32, 43, 58)
ACCENT = (76, 141, 255)
PHONE = (232, 240, 255)
WAVE = (186, 216, 255)
ACCENT_SOFT = (120, 165, 240)


def _gradient(size_px: int):
    img = Image.new("RGB", (1, size_px))
    px = img.load()
    for y in range(size_px):
        t = y / max(1, size_px - 1)
        px[0, y] = tuple(round(BG_TOP[i] * (1 - t) + BG_BOT[i] * t) for i in range(3))
    return img


def _background(size: int) -> Image.Image:
    s = size * SS
    base = _gradient(s).resize((s, s), Image.BILINEAR).convert("RGBA")
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy, r = s * 0.5, s * 0.38, s * 0.62
    for i in range(14):
        k = (i + 1) / 14
        rr = r * (1 - k * 0.55)
        gd.ellipse([cx - rr, cy - rr * 0.8, cx + rr, cy + rr * 0.8],
                   fill=ACCENT + (int(24 * k ** 0.7),))
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.06))
    base.alpha_composite(glow)
    # 与其它图元保持同一尺寸（逻辑像素），便于直接叠加
    return base.resize((size, size), Image.LANCZOS)


def _draw_motif(size: int, dx: float = 0.0, dy: float = 0.0, scale: float = 1.0) -> Image.Image:
    """透明画布上画显示器 + 声波 + 手机；dx/dy/scale 用于自适应图标的前景安全区。"""
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def box(x0, y0, x1, y1, r, fill=None, outline=None, width=0):
        d.rounded_rectangle(
            [s * (dx + x0 * scale), s * (dy + y0 * scale),
             s * (dx + x1 * scale), s * (dy + y1 * scale)],
            radius=s * r * scale, fill=fill, outline=outline, width=width,
        )

    # 显示器
    box(0.100, 0.245, 0.462, 0.500, 0.046, fill=ACCENT)
    # 支架
    box(0.254, 0.500, 0.310, 0.556, 0.010, fill=ACCENT_SOFT)
    box(0.200, 0.554, 0.364, 0.592, 0.019, fill=ACCENT_SOFT)
    # 手机
    box(0.655, 0.330, 0.820, 0.720, 0.052, fill=PHONE)
    # 手机听筒凹槽（用背景色"挖"出来，避免额外描边）
    box(0.703, 0.358, 0.772, 0.378, 0.010, fill=(26, 32, 43, 255))
    # 三段声波（浅蓝，配色统一；小尺寸时自动加粗，避免 48px 下消失）
    cx, cy = s * (dx + 0.472 * scale), s * (dy + 0.462 * scale)
    stroke = max(s * 0.025 * scale, 2.4 * SS)
    for r, alpha in [(0.036, 255), (0.072, 232), (0.108, 210)]:
        rr = s * r * scale
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], -56, 56,
              fill=WAVE + (alpha,), width=int(stroke))
    return layer.resize((size, size), Image.LANCZOS)


def _rounded_mask(size: int, radius_ratio: float = 0.23) -> Image.Image:
    s = size * SS
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * radius_ratio), fill=255)
    return m.resize((size, size), Image.LANCZOS)


def _circle_mask(size: int) -> Image.Image:
    s = size * SS
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).ellipse([0, 0, s - 1, s - 1], fill=255)
    return m.resize((size, size), Image.LANCZOS)


def icon(mask: Image.Image | None = None) -> Image.Image:
    size = mask.size[0]
    out = _background(size)
    out.putalpha(mask)
    # 传统图标没有 108dp 画布，图形按中心放大一点，小尺寸下更饱满
    sc = 1.12
    out.alpha_composite(_draw_motif(size, dx=0.445 * (1 - sc), dy=0.48 * (1 - sc), scale=sc))
    return out


def foreground(size: int) -> Image.Image:
    """自适应图标前景：图形放进中心 ~62% 安全区，背景透明。"""
    return _draw_motif(size, dx=0.19, dy=0.19, scale=0.62)


def rounded_icon(size: int) -> Image.Image:
    return icon(_rounded_mask(size))


def round_icon(size: int) -> Image.Image:
    return icon(_circle_mask(size))


DENSITIES = {"mdpi": (48, 108), "hdpi": (72, 162), "xhdpi": (96, 216),
             "xxhdpi": (144, 324), "xxxhdpi": (192, 432)}

PC_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def build_android(res_dir: str) -> None:
    for density, (legacy, fg) in DENSITIES.items():
        out = os.path.join(res_dir, f"mipmap-{density}")
        os.makedirs(out, exist_ok=True)
        rounded_icon(legacy).save(os.path.join(out, "ic_launcher.png"), "PNG", optimize=True)
        round_icon(legacy).save(os.path.join(out, "ic_launcher_round.png"), "PNG", optimize=True)
        foreground(fg).save(os.path.join(out, "ic_launcher_foreground.png"), "PNG", optimize=True)
        print(f"android {density}: {legacy}px / fg {fg}px")


def build_pc(assets_dir: str, preview_path: str) -> None:
    os.makedirs(assets_dir, exist_ok=True)
    frames = [rounded_icon(s) for s in PC_SIZES]
    frames[-1].save(os.path.join(assets_dir, "app.ico"), format="ICO",
                    sizes=[(s, s) for s in PC_SIZES])
    # 每档单独存 PNG，供 Qt 用 QIcon.addFile 组装，高 DPI 下不会被放大糊掉
    for s in PC_SIZES:
        rounded_icon(s).save(os.path.join(assets_dir, f"icon_{s}.png"), "PNG", optimize=True)
    rounded_icon(1024).save(os.path.join(assets_dir, "icon_1024.png"), "PNG", optimize=True)
    rounded_icon(512).save(preview_path, "PNG", optimize=True)
    print("pc ico:", os.path.join(assets_dir, "app.ico"), "frames:", PC_SIZES)
    print("preview:", preview_path)


if __name__ == "__main__":
    res = sys.argv[1] if len(sys.argv) > 1 else "res"
    assets = sys.argv[2] if len(sys.argv) > 2 else os.path.join("assets")
    prev = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.getcwd(), "app-icon-preview.png")
    build_android(res)
    build_pc(assets, prev)
