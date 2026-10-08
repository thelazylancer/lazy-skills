---
name: buffer-post
description: "Publish thelazybabyx content to X, Instagram, and TikTok through Buffer: uploads local media to the ImgBed host (imgs.thelazystudio.net), then creates a Buffer post as a draft, queued, scheduled, or immediate post."
version: 2.0.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [buffer, twitter, x, instagram, tiktok, social-media, publishing, video]
---

# buffer-post

Posts to X @thelazylan, Instagram @thelazybabyx, and TikTok @thelazybabyx via Buffer. The former @thelazybabyx handle is retired for X only; Instagram and TikTok remain @thelazybabyx. Verify the live channel identity before every account-specific write. One script does the whole flow:
local media → ImgBed upload (public https URL) → Buffer `createPost`.

Credentials (`IMGBED_URL`, `IMGBED_AUTH_CODE`, `BUFFER_API_KEY`) live in the profile `.env`. Never print, echo, or read them into the conversation.

## Hard rule: review in chat before any Buffer write

Show the owner the exact text, image(s), platform/handle, intended mode and due time in chat first. Do not put unrevised or unapproved content into Buffer, even as a draft; the pre-approval review happens in chat, not in Buffer. Wait for explicit approval of that displayed content. After approval, execute the approved action directly (for example, `schedule` with the approved `--due-at` when they said to schedule, or `now` when they said to publish now); do not make an intermediate draft unless the owner explicitly requests a Buffer draft. “没问题/可以/直接定时” after the exact review packet authorizes only the displayed copy, assets, channel and time. After every Buffer write, read back the exact post and verify status, text, due time, channel and attached assets before reporting success.

## Batch approval for scheduled/overnight posts

- To avoid asking between individual posts, the owner may approve one exact batch at once. Before scheduling, show every item's final copy, image(s), target channel, mode, and due time. One explicit approval of that displayed batch authorizes those exact items only; do not ask again per item in the same approved batch.
- A blanket request such as “post hourly,” the owner's being asleep, or approval of a previous post does not approve future content that has not been shown. Save unapproved future content as drafts; do not queue, schedule, or publish it.
- If a selected account/channel does not match the owner's target or its authorization is uncertain, pause and clarify before publishing.

## Usage

```bash
S=~/.hermes/skills/social-media/buffer-post/scripts/buffer_post.py

# X: single image, save as draft (default, not published)
python3 $S --platform x --text "傍晚的风刚刚好～" --image ~/workspace/out/a.png

# Timed X drafts are currently disabled in this profile after Buffer auto-published posts created with draft + --due-at.
# Use plain draft mode without --due-at; the owner must add a time manually in Buffer.
python3 $S --platform x --text "你们晚上一般几点睡？" --mode draft

# X: text only, add to Buffer queue
python3 $S --platform x --text "你们晚上一般几点睡？" --mode queue

# Instagram carousel, scheduled (Beijing time), hashtags at the end of the caption
python3 $S --platform instagram --ig-type carousel \
  --text "第一行要抓人…

#杭州 #日常 #ootd" --image a.png --image b.png --image c.png \
  --mode schedule --due-at "2026-10-01 20:00"

# TikTok: video post, scheduled
python3 $S --platform tiktok --text "新作品来了！#创作灵感 #tiktok" \
  --video output.mp4 --mode schedule --due-at "2026-10-08 19:00"

# TikTok: photo carousel (up to 35 images)
python3 $S --platform tiktok --text "周末随拍 📸" \
  --image a.jpg --image b.jpg --image c.jpg --mode draft

# Preview payload without uploading or posting
python3 $S --platform instagram --text "..." --image a.png --dry-run
```

### Options

| Flag | Meaning |
|---|---|
| `--platform` | `x`, `instagram`, or `tiktok` |
| `--text` | Post text / caption |
| `--image` | Local image, repeatable, order kept |
| `--video` | Local video (TikTok only; MP4/MOV/WEBM, max 10min, max 1GB) |
| `--image-url` | Already-hosted public https URL, repeatable |
| `--mode` | `draft` (default), `queue` (next Buffer slot), `schedule` (needs `--due-at`), `now` (publish immediately) |
| `--due-at` | Beijing time (Asia/Shanghai). `--mode schedule` auto-publishes at that time. In this profile, `--mode draft --due-at` was observed turning into scheduled/published posts; the script now rejects that combination. Use plain drafts without `--due-at` until a safe preset-time workflow is verified. |
| `--ig-type` | `post`, `carousel`, `story`, `reel` (Instagram only) |
| `--first-comment` | Instagram first comment. **Needs a paid Buffer plan.** The account is on the free plan, so don't use it. Put hashtags at the end of `--text` instead |
| `--ai-label` | Mark Instagram post as AI-generated (off by default) |
| `--dry-run` | Print payload only |

