"""PDF 解析工具 — MinerU 精准解析 API

将本地 PDF 文件上传到 MinerU，获取 Markdown 输出。
流程: 申请上传链接 → PUT 上传文件 → 自动触发解析 → 轮询结果 → 下载 zip → 提取 full.md
"""

import io
import logging
import os
import time
import zipfile
from pathlib import Path

import httpx

from src.tools.interfaces import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MINERU_BASE = "https://mineru.net"


class PDFParserTool(BaseTool):
    name = "pdf_parse"
    description = "解析 PDF 文件为 Markdown（MinerU 精准解析，支持表格/公式/图片）"
    is_concurrency_safe = False
    is_read_only = True
    max_result_chars = 200_000

    def __init__(self, api_token: str, model_version: str = "vlm", vault_path: str = ""):
        self._token = api_token
        self._model_version = model_version
        self._vault_path = vault_path

    def _resolve(self, path: str) -> str:
        """相对路径 → 绝对路径"""
        if os.path.isabs(path) or not self._vault_path:
            return path
        return os.path.join(self._vault_path, path)

    @staticmethod
    def _decode_markdown(content: bytes) -> str:
        """MinerU zip 内的 Markdown 偶尔不是 UTF-8，按常见中文编码回退。"""
        last_error: UnicodeDecodeError | None = None
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError as e:
                last_error = e
        if last_error:
            logger.warning("Markdown 解码回退到 replace: %s", last_error)
        return content.decode("utf-8", errors="replace")

    @property
    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

    def validate_input(self, params: dict) -> list[str]:
        errors = []
        path = params.get("path", "")
        if not path:
            errors.append("缺少 path 参数")
            return errors
        resolved = self._resolve(path)
        if not Path(resolved).exists():
            errors.append(f"文件不存在: {path}（已尝试: {resolved}）")
        elif not path.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            errors.append("仅支持 PDF/Word/PPT 文件")
        return errors

    def execute(self, params: dict) -> ToolResult:
        path = self._resolve(params["path"])
        file_name = Path(path).name
        file_size = Path(path).stat().st_size

        if file_size > 200 * 1024 * 1024:
            return ToolResult.err(f"文件过大: {file_size / 1024 / 1024:.1f}MB，上限 200MB")

        if not self._token:
            return ToolResult.err("MinerU API Token 未配置")

        # 诊断日志：确认 token 来源和内容（masked）
        _t = self._token or ""
        _masked = f"{_t[:4]}...{_t[-4:]}" if len(_t) > 8 else f"({len(_t)}chars)"
        logger.info("PDF 解析开始: %s (%.1fKB), token=%s (len=%d)", file_name, file_size / 1024, _masked, len(_t))

        with httpx.Client(timeout=300) as client:
            # 1. 申请上传链接
            batch_id, upload_url = self._request_upload_url(client, file_name)
            if not batch_id:
                return ToolResult.err(upload_url)  # upload_url 这里是错误消息

            # 2. 上传文件
            err = self._upload_file(client, upload_url, path)
            if err:
                return ToolResult.err(err)

            # 3. 轮询结果
            zip_url = self._poll_result(client, batch_id, file_name)
            if not zip_url:
                return ToolResult.err("解析超时或失败")

            # 4. 下载 zip 并提取 Markdown
            return self._extract_markdown(client, zip_url, file_name)

    def _request_upload_url(self, client: httpx.Client, file_name: str) -> tuple:
        """申请上传链接，返回 (batch_id, upload_url) 或 (None, error_msg)"""
        try:
            r = client.post(
                f"{MINERU_BASE}/api/v4/file-urls/batch",
                headers=self._headers,
                json={
                    "files": [{"name": file_name}],
                    "model_version": self._model_version,
                },
            )
            r.raise_for_status()
            data = r.json()

            if data.get("code") != 0:
                return None, f"申请上传链接失败: {data.get('msg', '未知错误')}"

            batch_id = data["data"]["batch_id"]
            file_urls = data["data"]["file_urls"]
            if not file_urls:
                return None, "未获取到上传链接"

            logger.info("上传链接获取成功, batch_id=%s", batch_id)
            return batch_id, file_urls[0]

        except httpx.HTTPStatusError as e:
            return None, f"API 请求失败 (HTTP {e.response.status_code})"
        except Exception as e:
            return None, f"申请上传链接异常: {e}"

    def _upload_file(self, client: httpx.Client, upload_url: str, path: str) -> str | None:
        """上传文件到签名 URL，返回错误消息或 None"""
        try:
            with open(path, "rb") as f:
                r = client.put(upload_url, content=f.read())
                r.raise_for_status()
            logger.info("文件上传完成")
            return None
        except Exception as e:
            return f"文件上传失败: {e}"

    def _poll_result(self, client: httpx.Client, batch_id: str,
                     file_name: str, timeout: int = 300, interval: int = 5) -> str | None:
        """轮询解析结果，返回 zip_url 或 None"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = client.get(
                    f"{MINERU_BASE}/api/v4/extract-results/batch/{batch_id}",
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()

                if data.get("code") != 0:
                    logger.warning("轮询返回错误: %s", data.get("msg"))
                    time.sleep(interval)
                    continue

                results = data["data"].get("extract_result", [])
                for item in results:
                    if item.get("file_name") == file_name or len(results) == 1:
                        state = item.get("state", "")
                        if state == "done":
                            zip_url = item.get("full_zip_url", "")
                            logger.info("解析完成, zip_url=%s", zip_url[:80])
                            return zip_url
                        elif state == "failed":
                            logger.error("解析失败: %s", item.get("err_msg"))
                            return None
                        else:
                            progress = item.get("extract_progress", {})
                            if progress:
                                logger.info(
                                    "解析中: %d/%d 页",
                                    progress.get("extracted_pages", 0),
                                    progress.get("total_pages", "?"),
                                )
                            break

            except Exception as e:
                logger.warning("轮询异常: %s", e)

            time.sleep(interval)

        logger.error("解析超时 (%ds)", timeout)
        return None

    def _extract_markdown(self, client: httpx.Client, zip_url: str,
                          file_name: str) -> ToolResult:
        """下载 zip 并提取 Markdown"""
        try:
            r = client.get(zip_url)
            r.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                md_files = [n for n in zf.namelist() if n.endswith(".md")]
                if not md_files:
                    return ToolResult.err("zip 中未找到 Markdown 文件")

                target = next((f for f in md_files if "full" in f.lower()), md_files[0])
                markdown = self._decode_markdown(zf.read(target))

                logger.info("PDF 解析完成: %s (%d 字符)", file_name, len(markdown))
                return ToolResult.ok(data={
                    "file_name": file_name,
                    "markdown": markdown,
                    "char_count": len(markdown),
                })
        except Exception as e:
            return ToolResult.err(f"下载/解压失败: {e}")
