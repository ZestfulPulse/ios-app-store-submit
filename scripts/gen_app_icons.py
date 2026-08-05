#!/usr/bin/env python3
"""Regenerate iOS/macOS/Android launcher icons from one square source PNG.

Usage:
    python3 gen_app_icons.py <source.png> <project_root> [--platforms ios,macos,android]

<project_root> is the Flutter project root (the dir containing ios/, macos/, android/).
Only platforms whose asset directories exist are touched; missing ones are skipped.
Requires Pillow: pip install Pillow
"""
import sys
import argparse
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

IOS_SIZES = [
    ("Icon-App-20x20@1x.png", 20), ("Icon-App-20x20@2x.png", 40), ("Icon-App-20x20@3x.png", 60),
    ("Icon-App-29x29@1x.png", 29), ("Icon-App-29x29@2x.png", 58), ("Icon-App-29x29@3x.png", 87),
    ("Icon-App-40x40@1x.png", 40), ("Icon-App-40x40@2x.png", 80), ("Icon-App-40x40@3x.png", 120),
    ("Icon-App-60x60@2x.png", 120), ("Icon-App-60x60@3x.png", 180),
    ("Icon-App-76x76@1x.png", 76), ("Icon-App-76x76@2x.png", 152),
    ("Icon-App-83.5x83.5@2x.png", 167),
    ("Icon-App-1024x1024@1x.png", 1024),
]

MACOS_SIZES = [
    ("app_icon_16.png", 16), ("app_icon_32.png", 32), ("app_icon_64.png", 64),
    ("app_icon_128.png", 128), ("app_icon_256.png", 256), ("app_icon_512.png", 512),
    ("app_icon_1024.png", 1024),
]

ANDROID_DIRS = {
    "mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144, "mipmap-xxxhdpi": 192,
}


def resize(src: Image.Image, size: int) -> Image.Image:
    return src.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("project_root")
    ap.add_argument("--platforms", default="ios,macos,android")
    args = ap.parse_args()

    src_path = Path(args.source)
    root = Path(args.project_root)
    platforms = set(args.platforms.split(","))

    src = Image.open(src_path).convert("RGBA")
    if src.width != src.height:
        sys.exit(f"Source image must be square, got {src.width}x{src.height}")

    if "ios" in platforms:
        ios_dir = root / "ios/Runner/Assets.xcassets/AppIcon.appiconset"
        if ios_dir.is_dir():
            for name, size in IOS_SIZES:
                resize(src, size).save(ios_dir / name)
            print(f"iOS: wrote {len(IOS_SIZES)} icons to {ios_dir}")
        else:
            print(f"iOS: skipped, {ios_dir} not found")

    if "macos" in platforms:
        macos_dir = root / "macos/Runner/Assets.xcassets/AppIcon.appiconset"
        if macos_dir.is_dir():
            for name, size in MACOS_SIZES:
                resize(src, size).save(macos_dir / name)
            print(f"macOS: wrote {len(MACOS_SIZES)} icons to {macos_dir}")
        else:
            print(f"macOS: skipped, {macos_dir} not found")

    if "android" in platforms:
        res_dir = root / "android/app/src/main/res"
        if res_dir.is_dir():
            count = 0
            for dirname, size in ANDROID_DIRS.items():
                target_dir = res_dir / dirname
                if target_dir.is_dir():
                    resize(src, size).save(target_dir / "ic_launcher.png")
                    count += 1
            print(f"Android: wrote {count} icons under {res_dir}")
        else:
            print(f"Android: skipped, {res_dir} not found")

    print("Done. Bump the app's build number and re-archive before uploading — icons are baked into the binary.")


if __name__ == "__main__":
    main()
