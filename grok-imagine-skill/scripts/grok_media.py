#!/usr/bin/env python3
"""
grok_media.py — 通过 OpenAI 兼容中转站调用 Grok Imagine 生图 / 生视频。
只依赖 Python 标准库 + 系统自带的 curl，可直接被 Claude 的 Bash 工具调用。

配置（优先级从高到低）：
  1. 命令行参数 --base-url / --api-key
  2. 环境变量 GROK_BASE_URL / GROK_API_KEY（兼容 GROK_RELAY_*）
  3. 配置文件 ~/.config/grok-relay/config.json  {"base_url": "...", "api_key": "..."}

用法：
  python3 grok_media.py image "a red fox in snow" --aspect-ratio 16:9 --out ./out
  python3 grok_media.py image "..." --model grok-imagine-image-2.0 --quality medium --n 2
  python3 grok_media.py edit "make it night" --image ./in.jpg --out ./out
  python3 grok_media.py video "ocean waves at sunset" --duration 8 --aspect-ratio 16:9 --resolution 720p
  python3 grok_media.py video "make the water move" --image ./in.jpg --model grok-imagine-video-1.5
  python3 grok_media.py video-status <request_id>
"""
import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
from urllib.parse import urljoin
from pathlib import Path

DEFAULT_BASE_URL = "https://api-fast.linkcode.site/v1"


# ---------- 配置 ----------
def load_config(args):
    base_url = args.base_url or os.environ.get("GROK_RELAY_BASE_URL") or os.environ.get("GROK_BASE_URL")
    api_key = (args.api_key or os.environ.get("GROK_API_KEY") or
               os.environ.get("GROK_RELAY_API_KEY"))
    if not (base_url and api_key):
        cfg = Path.home() / ".config" / "grok-relay" / "config.json"
        if cfg.exists():
            data = json.loads(cfg.read_text())
            base_url = base_url or data.get("base_url")
            api_key = api_key or data.get("api_key")
    base_url = base_url or DEFAULT_BASE_URL
    if not api_key:
        die("缺少 api_key。请用 --api-key 传入，或设置环境变量 GROK_API_KEY，"
            "或写入 ~/.config/grok-relay/config.json（{\"base_url\": \"...\", \"api_key\": \"...\"}）")
    return base_url.rstrip("/"), api_key


def die(msg, code=1):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(code)


def _curl(args, timeout, fatal=True):
    """统一走 curl（HTTP/2）。原因：中转站前面的 Cloudflare 会对 Python urllib/HTTP1.1 客户端
    返回 403 挑战页，而 curl 默认 HTTP/2 能通过（2026-09-14 实测）。"""
    cmd = ["curl", "-sS", "-m", str(timeout), "-w", "\n%{http_code}"] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    except FileNotFoundError:
        die("找不到 curl，请先安装。")
    except subprocess.TimeoutExpired:
        die(f"请求超时（{timeout}s）")
    if proc.returncode != 0:
        if "-o" in args:  # 下载类请求：交给调用方决定是否致命
            return 599, proc.stderr.strip()[:400]
        die(f"curl 失败: {proc.stderr.strip()[:400]}")
    out, _, code = proc.stdout.rpartition("\n")
    return int(code or 0), out


