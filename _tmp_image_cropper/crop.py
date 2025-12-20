#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from PIL import Image, ImageOps


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    def validate(self, width: int, height: int) -> None:
        if self.left < 0 or self.top < 0:
            raise ValueError("box 的 left/top 不能为负")
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("box 需要满足 right>left 且 bottom>top")
        if self.right > width or self.bottom > height:
            raise ValueError(
                f"box 超出图片范围：box=({self.left},{self.top},{self.right},{self.bottom}) 图片=({width}x{height})"
            )


def _default_output_path(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    if not ext:
        ext = ".png"
    return f"{base}_cropped{ext}"


def _parse_positive_ints(values: Iterable[str], n: int, name: str) -> Tuple[int, ...]:
    values = list(values)
    if len(values) != n:
        raise ValueError(f"{name} 需要 {n} 个整数参数")
    out: list[int] = []
    for v in values:
        try:
            iv = int(v)
        except ValueError as e:
            raise ValueError(f"{name} 参数必须是整数：{v}") from e
        if iv <= 0:
            raise ValueError(f"{name} 参数必须为正数：{iv}")
        out.append(iv)
    return tuple(out)


def _parse_box_int(values: Iterable[str]) -> Box:
    vals = list(values)
    if len(vals) != 4:
        raise ValueError("--box 需要 4 个整数：left top right bottom")
    try:
        l, t, r, b = (int(x) for x in vals)
    except ValueError as e:
        raise ValueError("--box 参数必须是整数") from e
    return Box(l, t, r, b)


def _parse_box_float(values: Iterable[str], width: int, height: int) -> Box:
    vals = list(values)
    if len(vals) != 4:
        raise ValueError("--boxf 需要 4 个小数：left top right bottom（范围 0~1）")
    try:
        lf, tf, rf, bf = (float(x) for x in vals)
    except ValueError as e:
        raise ValueError("--boxf 参数必须是小数") from e

    for name, v in [("left", lf), ("top", tf), ("right", rf), ("bottom", bf)]:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"--boxf 的 {name} 必须在 0~1：{v}")

    l = int(round(lf * width))
    t = int(round(tf * height))
    r = int(round(rf * width))
    b = int(round(bf * height))

    # 保证至少 1px
    if r == l:
        r = min(width, l + 1)
    if b == t:
        b = min(height, t + 1)

    return Box(l, t, r, b)


def _center_crop_box(width: int, height: int, target_w: int, target_h: int) -> Box:
    if target_w > width or target_h > height:
        raise ValueError(
            f"目标尺寸大于原图：target=({target_w}x{target_h}) image=({width}x{height})"
        )
    left = (width - target_w) // 2
    top = (height - target_h) // 2
    return Box(left, top, left + target_w, top + target_h)


def _max_center_crop_by_aspect(width: int, height: int, aspect_w: int, aspect_h: int) -> Box:
    # 计算在原图内能裁出的最大化区域，使其宽高比 = aspect_w:aspect_h
    if aspect_w <= 0 or aspect_h <= 0:
        raise ValueError("--aspect 参数必须为正数")

    target_ratio = aspect_w / aspect_h
    src_ratio = width / height

    if src_ratio > target_ratio:
        # 原图更“宽”，限制高度，用高度决定宽度
        target_h_px = height
        target_w_px = int(round(target_h_px * target_ratio))
    else:
        # 原图更“窄”，限制宽度，用宽度决定高度
        target_w_px = width
        target_h_px = int(round(target_w_px / target_ratio))

    target_w_px = min(target_w_px, width)
    target_h_px = min(target_h_px, height)

    # 防止四舍五入导致 0
    target_w_px = max(1, target_w_px)
    target_h_px = max(1, target_h_px)

    return _center_crop_box(width, height, target_w_px, target_h_px)


def _save_image(img: Image.Image, output_path: str) -> None:
    ext = os.path.splitext(output_path)[1].lower()
    save_kwargs = {}
    if ext in {".jpg", ".jpeg"}:
        save_kwargs.update({"quality": 95, "optimize": True})
    img.save(output_path, **save_kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description="用 Pillow 裁剪图片")
    parser.add_argument("input", help="输入图片路径")
    parser.add_argument("-o", "--output", help="输出图片路径（默认 input_cropped.ext）")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--box",
        nargs=4,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        help="按像素框裁剪",
    )
    group.add_argument(
        "--boxf",
        nargs=4,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        help="按比例框裁剪（0~1）",
    )
    group.add_argument(
        "--center",
        nargs=2,
        metavar=("W", "H"),
        help="居中裁剪到指定尺寸（像素）",
    )
    group.add_argument(
        "--aspect",
        nargs=2,
        metavar=("W", "H"),
        help="按固定宽高比做最大化居中裁剪（例如 16 9）",
    )

    args = parser.parse_args()

    input_path: str = args.input
    output_path: str = args.output or _default_output_path(input_path)

    with Image.open(input_path) as im_raw:
        im = ImageOps.exif_transpose(im_raw)
        width, height = im.size

        box: Optional[Box] = None
        if args.box is not None:
            box = _parse_box_int(args.box)
        elif args.boxf is not None:
            box = _parse_box_float(args.boxf, width, height)
        elif args.center is not None:
            target_w, target_h = _parse_positive_ints(args.center, 2, "--center")
            box = _center_crop_box(width, height, target_w, target_h)
        elif args.aspect is not None:
            aspect_w, aspect_h = _parse_positive_ints(args.aspect, 2, "--aspect")
            box = _max_center_crop_by_aspect(width, height, aspect_w, aspect_h)

        if box is None:
            raise RuntimeError("内部错误：未生成裁剪框")

        box.validate(width, height)
        cropped = im.crop((box.left, box.top, box.right, box.bottom))
        _save_image(cropped, output_path)

    print(f"OK: {input_path} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
