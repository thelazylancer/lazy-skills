#!/usr/bin/env python3
"""
grok-imagine-mcp — 极简 MCP server，把中转站上的 Grok Imagine 生图/生视频暴露成工具。

安装：  pip install "mcp[cli]" httpx
注册到 Claude Code：
  claude mcp add grok-imagine \
    -e GROK_RELAY_BASE_URL=https://你的中转站/v1 \
    -e GROK_RELAY_API_KEY=sk-xxx \
    -- python3 /绝对路径/grok-imagine-mcp/server.py
Claude Desktop 则在 claude_desktop_config.json 的 mcpServers 里加同样的 command/args/env。
"""
import asyncio
import base64
import os
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP, Image

BASE_URL = os.environ.get("GROK_BASE_URL", "https://api-fast.linkcode.site/v1").rstrip("/")
API_KEY = os.environ["GROK_API_KEY"]
OUT_DIR = Path(os.environ.get("GROK_OUTPUT_DIR", Path.home() / "grok-output"))
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

mcp = FastMCP("grok-imagine")


def _save(data: bytes, ext: str, prefix: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}.{ext}"
    dest.write_bytes(data)
    return dest


@mcp.tool()
async def generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    model: str = "grok-imagine-image-2.0",
    resolution: str = "1k",
    quality: str | None = None,
) -> list:
    """用 Grok Imagine 根据英文提示词生成一张图片。aspect_ratio 如 1:1/16:9/9:16；resolution 1k/2k；
    quality（low/medium/auto）仅 grok-imagine-image-2.0 支持。返回图片和本地保存路径。"""
    body = {"model": model, "prompt": prompt, "n": 1, "response_format": "b64_json",
            "aspect_ratio": aspect_ratio, "resolution": resolution}
    if quality:
        body["quality"] = quality
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{BASE_URL}/images/generations", headers=HEADERS, json=body)
        r.raise_for_status()
    item = r.json()["data"][0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    else:
        async with httpx.AsyncClient(timeout=180) as c:
            raw = (await c.get(item["url"])).content
    path = _save(raw, "jpg", "grok-image")
    return [f"已保存到 {path}", Image(data=raw, format="jpeg")]


@mcp.tool()
async def generate_video(
    prompt: str,
    duration: int = 8,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    model: str = "grok-imagine-video-1.5",
    image_path: str | None = None,
    timeout_seconds: int = 600,
) -> str:
    """用 Grok Imagine 生成视频（文生视频；给 image_path 则为图生视频，建议配 grok-imagine-video-1.5）。
    会阻塞轮询直到完成，返回本地 mp4 路径。按秒计费。"""
    body = {"model": model, "prompt": prompt, "duration": duration,
            "aspect_ratio": aspect_ratio, "resolution": resolution}
    if image_path:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        body["image"] = {"url": f"data:image/jpeg;base64,{b64}"}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{BASE_URL}/videos/generations", headers=HEADERS, json=body)
        r.raise_for_status()
        request_id = r.json().get("request_id") or r.json().get("id")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            s = (await c.get(f"{BASE_URL}/videos/{request_id}", headers=HEADERS)).json()
            status = s.get("status")
            if status == "done":
                url = s["video"]["url"]
                url = urljoin(BASE_URL, url) if url.startswith("/") else url
                raw = (await c.get(url, headers=HEADERS, timeout=300)).content
                path = _save(raw, "mp4", "grok-video")
                return f"视频已保存到 {path}（{s['video'].get('duration')}s）"
            if status in ("failed", "expired"):
                return f"视频生成失败：{s}"
            await asyncio.sleep(5)
    return f"轮询超时，request_id={request_id}，可稍后再查。"


if __name__ == "__main__":
    mcp.run()
