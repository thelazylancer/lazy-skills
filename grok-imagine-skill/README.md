# grok-imagine-skill

一个给 Claude Code / Claude 桌面版用的 skill：通过 LinkCode（也兼容其他 OpenAI 兼容中转站）调用 Grok Imagine 生成图片、改图、生成视频。

- 零依赖：Python 3 标准库 + 系统 curl
- 文生图、改图（多参考图）、文生视频、图生视频，视频自动轮询到完成
- 走中转站时兼容 new-api / one-api 一类网关；针对 Cloudflare 挑战页做了规避（用 curl HTTP/2 而非 urllib）
- xAI 特有参数 `aspect_ratio` / `resolution` / `quality` 原样透传

## 安装

### Claude Code

```bash
git clone https://github.com/MasamiYui/grok-imagine-skill.git ~/.claude/skills/grok-imagine
```

### Claude 桌面版

桌面版 skill 只能存单个 SKILL.md，把 `scripts/grok_media.py` 的内容内嵌进 SKILL.md（让 Claude 先写到 `/tmp` 再执行）后用「保存技能」导入。

## 配置

三选一，优先级从高到低：

```bash
# 1. 命令行参数
python3 scripts/grok_media.py --base-url https://your-relay/v1 --api-key sk-xxx image "..."

# 2. 环境变量（LinkCode 默认 base URL 可省略）
export GROK_BASE_URL=https://api-fast.linkcode.site/v1
export GROK_API_KEY=sk-xxx

# 3. 配置文件 ~/.config/grok-relay/config.json
{"base_url": "https://your-relay/v1", "api_key": "sk-xxx"}
```

不给 base_url 时默认使用 `https://api-fast.linkcode.site/v1`。也兼容旧变量名 `GROK_RELAY_BASE_URL` / `GROK_RELAY_API_KEY`。

## 用法

```bash
S=scripts/grok_media.py

python3 $S image "a red fox sitting in fresh snow, golden hour" --aspect-ratio 16:9 --out ./out
python3 $S image "..." --model grok-imagine-image-2.0 --quality medium --resolution 2k --n 2
python3 $S edit "make it night, add northern lights" --image ./out/fox.jpg
python3 $S video "gentle ocean waves at sunset, slow pan" --duration 5 --resolution 480p --out ./out
python3 $S video "make the water move" --image ./out/fox.jpg --model grok-imagine-video-1.5
python3 $S video "..." --no-wait          # 只提交，返回 request_id
python3 $S video-status <request_id> --out ./out
```

输出是一行 JSON，例如 `{"ok": true, "files": ["/abs/path/grok-image-...jpg"], ...}`；视频还会返回 `request_id` 和 API 报告的 `cost_usd`。

## 模型

| 模型 | 用途 | 备注 |
|---|---|---|
| `grok-imagine-image` | 文生图 / 改图 | 默认，约 $0.02/张 |
| `grok-imagine-image-2.0` | 文生图 / 改图 | 支持 `--quality`、21:9 等宽高比、多参考图，约 $0.04/张 |
| `grok-imagine-image-quality` | 文生图 | 高质量档，xAI 已标记弃用 |
| `grok-imagine-video` | 文生视频 / 图生视频 | 按秒计费约 $0.05/秒 |
| `grok-imagine-video-1.5` | 图生视频 | 原生 1080p，仅图生视频 |

`--model` 不做白名单校验，中转站有什么就能传什么。

## 中转站注意事项

- `aspect_ratio` 等 xAI 特有字段不在 OpenAI 标准 schema 里，new-api 一类网关可能会丢掉，需要在渠道设置里开"请求体透传"。先用 16:9 生一张看尺寸就知道有没有透传。
- 视频需要中转站同时代理 `POST /v1/videos/generations` 和 `GET /v1/videos/{id}` 两条路径。
- 视频完成后 LinkCode 可能返回 `/v1/videos/...` 相对路径，脚本会补全中转站地址并用 Bearer 认证立即下载；下载失败时会把 URL 原样返回。

## 额外：MCP server 版本

`extras/mcp-server.py` 是同样功能的极简 FastMCP 实现（需要 `pip install "mcp[cli]" httpx`），适合想在 Cursor / Codex 等多个 MCP 客户端复用的场景。注意它用 httpx 而非 curl，遇到 Cloudflare 挑战时可能被拦。

## License

MIT
