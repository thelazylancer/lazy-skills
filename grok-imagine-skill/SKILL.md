---
name: grok-imagine
description: 通过 xAI 官方 API 或任意 OpenAI 兼容中转站调用 Grok Imagine 生成图片、改图、生成视频。当用户说"画一张…"、"生成图片/配图/海报"、"把这张图改成…"、"生成一段视频"、"图生视频"、"用 grok 画/生成"时使用。
---

# Grok Imagine

通过 xAI 官方 API 或 OpenAI 兼容中转站调用 Grok Imagine 做文生图、改图、文生视频、图生视频。
所有调用都通过 `scripts/grok_media.py` 完成，只依赖 Python 3 标准库和系统 curl。

## 第一步：确认配置

脚本按顺序找配置：`--base-url` / `--api-key` 参数 → 环境变量 `GROK_BASE_URL` / `GROK_API_KEY`（也兼容 `GROK_RELAY_*`）→ `~/.config/grok-relay/config.json`。base_url 缺省为 `https://api-fast.linkcode.site/v1`。

先跑一次 `python3 scripts/grok_media.py video-status probe`：返回 `Malformed request ID` 之类的上游错误说明配置正确；返回"缺少 api_key"就向用户索要 key，之后在本会话内用 `--api-key` 传入。**绝不要把 key 回显到对话文本里、写进输出文件或存进记忆。**

## 第二步：改写提示词

Grok Imagine 对英文、具体、带风格与镜头描述的提示词效果明显更好。把用户的需求改写成一段英文提示词（主体 + 场景 + 风格 + 光线/构图/镜头），直接用，不必让用户确认。用户明确给了英文提示词就原样用。

## 第三步：选模型与参数

xAI 当前的模型（2026-09）：
- 图片：`grok-imagine-image`（默认，最便宜约 $0.02/张）、`grok-imagine-image-2.0`（支持 `--quality`、更多宽高比、多参考图编辑，约 $0.04/张）、`grok-imagine-image-quality`（高质量档，已标记弃用）
- 视频：`grok-imagine-video`（按秒计费约 $0.05/秒）、`grok-imagine-video-1.5`（原生 1080p，仅图生视频）

中转站上可能只有其中一部分，报 404 / model not found 时用 `GET /v1/models` 查一下或问用户。默认用便宜的；用户要求高质量再升级。视频默认 5–8 秒、480p 或 720p，用户没说就不要选 1080p 或长时长。

## 第四步：执行

文生图：
```bash
python3 scripts/grok_media.py image "<english prompt>" --aspect-ratio 16:9 --out <outdir>
python3 scripts/grok_media.py image "<prompt>" --model grok-imagine-image-2.0 --quality medium --resolution 2k --n 2 --out <outdir>
```

改图 / 图生图（可多张参考图）：
```bash
python3 scripts/grok_media.py edit "<english prompt>" --image <path1> [<path2> ...] --out <outdir>
```

文生视频（脚本自动每 5 秒轮询，5 秒视频实测约 30 秒完成）：
```bash
python3 scripts/grok_media.py video "<english prompt>" --duration 5 --aspect-ratio 16:9 --resolution 480p --out <outdir>
```

图生视频：
```bash
python3 scripts/grok_media.py video "<english prompt>" --image <path> --duration 5 --out <outdir>
```

只提交不等待 / 稍后查询下载：
```bash
python3 scripts/grok_media.py video "<prompt>" --no-wait
python3 scripts/grok_media.py video-status <request_id> --out <outdir>
```

## 第五步：展示结果

脚本 stdout 是一行 JSON。图片：用 Read 工具打开 `files` 里的路径让用户看到。视频：`file` 非空就给文件路径；下载失败时 `url` 会保留，方便稍后用 `video-status` 重试。完成的视频结果还包含 `request_id` 和 API 报告的 `cost_usd`。

## 参数速查

- `--aspect-ratio`：图片 `1:1 16:9 9:16 4:3 3:4 3:2 2:3 2:1 1:2`（2.0 另支持 `21:9`）；视频 `1:1 16:9 9:16 4:3 3:4 3:2 2:3`
- `--resolution`：图片 `1k`（默认）/ `2k`；视频 `480p` / `720p` / `1080p`
- `--quality`：`low` / `medium` / `auto`，只有 `grok-imagine-image-2.0` 支持
- `--n`：1–10，按张计费
- `--duration`：视频秒数，按秒计费

## 已知情况

- 脚本走 curl（HTTP/2）而不是 urllib：部分中转站前面有 Cloudflare，会对 Python urllib / HTTP1.1 客户端返回 403 挑战页。脚本报"被 Cloudflare 挑战页拦截"时是 WAF 问题不是 API 问题。
- 中转站可能不透传 `aspect_ratio` / `resolution` / `quality`（如 new-api 未开"请求体透传"）。出图一直是 1:1 就是这个原因。
- 旧模型 `grok-2-image` 不支持任何尺寸参数，传了会报 400。
- `/images/edits` 在 xAI 这边要求 JSON 而不是 multipart，脚本已按 JSON 发送。
- 视频接口返回的 URL 是临时链接，脚本会立即下载。
- 脚本用 `response_format: b64_json` 取图，不依赖中转站代理图片 URL。