def request(method, url, api_key, body=None, timeout=180):
    args = ["-X", method, url,
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json"]
    if body is not None:
        args += ["--data-binary", "@-"]
        # 通过 stdin 传 body，避免大 base64 参考图撑爆命令行长度
        return _request_with_stdin(args, url, json.dumps(body), timeout)
    code, out = _curl(args, timeout)
    return _parse(code, url, out)


def _request_with_stdin(args, url, data, timeout):
    cmd = ["curl", "-sS", "-m", str(timeout), "-w", "\n%{http_code}"] + args
    proc = subprocess.run(cmd, input=data, capture_output=True, text=True, timeout=timeout + 10)
    if proc.returncode != 0:
        die(f"curl 失败: {proc.stderr.strip()[:400]}")
    out, _, code = proc.stdout.rpartition("\n")
    return _parse(int(code or 0), url, out)


def _parse(code, url, out):
    if code >= 400:
        if out.lstrip().startswith("<!DOCTYPE") or "Just a moment" in out:
            die(f"HTTP {code} {url}: 被 Cloudflare 挑战页拦截（非 API 错误），请检查中转站 WAF 规则")
        die(f"HTTP {code} {url}: {out[:800]}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        die(f"响应不是 JSON（HTTP {code}）: {out[:400]}")


def download(url, dest, api_key=None, base_url=None):
    if url.startswith("/"):
        url = urljoin(base_url, url) if url.startswith("/v1/") else urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
    headers = ["-H", f"Authorization: Bearer {api_key}"] if api_key else []
    code, _ = _curl(headers + ["-L", "-o", str(dest), url], 300)
    if code >= 400:
        die(f"下载失败 HTTP {code}: {url}")


def image_to_data_url(path):
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def save_image_items(items, out_dir, prefix, api_key=None, base_url=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    ts = time.strftime("%Y%m%d-%H%M%S")
    for i, item in enumerate(items):
        dest = out_dir / f"{prefix}-{ts}-{i + 1}.jpg"
        if item.get("b64_json"):
            dest.write_bytes(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            download(item["url"], dest, api_key, base_url)
        else:
            continue
        saved.append(str(dest.resolve()))
    return saved


# ---------- 生图 ----------
def cmd_image(args):
    base_url, api_key = load_config(args)
    body = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.n,
        "response_format": "b64_json",
    }
    # xAI 特有参数：中转站若不透传，这些会被忽略（脚本会在结果里提示实际尺寸）
    if args.aspect_ratio:
        body["aspect_ratio"] = args.aspect_ratio
    if args.resolution:
        body["resolution"] = args.resolution
    if args.quality:
        body["quality"] = args.quality
    resp = request("POST", f"{base_url}/images/generations", api_key, body)
    items = resp.get("data") or []
    if not items:
        die(f"响应里没有 data 字段: {json.dumps(resp, ensure_ascii=False)[:800]}")
    saved = save_image_items(items, args.out, "grok-image", api_key, base_url)
    print(json.dumps({"ok": True, "files": saved, "model": args.model,
                      "revised_prompt": items[0].get("revised_prompt")}, ensure_ascii=False))


# ---------- 改图 ----------
def cmd_edit(args):
    base_url, api_key = load_config(args)
    # xAI 的 /images/edits 要求 JSON（不是 multipart），参考图用 data URL 传
    body = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.n,
        "response_format": "b64_json",
    }
    if len(args.image) == 1:
        body["image"] = {"url": image_to_data_url(args.image[0])}
    else:
        body["images"] = [{"url": image_to_data_url(p)} for p in args.image]
    if args.aspect_ratio:
        body["aspect_ratio"] = args.aspect_ratio
    if args.resolution:
        body["resolution"] = args.resolution
    resp = request("POST", f"{base_url}/images/edits", api_key, body)
    items = resp.get("data") or []
    if not items:
        die(f"响应里没有 data 字段: {json.dumps(resp, ensure_ascii=False)[:800]}")
    saved = save_image_items(items, args.out, "grok-edit", api_key, base_url)
    print(json.dumps({"ok": True, "files": saved, "model": args.model}, ensure_ascii=False))


# ---------- 生视频 ----------
def poll_video(base_url, api_key, request_id, interval, timeout):
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        data = request("GET", f"{base_url}/videos/{request_id}", api_key, timeout=60)
        status = data.get("status")
        if status != last_status:
            print(json.dumps({"progress": status, "request_id": request_id}), file=sys.stderr)
            last_status = status
        if status == "done":
            return data
        if status in ("failed", "expired"):
            die(f"视频生成 {status}: {json.dumps(data, ensure_ascii=False)[:800]}")
        time.sleep(interval)
    die(f"轮询超时（{timeout}s）。可稍后用 `video-status {request_id}` 再查。")


def save_video(data, out_dir, request_id, api_key, base_url):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    url = (data.get("video") or {}).get("url")
    if not url:
        die(f"完成响应里没有 video.url: {json.dumps(data, ensure_ascii=False)[:800]}")
    dest = out_dir / f"grok-video-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    # 中转站可能返回 /v1/videos/... 相对路径，且内容接口要求 Bearer 认证。
    if url.startswith("/"):
        url = urljoin(base_url, url) if url.startswith("/v1/") else urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
    code, _ = _curl(["-H", f"Authorization: Bearer {api_key}", "-L", "-o", str(dest), url], 300)
    if code >= 400 or not dest.exists() or dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        print(json.dumps({"warn": f"下载失败（HTTP {code}），请用 url 手动下载"}), file=sys.stderr)
        return None, url
    return str(dest.resolve()), url


def cmd_video(args):
    base_url, api_key = load_config(args)
    body = {"model": args.model, "prompt": args.prompt}
    if args.duration:
        body["duration"] = args.duration
    if args.aspect_ratio:
        body["aspect_ratio"] = args.aspect_ratio
    if args.resolution:
        body["resolution"] = args.resolution
    if args.image:
        body["image"] = {"url": image_to_data_url(args.image)}
    resp = request("POST", f"{base_url}/videos/generations", api_key, body)
    request_id = resp.get("request_id") or resp.get("id")
    if not request_id:
        die(f"提交响应里没有 request_id: {json.dumps(resp, ensure_ascii=False)[:800]}")
    if args.no_wait:
        print(json.dumps({"ok": True, "request_id": request_id, "status": "submitted"}))
        return
    data = poll_video(base_url, api_key, request_id, args.interval, args.timeout)
    path, url = save_video(data, args.out, request_id, api_key, base_url)
    usage = data.get("usage") or {}
    cost = usage.get("cost_in_usd_ticks")
    print(json.dumps({"ok": True, "file": path, "url": url, "request_id": request_id,
                      "duration": (data.get("video") or {}).get("duration"),
                      "cost_usd": cost / 10_000_000_000 if isinstance(cost, (int, float)) else None}, ensure_ascii=False))


def cmd_video_status(args):
    base_url, api_key = load_config(args)
    data = request("GET", f"{base_url}/videos/{args.request_id}", api_key, timeout=60)
    if data.get("status") == "done" and args.out:
        path, url = save_video(data, args.out, args.request_id, api_key, base_url)
        usage = data.get("usage") or {}
        cost = usage.get("cost_in_usd_ticks")
        print(json.dumps({"ok": True, "status": "done", "file": path, "url": url,
                          "cost_usd": cost / 10_000_000_000 if isinstance(cost, (int, float)) else None}, ensure_ascii=False))
    else:
        print(json.dumps({"ok": True, **data}, ensure_ascii=False))


# ---------- CLI ----------
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url")
    p.add_argument("--api-key")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("image", help="文生图")
    s.add_argument("prompt")
    s.add_argument("--model", default="grok-imagine-image-2.0")
    s.add_argument("--n", type=int, default=1)
    s.add_argument("--aspect-ratio", help="1:1 16:9 9:16 4:3 3:4 3:2 2:3 等")
    s.add_argument("--resolution", help="1k 或 2k")
    s.add_argument("--quality", help="low / medium / auto（仅 grok-imagine-image-2.0）")
    s.add_argument("--out", default="./grok-output")
    s.set_defaults(func=cmd_image)

    s = sub.add_parser("edit", help="图生图 / 改图（走 /images/edits，JSON 格式）")
    s.add_argument("prompt")
    s.add_argument("--image", nargs="+", required=True, help="参考图路径，可多张")
    s.add_argument("--model", default="grok-imagine-image-2.0")
    s.add_argument("--n", type=int, default=1)
    s.add_argument("--aspect-ratio")
    s.add_argument("--resolution")
    s.add_argument("--out", default="./grok-output")
    s.set_defaults(func=cmd_edit)

    s = sub.add_parser("video", help="文生视频 / 图生视频（自动轮询到完成）")
    s.add_argument("prompt")
    s.add_argument("--model", default="grok-imagine-video-1.5")
    s.add_argument("--image", help="图生视频的输入图路径")
    s.add_argument("--duration", type=int, help="秒，如 8 / 10 / 12")
    s.add_argument("--aspect-ratio")
    s.add_argument("--resolution", help="480p / 720p / 1080p")
    s.add_argument("--interval", type=int, default=5)
    s.add_argument("--timeout", type=int, default=600)
    s.add_argument("--no-wait", action="store_true", help="只提交不等待，返回 request_id")
    s.add_argument("--out", default="./grok-output")
    s.set_defaults(func=cmd_video)

    s = sub.add_parser("video-status", help="查询 / 下载已提交的视频")
    s.add_argument("request_id")
    s.add_argument("--out", help="若已完成则下载到该目录")
    s.set_defaults(func=cmd_video_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
