"""博客來閱讀器背景截圖。直接操作獨立 Chrome 頁面，不使用桌面按鍵或截圖。

Chrome 由本工具以一般方式啟動（不經 Playwright launch），等使用者登入、開書後
才用 CDP 連線。Playwright 自己啟動的 Chrome 會帶 --enable-automation，
navigator.webdriver 為 true，博客來登入會被擋。

截完一批不會關閉：可再輸入張數接著截、改截圖大小，或結束。截圖中按 Enter
會在目前這張存完後停止。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import math
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ROOT / "private" / ".ebook_capture_packages"
if PACKAGES.is_dir():
    sys.path.insert(0, str(PACKAGES))

DEFAULT_URL = "https://viewer-ebook.books.com.tw/viewer/epub_v3/?book_uni_id=E050236278_fixedlayout_normal&ran=51208689"
READER = "#UiObj-book-reader"
NEXT = "#UiObj-book-right-btn"
ALERT = "#UiObj-model-alert"
# 截圖時暫時隱藏，截完立即還原。
CONTROL_SELECTORS = "#UiObj-header-toolbar, #UiObj-footer-toolbar, #UiObj-book-right-btn, #UiObj-book-left-btn"
# 讓被其他視窗蓋住的 Chrome 照常繪製與執行計時器（翻頁動畫才會跑完）。
CHROME_FLAGS = [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--disable-features=CalculateNativeWinOcclusion",
]
TRIM_THRESHOLD = 3  # 閱讀器底色 (250,250,250) 與白色書頁差 5，門檻要比它小
TRIM_PADDING = 2


class ChromeClosed(RuntimeError):
    pass


class CaptureStop(RuntimeError):
    """This batch cannot continue; return to the menu."""


@dataclass
class Settings:
    trim: bool = True     # 裁掉書頁四周的閱讀器底色
    scale: float = 1      # 1＝跟螢幕一樣；2＝兩倍像素
    width: int = 0        # 輸出寬度（像素），0＝不縮放

    def describe(self) -> str:
        scale = "跟螢幕一樣" if self.scale == 1 else f"{self.scale:g} 倍像素"
        width = f"寬 {self.width}px" if self.width else "不縮放"
        return f"裁白邊 {'開' if self.trim else '關'}／清晰度 {scale}／輸出 {width}"


@dataclass
class State:
    output: Path
    saved: int = 0
    last_hash: str | None = None  # 最後存檔那頁的原始截圖雜湊
    method: int = 0               # 上次成功的翻頁方式


def reader_id(url: str) -> str | None:
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname != "viewer-ebook.books.com.tw":
        return None
    if parts.path.rstrip("/") != "/viewer/epub_v3":
        return None
    return parse_qs(parts.query).get("book_uni_id", [None])[0]


def assert_ready(page) -> None:
    if page.is_closed():
        raise CaptureStop("閱讀器分頁已關閉。")
    alert = page.locator(ALERT)
    if alert.is_visible():
        message = alert.inner_text().strip()
        raise CaptureStop(f"閱讀器顯示訊息，請先在 Chrome 處理：{message}")
    page.locator(READER).wait_for(state="visible", timeout=5000)


def find_reader(context, book_id: str):
    # Bookshelf can open the reader in a new tab. Use a ready matching book.
    for page in reversed(context.pages):
        if reader_id(page.url) == book_id:
            try:
                assert_ready(page)
                return page
            except Exception:
                continue
    raise CaptureStop("還沒找到已載入的書頁。請在工具開的 Chrome 登入、開書並關閉提示。")


# ---------- 終端機輸入 ----------

class Terminal:
    """One thread reads stdin lines; the main thread keeps Playwright running while waiting."""

    _EOF = object()

    def __init__(self) -> None:
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        while True:
            try:
                line = input()
            except Exception:
                self._lines.put(self._EOF)
                return
            self._lines.put(line)

    def _take(self, timeout: float | None):
        item = self._lines.get(timeout=timeout) if timeout else self._lines.get_nowait()
        if item is self._EOF:
            self._lines.put(item)
            raise EOFError
        return item

    def poll(self) -> str | None:
        """A line typed since the last call, or None."""
        try:
            return self._take(None)
        except queue.Empty:
            return None

    def ask(self, prompt: str, pump) -> str:
        print(prompt, end="", flush=True)
        while True:
            try:
                return self._take(0.1).strip()
            except queue.Empty:
                pump()


def chrome_pump(chrome: subprocess.Popen):
    def pump():
        if chrome.poll() is not None:
            raise ChromeClosed("工具的 Chrome 已關閉。")
    return pump


def context_pump(chrome: subprocess.Popen | None, context):
    def pump():
        if chrome is not None and chrome.poll() is not None:
            raise ChromeClosed("工具的 Chrome 已關閉。")
        pages = [page for page in context.pages if not page.is_closed()]
        if not pages:
            raise ChromeClosed("工具的 Chrome 分頁已全部關閉。")
        try:
            pages[0].wait_for_timeout(100)  # 讓 Playwright 處理瀏覽器事件
        except Exception:
            time.sleep(0.1)
    return pump


# ---------- 截圖與翻頁 ----------

_SESSIONS: dict = {}  # page -> 一直開著的 CDP 連線（倍率設定靠它維持）


def cdp_session(page):
    cdp = _SESSIONS.get(page)
    if cdp is None:
        cdp = page.context.new_cdp_session(page)
        # 視窗在背景時頁面仍當作有焦點，右方向鍵翻頁才有效。
        cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        _SESSIONS[page] = cdp
    return cdp


# 截圖時暫時隱藏工具列與翻頁按鈕，截完還原。用 element.style 而不是插入 <style>，
# 網站的內容安全政策（CSP）擋不到。
_HIDE_CONTROLS = """sels => {
  const saved = [];
  for (const el of document.querySelectorAll(sels)) {
    saved.push([el, el.style.getPropertyValue('visibility'), el.style.getPropertyPriority('visibility')]);
    el.style.setProperty('visibility', 'hidden', 'important');
  }
  window.__quizCaptureSaved = saved;
  const r = document.querySelector('%s').getBoundingClientRect();
  return {x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height};
}""" % READER
_RESTORE_CONTROLS = """() => {
  for (const [el, value, priority] of window.__quizCaptureSaved || []) el.style.setProperty('visibility', value, priority);
  delete window.__quizCaptureSaved;
}"""


def raw_shot(page) -> bytes:
    """PNG of the reader area in real device pixels (Playwright's own screenshot
    shrinks to CSS pixels when attached over CDP, which loses the scale setting)."""
    page.locator(READER).wait_for(state="visible", timeout=10000)
    box = page.evaluate(_HIDE_CONTROLS, CONTROL_SELECTORS)
    try:
        if box["width"] < 1 or box["height"] < 1:
            raise CaptureStop("閱讀區大小為 0，請確認視窗沒有最小化。")
        result = cdp_session(page).send("Page.captureScreenshot", {
            "format": "png", "clip": {**box, "scale": 1}, "captureBeyondViewport": False,
        })
    finally:
        page.evaluate(_RESTORE_CONTROLS)
    return base64.b64decode(result["data"])


def digest_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_shot(page, previous_hash: str | None, delay: float) -> tuple[bytes, str]:
    """Wait, then return the first screenshot that differs from the last saved page and repeats."""
    page.wait_for_timeout(delay * 1000)
    deadline = time.monotonic() + max(15, delay * 3)
    candidate = None
    while time.monotonic() < deadline:
        assert_ready(page)
        data = raw_shot(page)
        digest = digest_of(data)
        if digest != previous_hash and digest == candidate:
            return data, digest
        candidate = digest if digest != previous_hash else None
        page.wait_for_timeout(400)
    raise CaptureStop("頁面沒有變化或一直沒有載入完成；可能已到書末。")


def settled_hash(page, timeout: float = 10) -> str:
    """Hash of the current page once two screenshots in a row match."""
    deadline = time.monotonic() + timeout
    last = None
    while True:
        digest = digest_of(raw_shot(page))
        if digest == last or time.monotonic() > deadline:
            return digest
        last = digest
        page.wait_for_timeout(400)


def _click_button(page) -> None:
    # Page-level click does not move the OS mouse or focus another app.
    page.locator(NEXT).click(timeout=3000)
    page.mouse.move(0, 0)


TURN_METHODS = (
    ("翻頁按鈕", _click_button),
    ("按鈕事件", lambda page: page.locator(NEXT).dispatch_event("click", timeout=3000)),
    ("右方向鍵", lambda page: page.keyboard.press("ArrowRight")),
)


def wait_changed(page, previous_hash: str | None, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        page.wait_for_timeout(300)
        if digest_of(raw_shot(page)) != previous_hash:
            return True
    return False


def turn_page(page, state: State, delay: float, log) -> None:
    """Try the last working method first, then the others, until the page changes."""
    order = [state.method] + [i for i in range(len(TURN_METHODS)) if i != state.method]
    problems = []
    for i in order:
        name, action = TURN_METHODS[i]
        try:
            action(page)
        except Exception as exc:
            problems.append(f"{name}：{str(exc).splitlines()[0][:80]}")
            continue
        if wait_changed(page, state.last_hash, max(6, delay * 3)):
            if i != state.method:
                log(f"改用「{name}」翻頁")
                state.method = i
            return
        problems.append(f"{name}：畫面沒變")
    log("翻頁失敗：" + "；".join(problems))
    raise CaptureStop("翻頁失敗，可能已到書末，或閱讀器跳出提示（詳見 log.txt）。")


def content_box(image) -> tuple[int, int, int, int] | None:
    from PIL import Image, ImageChops
    background = image.getpixel((0, 0))
    diff = ImageChops.difference(image, Image.new("RGB", image.size, background)).convert("L")
    box = diff.point(lambda v: 255 if v > TRIM_THRESHOLD else 0).getbbox()
    if not box:
        return None
    left, top, right, bottom = box
    if (right - left) * (bottom - top) < image.width * image.height * 0.05:
        return None  # 太小，可能是載入中的圖示，不裁
    pad = TRIM_PADDING
    return (max(0, left - pad), max(0, top - pad),
            min(image.width, right + pad), min(image.height, bottom + pad))


def save_image(data: bytes, path: Path, settings: Settings) -> tuple[int, int]:
    if not settings.trim and not settings.width:
        with path.open("xb") as file:
            file.write(data)
        from PIL import Image
        return Image.open(io.BytesIO(data)).size
    from PIL import Image
    image = Image.open(io.BytesIO(data)).convert("RGB")
    if settings.trim:
        box = content_box(image)
        if box:
            image = image.crop(box)
    if settings.width and image.width != settings.width:
        height = max(1, round(image.height * settings.width / image.width))
        image = image.resize((settings.width, height), Image.LANCZOS)
    with path.open("xb") as file:
        image.save(file, "PNG")
    return image.size


def apply_scale(page, settings: Settings) -> None:
    """Set pixel density on the page (kept while the page's CDP session stays open)."""
    cdp = cdp_session(page)
    if settings.scale == 1:
        cdp.send("Emulation.clearDeviceMetricsOverride")
    else:
        # width/height 0＝沿用視窗大小，只改像素密度；視窗仍可縮放。
        cdp.send("Emulation.setDeviceMetricsOverride", {
            "width": 0, "height": 0, "deviceScaleFactor": settings.scale, "mobile": False,
        })


def capture_batch(page, state: State, count: int, delay: float, settings: Settings,
                  terminal: Terminal, log) -> int:
    """Capture up to count pages. Continues after the last saved page."""
    assert_ready(page)
    # 目前畫面就是上次存的那頁 → 先翻頁；使用者自己翻過 → 從目前這頁開始。
    need_turn = state.last_hash is not None and digest_of(raw_shot(page)) == state.last_hash
    done = 0
    for _ in range(count):
        try:
            if terminal.poll() is not None:
                print("已依要求停止。")
                break
        except EOFError:
            break
        assert_ready(page)
        if need_turn:
            turn_page(page, state, delay, log)
        need_turn = True
        data, digest = stable_shot(page, state.last_hash, delay)
        state.output.mkdir(parents=True, exist_ok=True)
        size = save_image(data, state.output / f"page-{state.saved + 1:04d}.png", settings)
        state.saved += 1
        state.last_hash = digest
        done += 1
        print(f"已存 page-{state.saved:04d}.png（本次 {done}/{count}，{size[0]}×{size[1]}）", flush=True)
    return done


# ---------- 設定與選單 ----------

def edit_settings(settings: Settings, ask) -> bool:
    """Ask for new values; returns True if the pixel scale changed."""
    print(f"\n目前：{settings.describe()}。直接按 Enter 保留原值。")
    old_scale = settings.scale
    answer = ask(f"裁掉書頁四周空白？(y/n，目前 {'y' if settings.trim else 'n'})：").lower()
    if answer in ("y", "n"):
        settings.trim = answer == "y"
    answer = ask(f"清晰度倍率 1～4（1＝跟螢幕一樣，2＝兩倍像素，目前 {settings.scale:g}）：")
    if answer:
        try:
            value = float(answer)
            if not 1 <= value <= 4:
                raise ValueError
            settings.scale = value
        except ValueError:
            print("倍率須為 1～4，保留原值。")
    answer = ask(f"輸出寬度（像素，0＝不縮放，目前 {settings.width}）：")
    if answer:
        try:
            value = int(answer)
            if value != 0 and not 200 <= value <= 10000:
                raise ValueError
            settings.width = value
        except ValueError:
            print("寬度須為 0 或 200～10000，保留原值。")
    print(f"新設定：{settings.describe()}")
    return settings.scale != old_scale


def positive_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("張數必須是整數。")
    if not 1 <= count <= 5000:
        raise argparse.ArgumentTypeError("張數須為 1～5000。")
    return count


def delay_seconds(value: str) -> float:
    try:
        delay = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("等待秒數必須是數字。")
    if not math.isfinite(delay) or not 0.5 <= delay <= 30:
        raise argparse.ArgumentTypeError("等待秒數須為 0.5～30。")
    return delay


def scale_value(value: str) -> float:
    try:
        scale = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("倍率必須是數字。")
    if not 1 <= scale <= 4:
        raise argparse.ArgumentTypeError("倍率須為 1～4。")
    return scale


def width_value(value: str) -> int:
    try:
        width = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("寬度必須是整數。")
    if width != 0 and not 200 <= width <= 10000:
        raise argparse.ArgumentTypeError("寬度須為 0 或 200～10000。")
    return width


def run_session(context, book_id: str, state: State, settings: Settings, delay: float,
                first_count: int | None, terminal: Terminal, pump) -> None:
    """Menu loop: capture batches, change size, quit. Returns when the user quits."""
    def ask(prompt: str) -> str:
        return terminal.ask(prompt, pump)

    def log(message: str) -> None:
        print(message, flush=True)
        state.output.mkdir(parents=True, exist_ok=True)
        with (state.output / "log.txt").open("a", encoding="utf-8") as file:
            file.write(f"{datetime.now():%H:%M:%S} {message}\n")

    page = None
    scale_ok = False      # 目前頁面是否已套用最新倍率
    pending = first_count
    while True:
        if pending is None:
            print(f"\n已存 {state.saved} 張：{state.output}")
            print(f"截圖大小：{settings.describe()}")
            answer = ask("輸入數字＝再截幾張（接著下一頁）、s＝改截圖大小、q＝結束並關閉 Chrome：").lower()
            if answer in ("q", "quit", "exit"):
                return
            if answer == "s":
                if edit_settings(settings, ask):
                    scale_ok = False  # 下一批重新套用倍率
                continue
            try:
                pending = positive_count(answer)
            except argparse.ArgumentTypeError as exc:
                if answer:
                    print(exc)
                continue

        count, pending = pending, None
        try:
            if page is None or page.is_closed():
                page = find_reader(context, book_id)
                scale_ok = False
            if not scale_ok:
                apply_scale(page, settings)
                scale_ok = True
                if state.last_hash is not None:
                    # 倍率改變後重新記下目前這頁，避免同一頁再存一次。
                    page.wait_for_timeout(1000)
                    state.last_hash = settled_hash(page)
            print(f"\n開始截圖，共 {count} 張。現在可以切去做其他事。")
            print("保留工具的 Chrome 視窗，可讓其他視窗蓋住它；先不要最小化或操作它。")
            print("要提早停止：在這個視窗按 Enter（存完目前這張就停）。", flush=True)
            done = capture_batch(page, state, count, delay, settings, terminal, log)
            print(f"本次完成 {done} 張。")
        except ChromeClosed:
            raise
        except CaptureStop as exc:
            log(f"停止：{exc}")
            print("已存的圖片都保留。可在 Chrome 處理後再輸入張數繼續。")
        except Exception as exc:
            if not any(not p.is_closed() for p in context.pages):
                raise ChromeClosed("工具的 Chrome 已關閉。")
            log(f"停止：{str(exc).splitlines()[0]}")
            print("已存的圖片都保留。可在 Chrome 處理後再輸入張數繼續。")
            page = None
            scale_ok = False


# ---------- Chrome ----------

def find_chrome() -> str:
    candidates = []
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                    candidates.append(winreg.QueryValue(key, None))
            except OSError:
                pass
    except ImportError:
        pass
    for base in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(base):
            candidates.append(str(Path(os.environ[base]) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise RuntimeError("找不到 Chrome（chrome.exe），請先安裝 Google Chrome。")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_debug_port(port: int, chrome: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if chrome.poll() is not None:
            raise ChromeClosed("工具的 Chrome 已關閉。")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("Chrome 沒有回應，無法連線截圖。")


def close_chrome(chrome: subprocess.Popen, profile: str) -> None:
    """Close the tool's Chrome (whole process tree), then delete its temp profile."""
    if chrome.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(chrome.pid)], capture_output=True)
        try:
            chrome.wait(10)
        except subprocess.TimeoutExpired:
            chrome.kill()
    # Chrome 子程序可能還要幾秒才放開設定檔。
    deadline = time.monotonic() + 15
    while Path(profile).exists():
        shutil.rmtree(profile, ignore_errors=True)
        if not Path(profile).exists() or time.monotonic() > deadline:
            break
        time.sleep(0.5)
    if Path(profile).exists():
        print(f"暫存設定檔未能完全刪除，可稍後手動刪除：{profile}")


def main() -> int:
    parser = argparse.ArgumentParser(description="博客來背景截圖（不含 OCR）")
    parser.add_argument("--url", default=DEFAULT_URL, help="開書後的閱讀器網址；預設為本次提供的 TOEIC 聽力書")
    parser.add_argument("--pages", type=positive_count, help="第一批截圖張數（之後可在選單追加）")
    parser.add_argument("--delay", type=delay_seconds, default=2, help="翻頁後等待秒數，預設 2")
    parser.add_argument("--scale", type=scale_value, default=1, help="清晰度倍率 1～4，預設 1（跟螢幕一樣）")
    parser.add_argument("--width", type=width_value, default=0, help="輸出寬度（像素），預設 0＝不縮放")
    parser.add_argument("--no-trim", action="store_true", help="不要裁掉書頁四周空白")
    parser.add_argument("--check-deps", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
        import PIL  # noqa: F401
    except ImportError:
        print("缺少 Playwright 或 Pillow，請執行 tools\\capture_ebook_background.cmd 自動安裝。")
        return 1
    if args.check_deps:
        return 0

    book_id = reader_id(args.url.strip())
    if not book_id:
        parser.error("請使用 https://viewer-ebook.books.com.tw/viewer/epub_v3/?book_uni_id=... 的閱讀器網址。")
    settings = Settings(trim=not args.no_trim, scale=args.scale, width=args.width)
    state = State(output=ROOT / "private" / "ebook_captures" / datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    terminal = Terminal()

    print("\n將開啟一般 Chrome 視窗與博客來首頁，使用獨立的暫存設定檔。")
    print("請在新視窗登入博客來，從電子書櫃開啟這本書並移到起始頁。")
    print("關閉工具後會清除本次暫存設定檔，不會讀取原本 Chrome 的登入。")
    chrome_path = find_chrome()
    port = free_port()
    profile = tempfile.mkdtemp(prefix="quiz-ebook-")
    try:
        # 一般方式啟動 Chrome（無 --enable-automation），登入頁不會把它當成自動化程式。
        chrome = subprocess.Popen([
            chrome_path, f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
            "--remote-allow-origins=http://127.0.0.1", "--no-first-run",
            "--no-default-browser-check", "--start-maximized", *CHROME_FLAGS,
            "https://www.books.com.tw/",
        ])
    except OSError:
        shutil.rmtree(profile, ignore_errors=True)
        raise
    try:
        wait_for_debug_port(port, chrome)
        terminal.ask("\n登入、開書並關閉教學／提示，看到完整書頁後，回到這裡按 Enter（Ctrl+C 取消）：",
                     chrome_pump(chrome))
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            try:
                context = browser.contexts[0]
                pump = context_pump(chrome, context)
                while True:
                    try:
                        find_reader(context, book_id)
                        break
                    except CaptureStop as exc:
                        print(exc)
                    terminal.ask("準備好後按 Enter 再試（Ctrl+C 取消）：", pump)
                print(f"\n截圖大小：{settings.describe()}（之後可在選單輸入 s 修改）")
                first = args.pages
                while first is None:
                    answer = terminal.ask("第一批要截幾張（建議先試 3 張）：", pump)
                    try:
                        first = positive_count(answer)
                    except argparse.ArgumentTypeError as exc:
                        print(exc)
                run_session(context, book_id, state, settings, args.delay, first, terminal, pump)
            finally:
                try:
                    browser.close()  # 只中斷連線；Chrome 由下方關閉
                except Exception:
                    pass
    except EOFError:
        pass
    except ChromeClosed as exc:
        print(f"\n{exc}")
    finally:
        close_chrome(chrome, profile)
    print(f"\n結束。共存 {state.saved} 張" + (f"：{state.output}" if state.saved else "。"))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    except KeyboardInterrupt:
        print("\n已停止，已存圖片保留。")
        code = 130
    except Exception as error:
        print(f"\n停止：{error}\n已存圖片保留在 private\\ebook_captures。")
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    # 讀 Enter 的背景執行緒可能仍卡在 input()；直接結束，避免關閉時的 stdin 鎖錯誤。
    os._exit(code)
