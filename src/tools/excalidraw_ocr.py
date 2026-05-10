"""Excalidraw OCR 工具 — 手写笔记识别为 Markdown

将 .excalidraw.md 中的 freedraw 笔画渲染为 PNG，
调用 Qwen-VL 视觉模型识别，保存为 companion .ocr.md。
"""

import base64
import io
import json
import logging
import os
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from src.tools.interfaces import BaseTool, ToolResult

logger = logging.getLogger(__name__)

OCR_PROMPT = """请识别这张手写笔记中的所有内容。要求：
1. 按照原始结构输出为 Markdown 格式
2. 数学公式用 LaTeX 语法（行内 $...$，独立 $$...$$）
3. 保留所有标注、箭头说明和图示描述
4. 如果有表格，用 Markdown 表格
5. 无法辨认的字迹用 [?] 标注
6. 不要添加任何解释性文字，只输出识别结果"""


class ExcalidrawOCRTool(BaseTool):
    name = "excalidraw_ocr"
    description = "识别 Excalidraw 手写笔记为 Markdown。支持单文件和全量扫描。"
    is_concurrency_safe = False
    is_read_only = True
    max_result_chars = 200_000

    def __init__(self, api_key: str, base_url: str = "",
                 model: str = "qwen-vl-max", vault_path: str = ""):
        self._api_key = api_key
        self._base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self._model = model
        self._vault_path = vault_path

    def validate_input(self, params: dict) -> list[str]:
        errors = []
        path = params.get("path", "")
        if path:
            if not path.endswith(".excalidraw.md"):
                errors.append("仅支持 .excalidraw.md 文件")
            if not Path(path).exists():
                errors.append(f"文件不存在: {path}")
        return errors

    def execute(self, params: dict) -> ToolResult:
        """同步执行 — 单文件模式或退化为 batch（无进度）"""
        if not self._api_key:
            return ToolResult.err("OCR API Key 未配置（设置 OCR_API_KEY 或 EMBED_API_KEY）")

        path = params.get("path", "")
        force = params.get("force", False)

        if path:
            return self._process_single(path, force)

        # 批量模式退化为同步
        vault = self._vault_path
        if vault:
            # drain the generator, capture return value via StopIteration
            gen = self._stream_batch(vault, force)
            result = None
            while True:
                try:
                    next(gen)
                except StopIteration as si:
                    result = si.value
                    break
            return result or ToolResult.err("批量扫描无结果")

        return ToolResult.err("缺少 path 或 vault 参数")

    def stream_execute(self, params: dict):
        """流式执行 — yield 进度字符串，最终 return ToolResult"""
        if not self._api_key:
            return ToolResult.err("OCR API Key 未配置")

        path = params.get("path", "")
        force = params.get("force", False)

        try:
            # 单文件模式
            if path:
                yield f"正在处理: {os.path.basename(path)}"
                result = self._process_single(path, force)
                if result.is_error:
                    yield f"失败: {result.error}"
                else:
                    status = result.data.get("status", "done")
                    chars = result.data.get("chars", "?")
                    yield f"完成: {os.path.basename(path)} ({status}, {chars} chars)"
                return result

            # 批量扫描
            vault = self._vault_path
            if not vault:
                return ToolResult.err("未配置 vault 路径")

            # _stream_batch 内部 yield 进度 + return ToolResult
            yield from self._stream_batch(vault, force)

        except Exception as e:
            logger.exception("stream_execute 异常: %s", e)
            return ToolResult.err(f"执行异常: {e}")

    # ── 单文件处理 ──────────────────────────────────────

    def _process_single(self, filepath: str, force: bool = False) -> ToolResult:
        # 解析相对路径为绝对路径
        if not os.path.isabs(filepath) and self._vault_path:
            filepath = os.path.join(self._vault_path, filepath)

        if not os.path.exists(filepath):
            return ToolResult.err(f"文件不存在: {filepath}")

        ocr_path = _ocr_path_for(filepath)
        if os.path.exists(ocr_path) and not force:
            # 读取已有结果
            with open(ocr_path, "r", encoding="utf-8") as f:
                content = f.read()
            return ToolResult.ok(data={
                "file": filepath,
                "ocr_path": ocr_path,
                "status": "cached",
                "content": content,
            })

        data = _parse_excalidraw_json(filepath)
        if not data:
            return ToolResult.err(f"无法解析: {filepath}")

        elements = data.get("elements", [])
        if not elements:
            return ToolResult.err(f"文件为空: {filepath}")

        png_bytes = _render_to_png(data)
        if not png_bytes:
            return ToolResult.err(f"渲染失败: {filepath}")

        ocr_text = self._ocr_image(png_bytes)
        if not ocr_text:
            return ToolResult.err(f"OCR 识别失败: {filepath}")

        # 保存 companion .ocr.md
        _save_ocr_file(filepath, ocr_text)

        return ToolResult.ok(data={
            "file": filepath,
            "ocr_path": ocr_path,
            "status": "created",
            "chars": len(ocr_text),
        })

    # ── 批量扫描（流式） ────────────────────────────────

    def _stream_batch(self, vault: str, force: bool = False):
        """生成器：yield str 进度，最终 return ToolResult"""
        files = _find_excalidraw_files(vault)
        if not files:
            return ToolResult.ok(data={"total": 0, "message": "未找到 excalidraw 文件"})

        # 分离已处理和待处理
        pending = []
        skipped = 0
        for f in files:
            ocr_file = _ocr_path_for(f)
            if force or not os.path.exists(ocr_file):
                pending.append(f)
            else:
                skipped += 1

        yield f"扫描完成: 共 {len(files)} 个文件, {skipped} 已处理, {len(pending)} 待处理"

        if not pending:
            return ToolResult.ok(data={
                "total": len(files), "processed": 0,
                "failed": 0, "skipped": skipped,
            })

        success, failed = [], []
        for i, f in enumerate(pending):
            name = os.path.basename(f)
            yield f"[{i + 1}/{len(pending)}] {name}"

            result = self._process_single(f, force=force)
            if result.is_error:
                failed.append({"file": name, "error": result.error})
                yield f"  -> 失败: {result.error[:60]}"
            else:
                success.append(name)
                chars = result.data.get("chars", "?")
                status = result.data.get("status", "done")
                yield f"  -> {status} ({chars} chars)"

            # 避免 API 限流
            if len(pending) > 1:
                time.sleep(1)

        # 汇总
        yield f"\n全部完成: {len(success)} 成功, {len(failed)} 失败, {skipped} 跳过"

        return ToolResult.ok(data={
            "total": len(files),
            "processed": len(success),
            "failed": len(failed),
            "skipped": skipped,
            "errors": failed[:5],
        })

    # ── Qwen-VL OCR ────────────────────────────────────

    def _ocr_image(self, png_bytes: bytes) -> str | None:
        b64 = base64.b64encode(png_bytes).decode("utf-8")

        # 构造 OpenAI 兼容的 chat completions 请求
        url = f"{self._base_url}/chat/completions"
        body = {
            "model": self._model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }],
        }

        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(url, json=body, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                })
                if resp.status_code != 200:
                    logger.error("OCR API %d: %s", resp.status_code, resp.text[:200])
                    return None
                result = resp.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content")
        except Exception as e:
            logger.error("OCR API 调用失败: %s", e)
            return None


