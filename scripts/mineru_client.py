"""MinerU 客户端 — 上传文件到 MinerU 云端解析，返回 Markdown

独立于 Flamme 后端，供 scripts/ 直接调用。
流程: 申请上传链接 → PUT 上传文件 → 轮询结果 → 下载 zip → 提取 full.md
"""

import io
import os
import time
import zipfile
from pathlib import Path

import httpx

MINERU_BASE = "https://mineru.net"


def _decode_markdown(content: bytes) -> str:
    """MinerU zip 内的 Markdown 可能不是 UTF-8，按常见中文编码回退"""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _get_headers(token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def request_upload_url(token: str, file_name: str,
                       model_version: str = "vlm") -> tuple[str, str] | tuple[None, str]:
    """申请上传链接，返回 (batch_id, upload_url) 或 (None, error_msg)"""
    try:
        r = httpx.post(
            f"{MINERU_BASE}/api/v4/file-urls/batch",
            headers=_get_headers(token),
            json={"files": [{"name": file_name}], "model_version": model_version},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        if data.get("code") != 0:
            return None, f"申请上传链接失败: {data.get('msg', '未知错误')}"

        batch_id = data["data"]["batch_id"]
        file_urls = data["data"]["file_urls"]
        if not file_urls:
            return None, "未获取到上传链接"

        return batch_id, file_urls[0]

    except httpx.HTTPStatusError as e:
        return None, f"API 请求失败 (HTTP {e.response.status_code})"
    except Exception as e:
        return None, f"申请上传链接异常: {e}"


def upload_file(upload_url: str, filepath: str) -> str | None:
    """上传文件到签名 URL，返回错误消息或 None"""
    try:
        with open(filepath, "rb") as f:
            r = httpx.put(upload_url, content=f.read(), timeout=120)
            r.raise_for_status()
        return None
    except Exception as e:
        return f"文件上传失败: {e}"


def poll_result(token: str, batch_id: str, file_name: str,
                timeout: int = 300, interval: int = 5) -> str | None:
    """轮询解析结果，返回 zip_url 或 None"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(
                f"{MINERU_BASE}/api/v4/extract-results/batch/{batch_id}",
                headers=_get_headers(token),
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()

            if data.get("code") != 0:
                time.sleep(interval)
                continue

            results = data["data"].get("extract_result", [])
            for item in results:
                if item.get("file_name") == file_name or len(results) == 1:
                    state = item.get("state", "")
                    if state == "done":
                        return item.get("full_zip_url", "")
                    elif state == "failed":
                        print(f"  [mineru] 解析失败: {item.get('err_msg')}")
                        return None
                    else:
                        progress = item.get("extract_progress", {})
                        if progress:
                            print(f"  [mineru] 解析中: {progress.get('extracted_pages', '?')}/{progress.get('total_pages', '?')} 页")
                        break

        except Exception as e:
            print(f"  [mineru] 轮询异常: {e}")

        time.sleep(interval)

    print(f"  [mineru] 解析超时 ({timeout}s)")
    return None


def extract_markdown(zip_url: str) -> str | None:
    """下载 zip 并提取 Markdown 文本"""
    try:
        r = httpx.get(zip_url, timeout=120)
        r.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            md_files = [n for n in zf.namelist() if n.endswith(".md")]
            if not md_files:
                print("  [mineru] zip 中未找到 Markdown 文件")
                return None

            target = next((f for f in md_files if "full" in f.lower()), md_files[0])
            return _decode_markdown(zf.read(target))

    except Exception as e:
        print(f"  [mineru] 下载/解压失败: {e}")
        return None


def parse_file(filepath: str, token: str = None) -> str | None:
    """完整解析流程：上传 → 解析 → 提取 Markdown

    Args:
        filepath: PDF/DOCX/PPTX 文件路径
        token: MinerU API Token（默认从环境变量 MINERU_API_TOKEN 读取）

    Returns:
        Markdown 文本，或 None（失败时）
    """
    token = token or os.environ.get("MINERU_API_TOKEN", "")
    if not token:
        print("[mineru] 错误: MINERU_API_TOKEN 未配置")
        return None

    filepath = str(filepath)
    file_name = Path(filepath).name
    file_size = Path(filepath).stat().st_size

    if file_size > 200 * 1024 * 1024:
        print(f"[mineru] 错误: 文件过大 ({file_size / 1024 / 1024:.1f}MB)，上限 200MB")
        return None

    print(f"  [mineru] 开始解析: {file_name} ({file_size / 1024:.1f}KB)")

    # 1. 申请上传链接
    batch_id, upload_url = request_upload_url(token, file_name)
    if not batch_id:
        print(f"  [mineru] 错误: {upload_url}")
        return None

    # 2. 上传文件
    err = upload_file(upload_url, filepath)
    if err:
        print(f"  [mineru] 错误: {err}")
        return None

    # 3. 轮询结果
    zip_url = poll_result(token, batch_id, file_name)
    if not zip_url:
        return None

    # 4. 提取 Markdown
    md = extract_markdown(zip_url)
    if md:
        print(f"  [mineru] 完成: {len(md)} 字符")
    return md
