"""日记完整复刻器：下载接口数据和图片，并生成带评论的 PDF。"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
from urllib.parse import urlparse

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

API = "https://hope.wantexe.com/services/v2/parallellife/period/dairy/list"
FONT_CANDIDATES = (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc")


def app_folder() -> Path:
    """安装为 exe 后使用 exe 所在目录；开发运行时使用脚本所在目录。"""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def safe_name(value: str, fallback: str) -> str:
    value = re.sub(r'[\\/:*?"<>|]+', "_", str(value)).strip(" .")
    return value[:100] or fallback


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    # 某些旧接口会把 UTF-8 按 GBK 传出，出现典型乱码时才修复，避免误伤正常中文。
    if any(mark in text for mark in ("锛", "銆", "鈥", "闃", "�")):
        try:
            return text.encode("gbk").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return text


def as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def rich_blocks(entry: dict) -> list[dict]:
    info = entry.get("noteInfo2") or {}
    if not isinstance(info, dict):
        return [{"type": 1, "text": clean_text(entry.get("dairy"))}]
    blocks = as_list(info.get("richTextInfo"))
    return [block for block in blocks if isinstance(block, dict)] or [{"type": 1, "text": clean_text(entry.get("dairy"))}]


def get_headers(value: str) -> dict[str, str]:
    parsed = json.loads(value) if value.strip() else {}
    if not isinstance(parsed, dict):
        raise ValueError("附加请求头必须是 JSON 对象。")
    return {str(k): str(v) for k, v in parsed.items() if v is not None and str(v).strip()}


def api_request(url: str, payload: dict, headers: dict[str, str], progress=None) -> dict:
    """优先使用系统网络配置；代理连接超时时自动尝试直接连接。"""
    request_headers = {"Accept": "application/json", "User-Agent": "DiaryReplica/1.0", **headers}
    try:
        response = requests.post(url, json=payload, headers=request_headers, timeout=(12, 25))
    except (requests.Timeout, requests.ConnectionError) as first_error:
        if progress:
            progress(4, "代理连接超时，正在尝试直连日记接口…")
        try:
            direct = requests.Session()
            direct.trust_env = False
            response = direct.post(url, json=payload, headers=request_headers, timeout=(12, 25))
        except (requests.Timeout, requests.ConnectionError) as second_error:
            raise RuntimeError(f"日记接口无法连接。代理连接：{first_error}；直连：{second_error}") from second_error
    response.raise_for_status()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            value = json.loads(response.content.decode(encoding))
            if isinstance(value, dict):
                return value
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise RuntimeError("接口返回内容不是 JSON 对象。")


def diary_entries(response: dict) -> tuple[dict, list[dict]]:
    datas = response.get("datas") or {}
    if not isinstance(datas, dict):
        return {}, []
    return datas, [item for item in as_list(datas.get("list")) if isinstance(item, dict)]


def ensure_api_success(response: dict) -> None:
    """把 HTTP 成功但业务失败的响应转换成用户可读错误。"""
    status = response.get("status")
    if status not in (None, 1, "1", True):
        message = response.get("msg") or response.get("message") or response.get("error") or "未知原因"
        raise RuntimeError(f"接口拒绝了查询：{clean_text(message)}（status={status}）")


def fetch_image(url: str, headers: dict[str, str]) -> bytes:
    """CDN 偶尔中断 TLS：交替使用系统代理和直连，并有限重试。"""
    request_headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://hope.wantexe.com/", **headers}
    failures = []
    for attempt in range(4):
        direct = attempt % 2 == 1
        session = requests.Session()
        session.trust_env = not direct
        try:
            response = session.get(url, headers=request_headers, timeout=(15, 40))
            response.raise_for_status()
            if not response.content:
                raise RuntimeError("服务器返回空图片")
            return response.content
        except (requests.RequestException, RuntimeError) as error:
            failures.append(f"第 {attempt + 1} 次（{'直连' if direct else '代理'}）：{error}")
            if attempt < 3:
                time.sleep(1.2 * (attempt + 1))
        finally:
            session.close()
    raise RuntimeError("；".join(failures))


def download_everything(url: str, payload: dict, headers: dict[str, str], root: Path, progress) -> tuple[list[dict], dict[str, Path], list[str]]:
    """自动翻页，保存所有原始 JSON、每篇 JSON 和媒体文件。"""
    root.mkdir(parents=True, exist_ok=True)
    pages_dir = root / "responses"
    pages_dir.mkdir(exist_ok=True)
    requested_page = max(1, int(payload["pageNum"]))
    page_size = max(1, int(payload["pageSize"]))
    entries: list[dict] = []
    first_response: dict | None = None
    total = 0
    seen_pages: set[str] = set()
    page = requested_page

    while True:
        page_payload = {**payload, "pageNum": page, "pageSize": page_size}
        progress(min(18, 4 + len(seen_pages)), f"正在请求第 {page} 页…")
        response = api_request(url, page_payload, headers, progress)
        ensure_api_success(response)
        if first_response is None:
            first_response = response
        (pages_dir / f"response_page_{page:04d}.json").write_text(
            json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        datas, page_entries = diary_entries(response)
        try:
            total = max(total, int(datas.get("total") or 0))
        except (TypeError, ValueError):
            pass
        progress(min(20, 5 + len(seen_pages)), f"接口请求成功：第 {page} 页返回 {len(page_entries)} 篇，共 {total} 篇")

        # 防止服务端忽略 pageNum、反复返回同一页而形成死循环。
        signature = json.dumps(page_entries, ensure_ascii=False, sort_keys=True)
        if signature in seen_pages:
            break
        seen_pages.add(signature)
        entries.extend(page_entries)
        if not page_entries or len(entries) >= total > 0 or len(page_entries) < page_size:
            break
        if page - requested_page >= 9999:
            raise RuntimeError("自动翻页超过 10000 页，已停止以避免异常循环。")
        page += 1

    combined_response = dict(first_response or {})
    combined_datas = dict((first_response or {}).get("datas") or {})
    combined_datas.update({"list": entries, "total": total})
    combined_response["datas"] = combined_datas
    (root / "response.json").write_text(json.dumps(combined_response, ensure_ascii=False, indent=2), encoding="utf-8")
    diary_dir, image_dir = root / "diaries", root / "images"
    diary_dir.mkdir(exist_ok=True)
    image_dir.mkdir(exist_ok=True)
    (root / "query.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not entries:
        return [], {}, ["请求已成功；该用户 ID、日期范围或日记类型下没有日记（total=0）。请确认填写的是用户 ID，而不是日记 ID。"]

    urls: list[str] = []
    for entry in entries:
        for block in rich_blocks(entry):
            for file in as_list(block.get("fileList")):
                if isinstance(file, dict) and file.get("mediaUrl"):
                    urls.append(str(file["mediaUrl"]))
    unique_urls = list(dict.fromkeys(urls))
    total_steps = len(entries) + len(unique_urls) + 1
    completed, errors, image_map = 0, [], {}
    for index, entry in enumerate(entries, 1):
        diary_id = entry.get("dairyId", index)
        day = clean_text(entry.get("noteDate", ""))[:10] or f"entry_{index}"
        (diary_dir / safe_name(f"{index:03d}_{day}_{diary_id}.json", f"entry_{index}.json")).write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        completed += 1
        progress(5 + 60 * completed / total_steps, f"已保存日记 JSON：{index}/{len(entries)}")
    media_headers = {k: v for k, v in headers.items() if k.lower() not in {"content-type", "accept"}}
    for index, media_url in enumerate(unique_urls, 1):
        try:
            extension = Path(urlparse(media_url).path).suffix.lower() or ".jpg"
            local = image_dir / f"{index:03d}{extension}"
            local.write_bytes(fetch_image(media_url, media_headers))
            image_map[media_url] = local
        except RuntimeError as error:
            errors.append(f"图片下载失败：{media_url} ({error})")
        completed += 1
        progress(5 + 60 * completed / total_steps, f"正在下载图片：{index}/{len(unique_urls)}")
    manifest = {"imageMap": {key: str(value.relative_to(root)) for key, value in image_map.items()}, "errors": errors}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        (root / "download_errors.txt").write_text("\n".join(errors), encoding="utf-8")
    return entries, image_map, errors


def register_font() -> str:
    for candidate in FONT_CANDIDATES:
        if os.path.exists(candidate):
            pdfmetrics.registerFont(TTFont("DiaryChinese", candidate, subfontIndex=0))
            return "DiaryChinese"
    raise RuntimeError("未找到中文字体。请确认 Windows 的微软雅黑、黑体或宋体字体存在。")


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def pdf_image(path: Path):
    try:
        image = Image(str(path))
        max_width, max_height = 166 * mm, 115 * mm
        ratio = min(max_width / image.imageWidth, max_height / image.imageHeight, 1)
        image.drawWidth, image.drawHeight = image.imageWidth * ratio, image.imageHeight * ratio
        return image
    except Exception:
        return None


def build_pdf(destination: Path, entries: list[dict], image_map: dict[str, Path], payload: dict, progress) -> None:
    font = register_font()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DTitle", parent=styles["Title"], fontName=font, fontSize=19, leading=27, textColor=colors.HexColor("#25364A"))
    heading = ParagraphStyle("DHead", parent=styles["Heading2"], fontName=font, fontSize=13, leading=20, textColor=colors.HexColor("#25364A"), spaceBefore=3)
    meta = ParagraphStyle("DMeta", parent=styles["Normal"], fontName=font, fontSize=8.8, leading=14, textColor=colors.HexColor("#687386"))
    body = ParagraphStyle("DBody", parent=styles["BodyText"], fontName=font, fontSize=10.5, leading=18, spaceAfter=5)
    comment = ParagraphStyle("DComment", parent=body, fontSize=9.6, leading=16, leftIndent=5 * mm, borderColor=colors.HexColor("#D8E2EC"), borderWidth=0.5, borderPadding=4, backColor=colors.HexColor("#F5F8FB"))
    story = [Paragraph("日记完整复刻", title), Paragraph(f"用户 ID：{payload['userId']}　查询日期：{payload['beginDate']} 至 {payload['endDate']}　共 {len(entries)} 篇", meta), Spacer(1, 7 * mm)]
    for number, entry in enumerate(entries, 1):
        diary_id, note_date = entry.get("dairyId", "—"), clean_text(entry.get("noteDate", "未知日期"))
        story += [Paragraph(f"{number}. {note_date}", heading), Paragraph(f"日记 ID：{diary_id}　心情：{entry.get('emotionIdentity') or '—'}　天气：{entry.get('weatherIdentity') or '—'}", meta), Spacer(1, 2 * mm)]
        for block in rich_blocks(entry):
            content = clean_text(block.get("text", "")).strip()
            if content:
                story.append(Paragraph(escape(content), body))
            for file in as_list(block.get("fileList")):
                media_url = file.get("mediaUrl") if isinstance(file, dict) else None
                image_path = image_map.get(str(media_url)) if media_url else None
                if image_path and image_path.exists():
                    image = pdf_image(image_path)
                    if image:
                        story.extend([image, Spacer(1, 3 * mm)])
        comments = []
        for group in as_list(entry.get("commentList")):
            comments.extend(item for item in as_list((group or {}).get("detail")) if isinstance(item, dict))
        if comments:
            story += [Spacer(1, 3 * mm), Paragraph(f"评论（{len(comments)}）", heading)]
            for item in comments:
                name = clean_text(item.get("fromName", "匿名"))
                content = clean_text(item.get("comments", ""))
                stamp = item.get("createTime") or ""
                story.append(Paragraph(f"<b>{escape(name)}</b>　{escape(str(stamp))}<br/>{escape(content)}", comment))
                story.append(Spacer(1, 2 * mm))
        if number < len(entries):
            story.append(PageBreak())
        progress(68 + 30 * number / len(entries), f"正在组装 PDF：{number}/{len(entries)}")

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D8E2EC")); canvas.line(18 * mm, 11 * mm, 192 * mm, 11 * mm)
        canvas.setFont(font, 8); canvas.setFillColor(colors.HexColor("#687386"))
        canvas.drawString(18 * mm, 7 * mm, "日记完整复刻")
        canvas.drawRightString(192 * mm, 7 * mm, f"第 {doc.page} 页")
        canvas.restoreState()
    SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=17 * mm, title="日记完整复刻").build(story, onFirstPage=decorate, onLaterPages=decorate)


class DiaryReplica(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("日记完整复刻器")
        self.geometry("980x620"); self.minsize(820, 530)
        self.base = app_folder() / "diary_output"; self.base.mkdir(exist_ok=True)
        self.output_dir = tk.StringVar(value=str(self.base))
        self.status = tk.StringVar(value="填写参数后点击“查询并完整导出”。")
        self._form()

    def _form(self):
        box = ttk.LabelFrame(self, text="查询参数", padding=10); box.pack(fill="x", padx=12, pady=12)
        defaults = {
            "api": API,
            "userId": "",
            "beginDate": f"{datetime.now().year}-01-01",
            "endDate": datetime.now().strftime("%Y-%m-%d"),
            "noteType": "0",
            "type": "all",
            "pageSize": "20",
            "pageNum": "1",
        }
        self.vars = {key: tk.StringVar(value=value) for key, value in defaults.items()}
        fields = [("接口地址", "api"), ("用户 ID（不是日记 ID）", "userId"), ("开始日期", "beginDate"), ("结束日期", "endDate"), ("日记类型", "noteType"), ("查询类型", "type"), ("每页数量", "pageSize"), ("起始页码", "pageNum")]
        for n, (label, key) in enumerate(fields):
            row, column = divmod(n, 4)
            ttk.Label(box, text=label).grid(row=row * 2, column=column, sticky="w", padx=4)
            ttk.Entry(box, textvariable=self.vars[key], width=24).grid(row=row * 2 + 1, column=column, sticky="ew", padx=4, pady=(0, 6))
            box.columnconfigure(column, weight=1)
        ttk.Label(self, text="附加请求头（JSON；需要登录时填 Cookie 或 Authorization）").pack(anchor="w", padx=14)
        self.headers = tk.Text(self, height=3, wrap="word"); self.headers.pack(fill="x", padx=12, pady=(2, 8))
        path = ttk.Frame(self); path.pack(fill="x", padx=12)
        ttk.Label(path, text="输出文件夹：").pack(side="left")
        ttk.Entry(path, textvariable=self.output_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(path, text="选择文件夹", command=self.choose_folder).pack(side="left")
        controls = ttk.Frame(self); controls.pack(fill="x", padx=12, pady=10)
        self.go = ttk.Button(controls, text="查询并完整导出", command=self.start); self.go.pack(side="left")
        self.bar = ttk.Progressbar(controls, mode="determinate", maximum=100); self.bar.pack(side="left", fill="x", expand=True, padx=10)
        ttk.Label(controls, textvariable=self.status).pack(side="right")
        result = ttk.LabelFrame(self, text="执行结果", padding=8); result.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(result, state="disabled", wrap="word"); self.log.pack(fill="both", expand=True)

    def choose_folder(self):
        selected = filedialog.askdirectory(title="选择输出文件夹", initialdir=self.output_dir.get() or str(self.base))
        if selected: self.output_dir.set(selected)

    def payload(self) -> dict:
        try:
            for key in ("beginDate", "endDate"): datetime.strptime(self.vars[key].get(), "%Y-%m-%d")
            result = {"beginDate": self.vars["beginDate"].get(), "noteType": int(self.vars["noteType"].get()), "endDate": self.vars["endDate"].get(), "pageSize": int(self.vars["pageSize"].get()), "type": self.vars["type"].get().strip(), "pageNum": int(self.vars["pageNum"].get()), "userId": self.vars["userId"].get().strip()}
            if result["pageSize"] <= 0 or result["pageNum"] <= 0:
                raise ValueError("每页数量和起始页码必须大于 0。")
            return result
        except ValueError as error:
            raise ValueError("日期须为 YYYY-MM-DD；日记类型、每页数量、页码须为整数。") from error

    def start(self):
        try:
            payload, headers = self.payload(), get_headers(self.headers.get("1.0", "end"))
            if not all(str(value).strip() for value in payload.values()): raise ValueError("所有查询参数都不能为空。")
        except (ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("参数有误", str(error)); return
        self.go.configure(state="disabled"); self.bar["value"] = 0
        self._write(f"开始执行：用户 ID {payload['userId']}，{payload['beginDate']} 至 {payload['endDate']}。程序会从第 {payload['pageNum']} 页开始自动获取全部页。\n")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = Path(self.output_dir.get()) / f"query_{payload['userId']}_{stamp}"
        url = self.vars["api"].get().strip()
        threading.Thread(target=self.worker, args=(url, root, payload, headers, stamp), daemon=True).start()

    def set_progress(self, percent, message):
        self.after(0, lambda: (self.bar.configure(value=percent), self.status.set(message)))

    def worker(self, url, root, payload, headers, stamp):
        try:
            entries, image_map, errors = download_everything(url, payload, headers, root, self.set_progress)
            if not entries:
                message = errors[0] if errors else "请求成功，但没有查询到日记。"
                self.set_progress(100, "请求完成：没有查询到日记")
                self.after(0, lambda: self.empty(message, root))
                return
            pdf = root / f"日记完整复刻_{stamp}.pdf"
            build_pdf(pdf, entries, image_map, payload, self.set_progress)
            self.set_progress(100, "已完成")
            report = f"完成：{len(entries)} 篇日记，{len(image_map)} 张图片。\n数据目录：{root}\nPDF：{pdf}"
            if errors: report += f"\n另有 {len(errors)} 个图片下载失败，详情见 download_errors.txt。"
            self.after(0, lambda: self.done(report))
        except Exception as error:
            root.mkdir(parents=True, exist_ok=True)
            (root / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            message = str(error)
            self.after(0, lambda: self.failed(message, root))

    def _write(self, text):
        self.log.configure(state="normal"); self.log.insert("end", text); self.log.see("end"); self.log.configure(state="disabled")

    def done(self, report):
        self.go.configure(state="normal"); self._write(report + "\n\n"); messagebox.showinfo("导出完成", report)

    def empty(self, message, root):
        self.go.configure(state="normal")
        report = f"{message}\n\n接口响应已保存：\n{root / 'response.json'}"
        self._write(report + "\n\n")
        messagebox.showwarning("请求成功，但没有日记", report)

    def failed(self, error, root):
        self.go.configure(state="normal"); self.status.set("失败")
        self._write(f"失败：{error}\n调试文件：{root / 'error.txt'}\n\n")
        messagebox.showerror("导出失败", f"{error}\n\n详细日志已保存：\n{root / 'error.txt'}")


if __name__ == "__main__":
    DiaryReplica().mainloop()
