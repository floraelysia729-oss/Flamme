"""
批量 OCR 薄页图片 → 补充到对应 markdown 文件

用法:
  python scripts/batch_ocr.py <md_dir> [--api-url URL] [--dry-run]

示例:
  python scripts/batch_ocr.py "D:/notebook/pro/人工智能导论"
  python scripts/batch_ocr.py "D:/notebook/pro/人工智能导论" --dry-run
"""

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

from flamme_paths import ocr_dir

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)


def ocr_image(img_path: Path, api_url: str) -> str | None:
    """单张图片 OCR，返回识别文字或 None"""
    import urllib.request

    b64 = base64.b64encode(img_path.read_bytes()).decode()
    payload = json.dumps({"base64": b64}).encode()
    req = urllib.request.Request(
        api_url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            if data.get("code") in (100, 200) and data.get("data"):
                texts = [
                    item["text"]
                    for item in data["data"]
                    if isinstance(item, dict) and item.get("text")
                ]
                return "\n".join(texts).strip() or None
    except Exception as e:
        print(f"    [fail] {img_path.name}: {e}")
    return None


def find_prefix_groups(images_dir: Path) -> dict[str, list[Path]]:
    """按 PDF 前缀分组图片，如 1.绪论_p1 → 1.绪论"""
    groups: dict[str, list[Path]] = {}
    for img in sorted(images_dir.iterdir()):
        if not img.is_file() or not img.name.endswith(".png"):
            continue
        # 提取前缀: "1.绪论_p10.png" → "1.绪论"
        m = re.match(r"(.+)_p\d+\.png$", img.name)
        if m:
            prefix = m.group(1)
            groups.setdefault(prefix, []).append(img)
    return groups


def main():
    parser = argparse.ArgumentParser(description="批量 OCR 薄页图片")
    parser.add_argument("md_dir", help="包含 md 文件和 images/ 子目录的路径")
    parser.add_argument("--api-url", default="http://localhost:1224/api/ocr")
    parser.add_argument("--dry-run", action="store_true", help="只统计不执行")
    args = parser.parse_args()

    md_dir = Path(args.md_dir)
    images_dir = ocr_dir(md_dir)

    if not images_dir.exists() or not any(images_dir.iterdir()):
        print(f"Error: no images found in {images_dir}")
        sys.exit(1)

    groups = find_prefix_groups(images_dir)
    total = sum(len(v) for v in groups.values())
    print(f"Found {total} images in {len(groups)} groups\n")

    if args.dry_run:
        for prefix, imgs in groups.items():
            print(f"  {prefix}: {len(imgs)} images")
        return

    ocr_done = 0
    ocr_fail = 0

    for prefix, imgs in groups.items():
        # 找对应的 md 文件
        md_file = None
        for ext in (".md", ".markdown"):
            candidate = md_dir / f"{prefix}{ext}"
            if candidate.exists():
                md_file = candidate
                break

        if not md_file:
            print(f"[skip] no md file for {prefix}")
            continue

        print(f"[*] {prefix} ({len(imgs)} pages)")

        # 检查是否已有 OCR 补充内容
        md_content = md_file.read_text(encoding="utf-8")
        if "# OCR 补充内容" in md_content:
            print(f"  [skip] already has OCR content")
            continue

        # 批量 OCR
        ocr_results: dict[str, str] = {}
        for i, img in enumerate(imgs):
            page_num_match = re.search(r"_p(\d+)\.png$", img.name)
            page_num = page_num_match.group(1) if page_num_match else "?"

            text = ocr_image(img, args.api_url)
            if text:
                ocr_results[img.name] = text
            else:
                ocr_fail += 1

            ocr_done += 1
            if (i + 1) % 10 == 0 or (i + 1) == len(imgs):
                print(f"  [{i+1}/{len(imgs)}] done")

        if not ocr_results:
            print(f"  [warn] no text recognized")
            continue

        # 按页码排序拼成 markdown
        ocr_lines = ["\n\n---\n\n# OCR 补充内容（薄页）\n"]
        for img in sorted(imgs):
            text = ocr_results.get(img.name, "")
            if text:
                page_num_match = re.search(r"_p(\d+)\.png$", img.name)
                page_num = page_num_match.group(1) if page_num_match else "?"
                ocr_lines.append(f"\n### Page {page_num} (OCR)\n\n{text}\n")

        # 追加到 md 文件
        md_file.write_text(md_content + "\n".join(ocr_lines), encoding="utf-8")
        print(f"  → OCR appended to {md_file.name} ({len(ocr_results)} pages)")

    print(f"\nDone. OCR: {ocr_done} attempted, {ocr_fail} failed")


if __name__ == "__main__":
    main()