# ── 模块级辅助函数 ──────────────────────────────────────

def _parse_excalidraw_json(filepath: str) -> dict | None:
    """从 .excalidraw.md 文件中提取 JSON 数据。

    支持两种格式：
    1. 直接嵌入的 JSON（旧格式）
    2. LZString 压缩的 compressed-json（新格式）
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 方案 1: compressed-json 块（LZString 压缩）
    import re
    m = re.search(r"```compressed-json\n(.*?)\n```", content, re.DOTALL)
    if m:
        try:
            import lzstring
            compressed = m.group(1).strip().replace("\n", "").replace("\r", "")
            json_str = lzstring.LZString().decompressFromBase64(compressed)
            if json_str:
                return json.loads(json_str)
        except Exception as e:
            logger.warning("LZString 解压失败 %s: %s", os.path.basename(filepath), e)

    # 方案 2: 直接嵌入的 JSON
    start = content.find('{"type":"excalidraw"')
    if start < 0:
        start = content.find("{")
    if start < 0:
        return None

    depth = 0
    end = start
    for i in range(start, len(content)):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
        if depth == 0:
            end = i + 1
            break

    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        return None


def _render_to_png(data: dict, scale: float = 1.0, padding: int = 40) -> bytes:
    """将 excalidraw JSON 中的元素渲染为 PNG"""
    elements = data.get("elements", [])
    if not elements:
        return b""

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)

    if min_x == float("inf"):
        return b""

    width = int((max_x - min_x + 2 * padding) * scale)
    height = int((max_y - min_y + 2 * padding) * scale)

    if width <= 0 or height <= 0 or width > 8000 or height > 8000:
        return b""

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    for el in elements:
        el_type = el.get("type", "")
        stroke_color = el.get("strokeColor", "#000000")
        stroke_width = el.get("strokeWidth", 2)
        opacity = el.get("opacity", 100)

        if opacity <= 0 or el.get("isDeleted", False):
            continue

        color = _resolve_color(stroke_color, opacity)

        if el_type == "freedraw":
            points = el.get("points", [])
            if len(points) < 2:
                continue
            xy = [(el["x"] + points[0][0] - min_x + padding) * scale,
                  (el["y"] + points[0][1] - min_y + padding) * scale]
            for pt in points[1:]:
                xy.append((el["x"] + pt[0] - min_x + padding) * scale)
                xy.append((el["y"] + pt[1] - min_y + padding) * scale)
            w = max(1, int(stroke_width * scale))
            if len(xy) >= 4:
                draw.line(xy, fill=color, width=w, joint="curve")

        elif el_type == "text":
            text = el.get("text", "")
            if not text:
                continue
            font_size = max(8, int(el.get("fontSize", 20) * scale))
            x = (el["x"] - min_x + padding) * scale
            y = (el["y"] - min_y + padding) * scale
            try:
                from PIL import ImageFont
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            draw.text((x, y), text, fill=color, font=font)

        elif el_type in ("rectangle", "diamond", "ellipse"):
            x1 = (el["x"] - min_x + padding) * scale
            y1 = (el["y"] - min_y + padding) * scale
            x2 = x1 + el.get("width", 0) * scale
            y2 = y1 + el.get("height", 0) * scale
            w = max(1, int(stroke_width * scale))
            if el_type == "rectangle":
                draw.rectangle([x1, y1, x2, y2], outline=color, width=w)
            elif el_type == "ellipse":
                draw.ellipse([x1, y1, x2, y2], outline=color, width=w)
            elif el_type == "diamond":
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                draw.polygon([(cx, y1), (x2, cy), (cx, y2), (x1, cy)],
                             outline=color, width=w)

        elif el_type in ("line", "arrow"):
            points = el.get("points", [])
            if len(points) < 2:
                continue
            w = max(1, int(stroke_width * scale))
            xy = []
            for p in points:
                xy.append((el["x"] + p[0] - min_x + padding) * scale)
                xy.append((el["y"] + p[1] - min_y + padding) * scale)
            draw.line(xy, fill=color, width=w)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _resolve_color(color: str, opacity: int = 100) -> str:
    if not color or color == "transparent":
        return "#000000"
    return color


def _ocr_path_for(filepath: str) -> str:
    """dir/file.excalidraw.md → dir/ocr/file.ocr.md"""
    directory = os.path.dirname(filepath)
    basename = os.path.basename(filepath).replace(".excalidraw.md", ".ocr.md")
    return os.path.join(directory, "ocr", basename)


def _find_excalidraw_files(vault_path: str) -> list[str]:
    results = []
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if d not in (".trash", ".obsidian", ".wiki", "ocr")]
        for f in files:
            if f.endswith(".excalidraw.md"):
                results.append(os.path.join(root, f))
    return sorted(results)


def _save_ocr_file(excalidraw_path: str, ocr_text: str) -> str:
    ocr_path = _ocr_path_for(excalidraw_path)
    source_name = os.path.splitext(os.path.basename(excalidraw_path))[0]
    frontmatter = "\n".join([
        "---",
        f'source: "{source_name}"',
        "type: ocr",
        f"date: {time.strftime('%Y-%m-%d')}",
        "tags: [excalidraw-ocr]",
        "---",
        "",
    ])
    os.makedirs(os.path.dirname(ocr_path), exist_ok=True)
    with open(ocr_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + ocr_text)
    return ocr_path