The script prints JSON with `post_id`, `status`, `due_at`, and the uploaded `media_urls`. Report these to the owner.

## Platform notes

### All platforms
- Before upload, every local `--image` is rebuilt with Pillow after correcting orientation and converting embedded color profiles to sRGB. Original metadata (including XMP/text/C2PA) is removed, then fresh Apple / iPhone 17 Pro Max EXIF camera parameters are written. JPEG stays JPEG; other formats become PNG. Originals are left untouched.
- Every local `--video` is re-encoded with ffmpeg to strip all metadata (XMP, location, creation time, etc.). Video stays in its original format (MP4/MOV/WEBM). Originals are left untouched.
- `--image-url` inputs are passed through as-is (no metadata processing).
- `--dry-run` processes media locally and previews the payload without credentials, uploads or Buffer requests.
- Every local image automatically gets iPhone 17 Pro Max main-camera parameters (6.765mm, f/1.78, 24mm equivalent) and current local time.
- Buffer fetches media at publish time. ImgBed URLs are permanent public links, so scheduled posts are fine.

### Instagram
- Requires at least one image
- Recommended aspect ratios: 4:5 (1080×1350) for feed posts/carousels, 9:16 (1080×1920) for stories/reels
- Images not marked as AI-generated by default (owner's choice). Pass `--ai-label` only if the owner asks
- For photorealistic Reels (video), remind the owner that Meta requires AI disclosure for realistic video
- Max 10 images per carousel

### X (Twitter)
- Accepts up to 4 images, or text only
- Images optional

### TikTok
- Supports video (MP4/MOV/WEBM, max 10 minutes, max 1GB) or photo carousel (up to 35 images)
- Cannot mix video and images in one post
- **Music limitation**: Buffer API cannot access TikTok's music library. Options:
  1. Upload video with audio track already mixed in (recommended for AI-generated content)
  2. Use Buffer's notification publishing to manually add music in the TikTok app
- Videos should use royalty-free music or your own music to avoid copyright issues
- TikTok posts default to allowing comments, duets, and stitches

## Buffer free-plan scheduled-post cap

- This profile's Buffer free plan rejects a batch once there are 10 scheduled posts, with `Scheduled posts limit reached. You have 10 scheduled posts out of 10 allowed.` Before a large schedule batch, read the current scheduled count and compare it with remaining capacity. Create only posts that fit; do not retry rejected posts, switch them to `now`/queue, or otherwise work around the plan cap. Report the remaining items and wait until a slot becomes available or the owner changes the plan/instructions.

## Environment variables

The script reads from `~/.hermes/profiles/thelazybabyx/.env`:

```bash
IMGBED_URL=https://imgs.thelazystudio.net
IMGBED_AUTH_CODE=<your_token>
BUFFER_API_KEY=<your_buffer_key>
BUFFER_CHANNEL_X=<x_channel_id>
BUFFER_CHANNEL_INSTAGRAM=<instagram_channel_id>
BUFFER_CHANNEL_TIKTOK=<tiktok_channel_id>
```

Channel IDs come from Buffer's GraphQL API or web UI. Never print credentials.

## Errors

- `Unauthorized` from upload: the ImgBed token is wrong or expired. Ask the owner to update `IMGBED_AUTH_CODE`.
- `HTTP 403 error code: 1010` from upload: Cloudflare blocked the request's User-Agent. The script already sends a custom UA. If this shows up again, the owner needs to relax the bot rule in Cloudflare.
- `First comment requires a paid plan`: drop `--first-comment`.
- `Buffer HTTP 401`: `BUFFER_API_KEY` is wrong or revoked.
- `Buffer error: ...`: a MutationError, such as a bad channel, a missing image for IG, or a daily limit. Show the message to the owner.
- `429`: Buffer rate limit (100 per 15 min, 250 per day). Wait and retry later.
- `TikTok videos must be ≤600s` or `≤1024MB`: video exceeds TikTok's limits. Compress or trim the video.
- `ffmpeg not found`: Install ffmpeg for video metadata stripping (`brew install ffmpeg` on macOS).
