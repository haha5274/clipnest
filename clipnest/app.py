"""tkinter 界面 + 全局热键 + 剪贴板轮询。"""

from __future__ import annotations

import base64
import queue
import sys
import threading
import time
import tkinter as tk

from . import winclip
from .config import Config, db_path
from .hotkey import HotkeyManager
from .imageutil import DibError, dib_to_png
from .store import Store

BG = "#f4f5f7"
CARD = "#ffffff"
SEL = "#dbe8ff"
BORDER = "#e4e7eb"
TEXT = "#1d2129"
MUTED = "#8b939e"
ACCENT = "#2f6fed"
STAR = "#e39b2f"
FONT = "Microsoft YaHei UI"


def human_time(ts: float) -> str:
    delta = max(0.0, time.time() - ts)
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{int(delta // 60)} 分钟前"
    if delta < 86400:
        return f"{int(delta // 3600)} 小时前"
    if delta < 86400 * 30:
        return f"{int(delta // 86400)} 天前"
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class ClipboardWatcher(threading.Thread):
    """轮询剪贴板序号，变化时抓取内容投递到队列。"""

    def __init__(self, out_queue: queue.Queue, cfg: Config):
        super().__init__(daemon=True, name="clipnest-watch")
        self.queue = out_queue
        self.cfg = cfg
        self._stop = threading.Event()

    def run(self) -> None:
        try:
            last = winclip.sequence_number()
        except OSError:
            last = 0
        interval = max(0.05, self.cfg.poll_interval_ms / 1000)
        while not self._stop.wait(interval):
            try:
                seq = winclip.sequence_number()
            except OSError:
                continue
            if seq == last:
                continue
            last = seq
            payload = self._capture()
            if payload:
                self.queue.put(("clip", payload))

    def _capture(self) -> dict | None:
        text = None
        try:
            text = winclip.read_text()
        except OSError:
            text = None
        if text and text.strip():
            if len(text.encode("utf-8", "ignore")) <= self.cfg.max_text_kb * 1024:
                return {"kind": "text", "text": text}
            return None

        if not self.cfg.capture_images:
            return None
        try:
            dib = winclip.read_dib()
        except OSError:
            return None
        if not dib:
            return None
        try:
            thumb, _, _ = dib_to_png(dib, max_side=96)
            png, width, height = dib_to_png(dib, max_side=720)
        except (DibError, ValueError, MemoryError):
            return None
        return {"kind": "image", "dib": dib, "thumb": thumb, "png": png,
                "width": width, "height": height}

    def stop(self) -> None:
        self._stop.set()


class ClipNestApp:
    def __init__(self, root: tk.Tk, store: Store, cfg: Config,
                 autostart: bool = True):
        self.root = root
        self.store = store
        self.cfg = cfg
        self.events: queue.Queue = queue.Queue()
        self.query = ""
        self.items: list[dict] = []
        self.rows: list[dict] = []
        self.sel = -1
        self._visible = True
        self._photo_cache: dict[int, tk.PhotoImage] = {}

        self._build_ui()
        self.refresh()

        self.watcher = None
        self.hotkey = None
        if autostart:
            self.watcher = ClipboardWatcher(self.events, cfg)
            self.watcher.start()
            self.hotkey = HotkeyManager(
                cfg.hotkey,
                lambda: self.events.put(("hotkey", None)),
                lambda msg: self.events.put(("error", msg)),
            )
            self.hotkey.start()

        self.root.after(120, self._pump)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = self.root
        root.title("ClipNest")
        root.configure(bg=BG)
        w, h = 780, 640
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        root.minsize(560, 420)
        root.protocol("WM_DELETE_WINDOW", self.hide)

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=18, pady=(14, 6))
        tk.Label(header, text="ClipNest", bg=BG, fg=TEXT,
                 font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(header, text="剪贴板历史", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=(8, 0), pady=(3, 0))
        self.count_label = tk.Label(header, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.count_label.pack(side="right")

        search = tk.Frame(root, bg=CARD, highlightthickness=1,
                          highlightbackground=BORDER, highlightcolor=ACCENT)
        search.pack(fill="x", padx=18, pady=(2, 10))
        tk.Label(search, text="⌕", bg=CARD, fg=MUTED,
                 font=(FONT, 14)).pack(side="left", padx=(10, 4))
        self.var = tk.StringVar()
        self.entry = tk.Entry(search, textvariable=self.var, bd=0, relief="flat",
                              bg=CARD, fg=TEXT, insertbackground=TEXT,
                              font=(FONT, 11), highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 12))
        self.var.trace_add("write", lambda *_: self._on_search())

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        self.vsb = tk.Scrollbar(body, orient="vertical", width=11,
                                command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

        footer = tk.Frame(root, bg=BG)
        footer.pack(fill="x", padx=18, pady=(8, 12))
        self.hint = tk.Label(
            footer,
            text=f"↑↓ 选择 · Enter 复制 · Ctrl+P 置顶 · Del 删除 · {self.cfg.hotkey} 呼出",
            bg=BG, fg=MUTED, font=(FONT, 9),
        )
        self.hint.pack(side="left")
        for text, cmd in (("退出", self.quit), ("清空", self._clear)):
            tk.Button(footer, text=text, command=cmd, bd=0, relief="flat",
                      bg=CARD, fg=MUTED, activebackground=BORDER,
                      activeforeground=TEXT, font=(FONT, 9), padx=10, pady=3,
                      takefocus=0, cursor="hand2").pack(side="right", padx=(6, 0))

        root.bind("<Up>", lambda e: self._move(-1))
        root.bind("<Down>", lambda e: self._move(1))
        root.bind("<Return>", lambda e: self._copy_selected())
        root.bind("<KP_Enter>", lambda e: self._copy_selected())
        root.bind("<Delete>", lambda e: self._delete_selected())
        root.bind("<Control-p>", lambda e: self._toggle_pin(self.sel))
        root.bind("<Escape>", self._on_escape)
        self.entry.focus_set()

    def _on_inner_config(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_escape(self, _event=None):
        if self.var.get():
            self.var.set("")
        else:
            self.hide()
        return "break"

    # -------------------------------------------------------------- 列表渲染
    def refresh(self, keep_sel: bool = False) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self.rows = []
        self.items = self.store.list(self.query, limit=200)
        total, pinned = self.store.counts()
        self.count_label.config(text=f"共 {total} 条 · 置顶 {pinned}")

        if not self.items:
            msg = "没有匹配的内容" if self.query else "还没有记录\n复制一段文字或截个图试试"
            tk.Label(self.inner, text=msg, bg=BG, fg=MUTED, font=(FONT, 10),
                     justify="center").pack(pady=70)
            self.sel = -1
            return

        for idx, item in enumerate(self.items):
            self.rows.append(self._make_row(item, idx))
        self.sel = min(self.sel, len(self.items) - 1) if keep_sel and self.sel >= 0 else 0
        self._paint_selection()

    def _make_row(self, item: dict, idx: int) -> dict:
        row = tk.Frame(self.inner, bg=CARD, highlightthickness=1,
                       highlightbackground=BORDER, cursor="hand2")
        row.pack(fill="x", padx=6, pady=3)
        widgets: list[tk.Widget] = [row]

        star = tk.Label(row, text="★" if item["pinned"] else "☆", bg=CARD,
                        fg=STAR if item["pinned"] else "#c9ced6",
                        font=(FONT, 11), width=2, cursor="hand2")
        star.pack(side="left", padx=(6, 0))
        widgets.append(star)
        star.bind("<Button-1>", lambda e, i=idx: self._toggle_pin(i))

        if item["kind"] == "image" and item["thumb"]:
            photo = self._photo(item["thumb"])
            if photo is not None:
                thumb = tk.Label(row, image=photo, bg=CARD, bd=0)
                thumb.image = photo  # 防止被 GC
                thumb.pack(side="left", padx=(2, 8), pady=7)
                widgets.append(thumb)

        col = tk.Frame(row, bg=CARD)
        col.pack(side="left", fill="x", expand=True, pady=6)
        widgets.append(col)

        if item["kind"] == "image":
            preview = f"图片 · {item['width']}×{item['height']}"
        else:
            preview = " ".join((item["preview"] or item["content"]).split())
            if len(preview) > 120:
                preview = preview[:120] + "…"

        title = tk.Label(col, text=preview, bg=CARD, fg=TEXT, font=(FONT, 10),
                         anchor="w", justify="left")
        title.pack(fill="x")
        widgets.append(title)

        if item["kind"] == "image":
            meta = f"{human_time(item['ts'])} · 使用 {item['use_count']} 次"
        else:
            meta = (f"{human_time(item['ts'])} · {len(item['content'])} 字符"
                    f" · 使用 {item['use_count']} 次")
        meta_label = tk.Label(col, text=meta, bg=CARD, fg=MUTED, font=(FONT, 8),
                              anchor="w")
        meta_label.pack(fill="x", pady=(2, 0))
        widgets.append(meta_label)

        for widget in widgets:
            widget.bind("<Button-1>", lambda e, i=idx: self._select(i))
            widget.bind("<Double-Button-1>", lambda e, i=idx: self._activate(i))

        return {"frame": row, "widgets": widgets, "item": item}

    def _photo(self, blob: bytes) -> tk.PhotoImage | None:
        key = hash(blob)
        cached = self._photo_cache.get(key)
        if cached is not None:
            return cached
        try:
            image = tk.PhotoImage(data=base64.b64encode(blob).decode("ascii"))
        except tk.TclError:
            return None
        if len(self._photo_cache) > 240:
            self._photo_cache.clear()
        self._photo_cache[key] = image
        return image

    def _paint_selection(self) -> None:
        for i, row in enumerate(self.rows):
            selected = i == self.sel
            bg = SEL if selected else CARD
            for widget in row["widgets"]:
                try:
                    widget.configure(bg=bg)
                except tk.TclError:
                    pass
            row["frame"].configure(highlightbackground=ACCENT if selected else BORDER)

    def _scroll_to(self, index: int) -> None:
        if not (0 <= index < len(self.rows)):
            return
        self.root.update_idletasks()
        frame = self.rows[index]["frame"]
        top = self.canvas.canvasy(0)
        view = self.canvas.winfo_height()
        height = max(1, self.inner.winfo_height())
        y, h = frame.winfo_y(), frame.winfo_height()
        if y < top:
            self.canvas.yview_moveto(y / height)
        elif y + h > top + view:
            self.canvas.yview_moveto(max(0.0, (y + h - view) / height))

    # ------------------------------------------------------------------ 动作
    def current(self) -> dict | None:
        if 0 <= self.sel < len(self.items):
            return self.items[self.sel]
        return None

    def _select(self, index: int) -> None:
        if 0 <= index < len(self.rows):
            self.sel = index
            self._paint_selection()

    def _move(self, delta: int) -> str:
        if not self.rows:
            return "break"
        self.sel = max(0, min(len(self.rows) - 1, self.sel + delta))
        self._paint_selection()
        self._scroll_to(self.sel)
        return "break"

    def _activate(self, index: int) -> None:
        self._select(index)
        self._copy_selected()

    def _copy_selected(self) -> str:
        item = self.current()
        if not item:
            return "break"
        try:
            if item["kind"] == "text":
                winclip.write_text(item["content"])
            elif item.get("dib"):
                winclip.write_dib(item["dib"])
            else:
                self.set_status("这条图片缺少原始数据，无法复制")
                return "break"
        except OSError as exc:
            self.set_status(f"复制失败：{exc}")
            return "break"
        self.store.touch(item["id"])
        self.hide()
        return "break"

    def _toggle_pin(self, index: int) -> str:
        if not (0 <= index < len(self.items)):
            return "break"
        item = self.items[index]
        self.store.set_pinned(item["id"], not item["pinned"])
        self.sel = index
        self.refresh(keep_sel=True)
        return "break"

    def _delete_selected(self) -> str:
        item = self.current()
        if not item:
            return "break"
        self.store.delete(item["id"])
        self.refresh(keep_sel=True)
        return "break"

    def _clear(self) -> None:
        removed = self.store.clear(keep_pinned=True)
        self.refresh()
        self.set_status(f"已清空 {removed} 条（置顶项保留）")

    def set_status(self, message: str) -> None:
        default = (f"↑↓ 选择 · Enter 复制 · Ctrl+P 置顶 · Del 删除 · "
                   f"{self.cfg.hotkey} 呼出")
        self.hint.config(text=message, fg=ACCENT)
        self.root.after(2200, lambda: self.hint.config(text=default, fg=MUTED))

    def _on_search(self) -> None:
        self.query = self.var.get().strip()
        self.refresh()

    # ------------------------------------------------------------ 显示与事件
    def show(self) -> None:
        self._visible = True
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(220, lambda: self.root.attributes("-topmost", False))
        if self.var.get():
            self.var.set("")
        self.entry.focus_force()
        self.refresh()

    def hide(self) -> None:
        self._visible = False
        self.root.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "clip":
                    self._on_clip(payload)
                elif kind == "hotkey":
                    self.toggle()
                elif kind == "error":
                    self.set_status(payload)
        except queue.Empty:
            pass
        self.root.after(120, self._pump)

    def _on_clip(self, payload: dict) -> None:
        if payload["kind"] == "text":
            self.store.add_text(payload["text"])
        else:
            self.store.add_image(payload["dib"], payload["png"], payload["thumb"],
                                 payload["width"], payload["height"])
        self.store.trim(self.cfg.max_items)
        if self._visible:
            self.refresh(keep_sel=True)
        else:
            total, pinned = self.store.counts()
            self.count_label.config(text=f"共 {total} 条 · 置顶 {pinned}")

    def quit(self) -> None:
        try:
            self.cfg.save()
        except OSError:
            pass
        try:
            if self.watcher:
                self.watcher.stop()
            if self.hotkey:
                self.hotkey.stop()
        finally:
            self.store.close()
            self.root.destroy()


def _enable_dpi_awareness() -> None:
    try:
        if sys.platform.startswith("win"):
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - 老系统没有该 API
        pass


def run(hidden: bool = False, db_file: str | None = None) -> int:
    _enable_dpi_awareness()
    cfg = Config.load()
    store = Store(db_file or db_path())
    root = tk.Tk()
    app = ClipNestApp(root, store, cfg)
    if hidden:
        app.hide()
    root.mainloop()
    return 0
