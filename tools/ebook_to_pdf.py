"""把電子書截圖（page-0001.png …）合併成給 OCR 用的 PDF。

截圖解析度低時（例如書頁只有 690 像素寬，中文字約 11 像素高），OCR 容易把
「寫」認成「舄」、「目」認成「冃」。這個工具先把每頁用 Lanczos 等比放大
（預設 3 倍），再以 300 DPI 的實際尺寸放進 PDF，OCR 軟體會用它最擅長的
解析度辨識。放大不會無中生有細節；最好的做法仍是截圖時就用高倍率
（capture_ebook_background.py 的清晰度倍率）。已是高倍率截圖時用 --scale 1。

用法：
  py -X utf8 tools/ebook_to_pdf.py 圖片資料夾 [圖片資料夾 …] [--scale 3] [--dpi 300] [--out 輸出.pdf]
  py -X utf8 tools/ebook_to_pdf.py 圖片資料夾 --pages 323-640,642-919 --out 詳解.pdf   # 只取部分截圖

多個資料夾會依序合併成一本。預設輸出在第一個資料夾旁：「資料夾名（OCR用）.pdf」。
圖片與 PDF 都是市售書內容，只放 private/。
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path


def parse_pages(spec: str) -> set[int]:
    """'1-322' / '323-640,642-919' → set of capture numbers."""
    pages: set[int] = set()
    for part in spec.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        lo, hi = int(lo), int(hi or lo)
        if lo > hi:
            raise ValueError(part)
        pages.update(range(lo, hi + 1))
    if not pages:
        raise ValueError(spec)
    return pages


def page_images(folders: list[Path], pages: set[int] | None = None) -> list[Path]:
    images = []
    for folder in folders:
        found = sorted(folder.glob("page-*.png"))
        if not found:
            raise SystemExit(f"資料夾裡沒有 page-*.png：{folder}")
        images += found
    if pages is not None:
        if len(folders) > 1:
            raise SystemExit("--pages 只能搭配單一資料夾。")
        numbers = {int(path.stem.split("-")[1]): path for path in images}
        missing = sorted(pages - numbers.keys())
        if missing:
            raise SystemExit(f"找不到這些截圖編號：{missing[:10]}")
        images = [numbers[n] for n in sorted(pages)]
    return images


def main() -> int:
    parser = argparse.ArgumentParser(description="截圖合併成 OCR 用 PDF")
    parser.add_argument("folders", nargs="+", type=Path, help="放 page-0001.png … 的資料夾")
    parser.add_argument("--scale", type=float, default=3, help="放大倍率，預設 3；高倍率截圖用 1")
    parser.add_argument("--dpi", type=int, default=300, help="PDF 標示的解析度，預設 300")
    parser.add_argument("--quality", type=int, default=92, help="JPEG 品質 1～100，預設 92")
    parser.add_argument("--png", action="store_true", help="改用無損 PNG（檔案約大 2.5 倍）")
    parser.add_argument("--pages", help="只取這些截圖編號，例如 1-322 或 323-640,642-919（跳過壞頁）")
    parser.add_argument("--out", type=Path, help="輸出 PDF 路徑")
    args = parser.parse_args()
    if not 1 <= args.scale <= 6 or not 72 <= args.dpi <= 1200 or not 1 <= args.quality <= 100:
        parser.error("--scale 1～6、--dpi 72～1200、--quality 1～100")
    try:
        pages = parse_pages(args.pages) if args.pages else None
    except ValueError:
        parser.error("--pages 格式例如 1-322 或 323-640,642-919")

    import pymupdf
    from PIL import Image

    images = page_images(args.folders, pages)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
    out = args.out or args.folders[0].with_name(f"{args.folders[0].name}（OCR用）.pdf")
    if out.exists():
        parser.error(f"輸出檔已存在，請刪除或用 --out 指定其他名稱：{out}")

    doc = pymupdf.open()
    for number, path in enumerate(images, 1):
        image = Image.open(path).convert("RGB")
        if args.scale != 1:
            size = (round(image.width * args.scale), round(image.height * args.scale))
            image = image.resize(size, Image.LANCZOS)
        data = io.BytesIO()
        if args.png:
            image.save(data, "PNG", dpi=(args.dpi, args.dpi))
        else:
            # subsampling=0：色彩不降採樣，彩色字的邊緣不會糊。
            image.save(data, "JPEG", quality=args.quality, subsampling=0, dpi=(args.dpi, args.dpi))
        width, height = image.width * 72 / args.dpi, image.height * 72 / args.dpi
        page = doc.new_page(width=width, height=height)
        page.insert_image(page.rect, stream=data.getvalue())
        if number % 50 == 0 or number == len(images):
            print(f"{number} / {len(images)}", flush=True)
    doc.set_metadata({"title": out.stem, "creator": "tools/ebook_to_pdf.py"})
    tmp = out.with_name(out.name + ".tmp")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(out)
    print(f"完成：{out}（{len(images)} 頁，{out.stat().st_size / 1e6:.0f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
