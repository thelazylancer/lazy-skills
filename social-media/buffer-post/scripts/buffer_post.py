#!/usr/bin/env python3
"""Upload media to the ImgBed host and create a Buffer post for X, Instagram, or TikTok.

Reads IMGBED_URL, IMGBED_AUTH_CODE and BUFFER_API_KEY from the environment,
falling back to the thelazybabyx profile .env. Never prints credentials.
"""
import argparse
import json
import logging
import mimetypes
import os
import random
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

BUFFER_API = "https://api.buffer.com"
# Cloudflare in front of ImgBed blocks urllib's default UA (error 1010).
USER_AGENT = "buffer-post/1.0 (+https://thelazystudio.net)"
BEIJING = ZoneInfo("Asia/Shanghai")
PROFILE_ENV = Path.home() / ".hermes/profiles/thelazybabyx/.env"

# Platform constraints
IG_MAX_IMAGES = 10
IG_MAX_FILE_MB = 30
IG_MAX_DIMENSION = 8000
TIKTOK_MAX_IMAGES = 35  # TikTok photo carousel limit
TIKTOK_MAX_VIDEO_MB = 1024
TIKTOK_MAX_DURATION_SEC = 600  # 10 minutes
TIKTOK_MAX_IMAGES = 10

logger = logging.getLogger(__name__)


def camera_exif():
    """Build fixed iPhone main-camera tags with the current local time."""
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational

    model = "iPhone 17 Pro Max"
    focal, aperture, equivalent = 6.765, 1.78, 24
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y:%m:%d %H:%M:%S")
    offset = now.strftime("%z")
    offset = offset[:3] + ":" + offset[3:]
    shutter, iso = random.choice([(120, 50), (240, 64), (500, 80), (60, 100), (320, 64)])
    lens_info = (2.22, 16.89, 1.78, 2.8)
    exif = Image.Exif()
    exif.update({271: "Apple", 272: model, 305: "26.0", 316: model,
                 274: 1, 306: stamp})
    exif[34665] = {
        42035: "Apple", 42036: f"{model} back triple camera {focal:g}mm f/{aperture:g}",
        42034: tuple(IFDRational(Fraction(str(v))) for v in lens_info),
        37386: IFDRational(Fraction(str(focal))), 33437: IFDRational(Fraction(str(aperture))), 41989: equivalent,
        33434: IFDRational(1, shutter), 34855: iso, 34850: 2,
        37383: 5, 37385: 16, 41987: 0,
        36867: stamp, 36868: stamp, 36880: offset, 36881: offset, 36882: offset,
    }
    return exif


def load_env():
    if PROFILE_ENV.exists():
        for line in PROFILE_ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    missing = [k for k in ("IMGBED_URL", "IMGBED_AUTH_CODE", "BUFFER_API_KEY", "BUFFER_CHANNEL_X", "BUFFER_CHANNEL_INSTAGRAM") if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")


def to_utc(value: str) -> str:
    """Parse a Beijing-time string (or any ISO time with an explicit offset) into Buffer's UTC format."""
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"bad --due-at {value!r}; use Beijing time like '2026-10-01 20:00'")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING)
    if dt <= datetime.now(timezone.utc):
        sys.exit(f"--due-at {value!r} is in the past (Beijing time)")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def to_srgb(im):
    """Convert an image with an embedded ICC profile (e.g. iPhone Display P3) to sRGB.

    The profile is dropped on save, so without this wide-gamut photos would look washed out.
    """
    icc = im.info.get("icc_profile")
    if not icc:
        return im
    try:
        from io import BytesIO
        from PIL import ImageCms
        src = ImageCms.ImageCmsProfile(BytesIO(icc))
        dst = ImageCms.createProfile("sRGB")
        mode = "RGBA" if "A" in im.getbands() else "RGB"
        return ImageCms.profileToProfile(im.convert(mode), src, dst, outputMode=mode)
    except Exception:
        return im  # unusable profile or no LittleCMS: keep pixels as-is


def check_image_constraints(path: Path, platform: str):
    """Check image size and dimensions against platform limits."""
    from PIL import Image

    size_mb = path.stat().st_size / (1024 * 1024)
    with Image.open(path) as im:
        width, height = im.size

    if platform == "instagram":
        if size_mb > IG_MAX_FILE_MB:
            logger.warning(f"{path.name}: {size_mb:.1f}MB exceeds Instagram's {IG_MAX_FILE_MB}MB limit")
        if width > IG_MAX_DIMENSION or height > IG_MAX_DIMENSION:
            logger.warning(f"{path.name}: {width}x{height} exceeds Instagram's {IG_MAX_DIMENSION}px limit")


def strip_metadata(path: Path, workdir: Path) -> Path:
    """Remove source metadata and write fresh iPhone camera EXIF to a temporary copy.

    Runs locally with Pillow; C2PA, XMP, ICC and text chunks are not carried over.
    JPEG input stays JPEG (PNG would bloat photos several times); everything else becomes PNG.
    """
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im.load()
        exif = camera_exif()
        is_jpeg = im.format in ("JPEG", "MPO")
        # Bake EXIF Orientation into the pixels, otherwise portrait shots upload sideways.
        im = to_srgb(ImageOps.exif_transpose(im))
        if is_jpeg:
            mode = "L" if im.mode in ("L", "LA") else "RGB"
        else:
            mode = im.mode if im.mode in ("RGB", "RGBA", "L", "LA") else "RGBA"
        clean = Image.new(mode, im.size)
        clean.paste(im.convert(mode))

    # Only our generated EXIF is saved; no source metadata is carried over.
    if is_jpeg:
        dest = workdir / (path.stem + "-" + uuid.uuid4().hex + ".jpg")
        clean.save(dest, format="JPEG", quality=95, optimize=True, exif=exif)
    else:
        dest = workdir / (path.stem + "-" + uuid.uuid4().hex + ".png")
        clean.save(dest, format="PNG", optimize=True, exif=exif)
    verify_clean(dest, exif)
    return dest


def verify_clean(path: Path, expected=None):
    """Check that only the generated camera EXIF survived the pixel rebuild."""
    from PIL import Image

    with Image.open(path) as im:
        im.load()
        leftover = [k for k in ("icc_profile", "xmp", "XML:com.adobe.xmp", "caBX", "jumbf") if k in im.info]
        actual = im.getexif()
        if expected is None:
            if len(actual):
                leftover.append("EXIF tags")
        else:
            if set(actual) != set(expected) or any(actual[k] != expected[k] for k in expected if k != 34665):
                leftover.append("unexpected camera EXIF")
            if actual.get_ifd(34665) != expected[34665]:
                leftover.append("unexpected camera parameters")
        if getattr(im, "text", None):
            leftover.append("text chunks")
        # Check PNG private chunks for C2PA
        for chunk in getattr(im, "private_chunks", []):
            if chunk[0] in (b"caBX", b"jumb"):
                leftover.append("C2PA chunk")
                break
    if leftover:
        sys.exit(f"metadata not fully stripped from {path.name}: {', '.join(leftover)}")


def strip_video_metadata(path: Path, workdir: Path) -> Path:
    """Remove all metadata from video using ffmpeg.

    Strips title, comment, creation_time, location, and all other metadata tags.
    Keeps only video/audio streams with no metadata attached.
    """
    import subprocess

    dest = workdir / (path.stem + "-" + uuid.uuid4().hex + path.suffix)
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-map_metadata", "-1",  # Strip all global metadata
        "-map_metadata:s:v", "-1",  # Strip video stream metadata
        "-map_metadata:s:a", "-1",  # Strip audio stream metadata
        "-codec", "copy",  # Copy streams without re-encoding
        "-fflags", "+bitexact",  # Reproducible output
        "-loglevel", "error",
        str(dest)
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as e:
        sys.exit(f"ffmpeg failed on {path.name}: {e.stderr.decode(errors='replace')}")
    except subprocess.TimeoutExpired:
        sys.exit(f"ffmpeg timed out processing {path.name} (>5 minutes)")

    if not dest.exists() or dest.stat().st_size == 0:
        sys.exit(f"ffmpeg produced empty output for {path.name}")

    verify_video_clean(dest)
    return dest


def verify_video_clean(path: Path):
    """Check that ffmpeg actually stripped metadata."""
    import subprocess

    cmd = ["ffprobe", "-v", "error", "-show_entries", "format_tags:stream_tags",
           "-of", "json", str(path)]
    try:
        out = subprocess.check_output(cmd, timeout=30).decode()
        data = json.loads(out)
        tags = []
        if data.get("format", {}).get("tags"):
            tags.append(f"format tags: {list(data['format']['tags'].keys())}")
        for stream in data.get("streams", []):
            if stream.get("tags"):
                tags.append(f"stream tags: {list(stream['tags'].keys())}")
        if tags:
            sys.exit(f"metadata not fully stripped from {path.name}: {', '.join(tags)}")
    except subprocess.CalledProcessError as e:
        sys.exit(f"ffprobe verification failed: {e.stderr.decode(errors='replace')}")
    except subprocess.TimeoutExpired:
        sys.exit(f"ffprobe timed out on {path.name}")


def get_video_info(path: Path) -> dict:
    """Get video duration, dimensions, and size."""
    import subprocess

    cmd = ["ffprobe", "-v", "error", "-show_entries",
           "format=duration,size:stream=width,height,codec_type",
           "-of", "json", str(path)]
    try:
        out = subprocess.check_output(cmd, timeout=30).decode()
        data = json.loads(out)
        fmt = data.get("format", {})
        video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        return {
            "duration": float(fmt.get("duration", 0)),
            "size_mb": int(fmt.get("size", 0)) / (1024 * 1024),
            "width": video.get("width", 0),
            "height": video.get("height", 0),
        }
    except subprocess.CalledProcessError as e:
        sys.exit(f"ffprobe failed on {path.name}: {e.stderr.decode(errors='replace')}")
    except (ValueError, KeyError) as e:
        sys.exit(f"failed to parse video info for {path.name}: {e}")


def is_video(path: Path) -> bool:
    """Check if file is a video based on extension."""
    return path.suffix.lower() in {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}


def upload_with_retry(path: Path, max_retries=3) -> str:
    """Upload one file to ImgBed with exponential backoff retry."""
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    url = os.environ["IMGBED_URL"].rstrip("/") + "/upload?returnFormat=full&uploadFolder=thelazybabyx"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": "Bearer " + os.environ["IMGBED_AUTH_CODE"],
        "User-Agent": USER_AGENT,
    })

    for attempt in range(max_retries):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=120))
            item = data[0] if isinstance(data, list) else data
            src = item.get("publicUrl") or item.get("src") or ""
            if not src.startswith("https://"):
                sys.exit(f"upload returned no public https URL for {path.name}: {item}")
            logger.info(f"uploaded {path.name} -> {src}")
            return src
        except urllib.error.HTTPError as e:
            err_body = e.read()[:200].decode(errors='replace')
            if attempt < max_retries - 1 and e.code >= 500:
                wait = 2 ** attempt
                logger.warning(f"upload {path.name} failed (HTTP {e.code}), retry in {wait}s...")
                time.sleep(wait)
            else:
                sys.exit(f"upload failed for {path.name} after {attempt + 1} attempts: HTTP {e.code} {err_body}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"upload {path.name} network error, retry in {wait}s...")
                time.sleep(wait)
            else:
                sys.exit(f"upload failed for {path.name} after {attempt + 1} attempts: {e}")


def buffer_query(query: str, variables: dict) -> dict:
    req = urllib.request.Request(BUFFER_API, data=json.dumps({"query": query, "variables": variables}).encode(), headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ["BUFFER_API_KEY"],
        "User-Agent": USER_AGENT,
    })
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        sys.exit(f"Buffer HTTP {e.code}: {e.read()[:500].decode(errors='replace')}")


def parse_buffer_error(out: dict, res: dict) -> str:
    """Parse Buffer error and return a friendly message."""
    msg = out.get("message") or ""
    errors = res.get("errors") or []

    # Common error patterns
    if "rate limit" in msg.lower() or any("rate limit" in str(e).lower() for e in errors):
        return "Buffer rate limit reached. Free plan allows 10 posts/day per channel."
    if "unauthorized" in msg.lower() or any("unauthorized" in str(e).lower() for e in errors):
        return "Buffer API key expired or invalid. Check BUFFER_API_KEY in .env"
    if "channel" in msg.lower() and "not found" in msg.lower():
        return f"Channel not found. Check BUFFER_CHANNEL_X / BUFFER_CHANNEL_INSTAGRAM / BUFFER_CHANNEL_TIKTOK in .env"
    if "image" in msg.lower() or "media" in msg.lower() or "video" in msg.lower():
        return f"Media rejected by Buffer: {msg}"

    return f"Buffer error: {msg or errors}"


def check_media_constraints(path: Path, platform: str):
    """Check platform-specific media file constraints."""
    if is_video(path):
        info = get_video_info(path)
        if platform == "tiktok":
            if info["duration"] > TIKTOK_MAX_DURATION_SEC:
                sys.exit(f"{path.name}: TikTok videos must be ≤{TIKTOK_MAX_DURATION_SEC}s (got {info['duration']:.1f}s)")
            if info["size_mb"] > TIKTOK_MAX_VIDEO_MB:
                sys.exit(f"{path.name}: TikTok videos must be ≤{TIKTOK_MAX_VIDEO_MB}MB (got {info['size_mb']:.1f}MB)")
    else:
        # Image constraints
        if platform == "instagram":
            from PIL import Image
            with Image.open(path) as im:
                if max(im.width, im.height) > IG_MAX_DIMENSION:
                    sys.exit(f"{path.name}: Instagram images must be ≤{IG_MAX_DIMENSION}px (got {im.width}x{im.height})")
                size_mb = path.stat().st_size / (1024 * 1024)
                if size_mb > IG_MAX_FILE_MB:
                    sys.exit(f"{path.name}: Instagram images must be ≤{IG_MAX_FILE_MB}MB (got {size_mb:.1f}MB)")


def main():
    p = argparse.ArgumentParser(description="Create Buffer posts for X, Instagram, or TikTok.")
    p.add_argument("--platform", required=True, choices=["x", "instagram", "tiktok"])
    p.add_argument("--text", required=True, help="Post text / caption")
    p.add_argument("--image", action="append", default=[], help="Local image path (repeatable, order kept)")
    p.add_argument("--video", help="Local video path (TikTok only)")
    p.add_argument("--image-url", action="append", default=[], help="Already-hosted public https image URL (repeatable)")
    p.add_argument("--mode", default="draft", choices=["draft", "queue", "schedule", "now"],
                   help="draft (default; unpublished; may use --due-at as a preset time) | queue | schedule (auto-publish; needs --due-at) | now")
    p.add_argument("--due-at", help="Beijing time (Asia/Shanghai); with draft, preset the time without publishing; with schedule, auto-publish then")
    p.add_argument("--ig-type", default="post", choices=["post", "carousel", "story", "reel"],
                   help="Instagram post type")
    p.add_argument("--first-comment", help="Instagram first comment (e.g. hashtags)")
    p.add_argument("--ai-label", action="store_true", help="Mark the Instagram post as AI-generated (off by default)")
    p.add_argument("--log-file", help="Optional log file path for upload/post history")
    p.add_argument("--dry-run", action="store_true", help="Prepare images locally and print the payload, without uploading or posting")
    a = p.parse_args()

    # Setup logging
    log_level = logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    handlers = [logging.StreamHandler(sys.stderr)]
    if a.log_file:
        handlers.append(logging.FileHandler(Path(a.log_file).expanduser()))
    logging.basicConfig(level=log_level, format=log_format, handlers=handlers)

    if a.mode == "schedule" and not a.due_at:
        sys.exit("--mode schedule requires --due-at")
    if a.due_at and a.mode not in {"draft", "schedule"}:
        sys.exit("--due-at is only supported with --mode draft or --mode schedule")
    if a.mode == "draft" and a.due_at:
        sys.exit("Unsafe in this Buffer account: draft + --due-at can become scheduled and publish automatically. Use plain --mode draft without --due-at until a safe preset-time draft flow is verified.")

    # Check Instagram carousel limit
    total_images = len(a.image) + len(a.image_url)
    if a.platform == "instagram" and total_images > IG_MAX_IMAGES:
        sys.exit(f"Instagram allows max {IG_MAX_IMAGES} images per post, got {total_images}")

    # Check TikTok constraints
    if a.platform == "tiktok":
        if a.video and (a.image or a.image_url):
            sys.exit("TikTok: cannot mix video and images in one post")
        if not a.video and not a.image and not a.image_url:
            sys.exit("TikTok posts need at least one video or image")
        total_media = len(a.image) + len(a.image_url)
        if not a.video and total_media > TIKTOK_MAX_IMAGES:
            sys.exit(f"TikTok allows max {TIKTOK_MAX_IMAGES} images per post, got {total_media}")

    if not a.dry_run:
        load_env()

    # Load channel IDs from environment
    channels = {
        "x": os.environ.get("BUFFER_CHANNEL_X"),
        "instagram": os.environ.get("BUFFER_CHANNEL_INSTAGRAM"),
        "tiktok": os.environ.get("BUFFER_CHANNEL_TIKTOK"),
    }
    if not a.dry_run and not channels.get(a.platform):
        sys.exit(f"BUFFER_CHANNEL_{a.platform.upper()} not set in environment")

    # Collect media files
    media_files = []
    if a.video:
        video_path = Path(a.video).expanduser()
        if not video_path.is_file():
            sys.exit(f"video not found: {video_path}")
        if not is_video(video_path):
            sys.exit(f"{video_path.name} is not a recognized video format")
        media_files.append(video_path)

    for img_path in a.image:
        path = Path(img_path).expanduser()
        if not path.is_file():
            sys.exit(f"image not found: {path}")
        media_files.append(path)

    inp = {
        "channelId": channels[a.platform],
        "text": a.text,
        "schedulingType": "automatic",
        "mode": {
            "draft": "customScheduled" if a.due_at else "addToQueue",
            "queue": "addToQueue",
            "schedule": "customScheduled",
            "now": "shareNow",
        }[a.mode],
    }
    if a.mode == "draft":
        inp["saveToDraft"] = True
    if a.mode in {"draft", "schedule"} and a.due_at:
        inp["dueAt"] = to_utc(a.due_at)

    # Platform-specific metadata
    if a.platform == "instagram":
        if not (media_files or a.image_url):
            sys.exit("Instagram posts need at least one image")
        ig = {"type": a.ig_type, "shouldShareToFeed": True}
        if a.ai_label:
            ig["isAiGenerated"] = True
        if a.first_comment:
            ig["firstComment"] = a.first_comment
        inp["metadata"] = {"instagram": ig}
    elif a.platform == "tiktok":
        if not (media_files or a.image_url):
            sys.exit("TikTok posts need at least one video or image")
        # TikTok metadata (Buffer API specific fields)
        tiktok = {"allowComments": True, "allowDuet": True, "allowStitch": True}
        inp["metadata"] = {"tiktok": tiktok}

    with tempfile.TemporaryDirectory(prefix="buffer-post-") as tmp:
        # Strip metadata from all media files
        cleaned = []
        for path in media_files:
            if is_video(path):
                logger.info(f"stripping video metadata from {path.name}...")
                cleaned.append(strip_video_metadata(path, Path(tmp)))
            else:
                cleaned.append(strip_metadata(path, Path(tmp)))

        for c in cleaned:
            check_media_constraints(c, a.platform)

        if a.dry_run:
            files = []
            for src, dst in zip(media_files, cleaned):
                if is_video(dst):
                    info = get_video_info(dst)
                    files.append({
                        "source": str(src),
                        "type": "video",
                        "format": dst.suffix.lstrip('.').upper(),
                        "duration": f"{info['duration']:.1f}s",
                        "size": f"{info['width']}x{info['height']}",
                        "bytes": dst.stat().st_size,
                        "source_bytes": src.stat().st_size,
                    })
                else:
                    from PIL import Image
                    with Image.open(dst) as im:
                        files.append({
                            "source": str(src),
                            "type": "image",
                            "format": im.format,
                            "size": f"{im.width}x{im.height}",
                            "bytes": dst.stat().st_size,
                            "source_bytes": src.stat().st_size,
                            "camera": im.getexif().get(272),
                            "lens": im.getexif().get_ifd(34665).get(42036) if im.getexif().get_ifd(34665) else None,
                        })

            # Build preview assets - Buffer treats videos and images the same in assets array
            preview_assets = []
            for c in cleaned:
                if is_video(c):
                    preview_assets.append({"video": {"url": f"<upload:{c.name}>"}})
                else:
                    preview_assets.append({"image": {"url": f"<upload:{c.name}>"}})
            preview_assets.extend([{"image": {"url": u}} for u in a.image_url])

            preview = dict(inp, assets=preview_assets)
            print(json.dumps({"payload": preview, "cleaned_media": files}, ensure_ascii=False, indent=2))
            return

        logger.info(f"uploading {len(cleaned)} file(s) to ImgBed...")
        urls = [upload_with_retry(c) for c in cleaned] + a.image_url

    if urls:
        # Buffer API: videos and images both go in assets array
        assets = []
        for i, c in enumerate(cleaned):
            if is_video(c):
                assets.append({"video": {"url": urls[i]}})
            else:
                assets.append({"image": {"url": urls[i]}})
        # Add any pre-uploaded image URLs (assuming they're images)
        assets.extend([{"image": {"url": u}} for u in a.image_url])
        inp["assets"] = assets

    logger.info(f"creating Buffer post on {a.platform} ({a.mode})...")
    query = """mutation($input: CreatePostInput!) { createPost(input: $input) {
      ... on PostActionSuccess { post { id status dueAt text } }
      ... on MutationError { message } } }"""
    res = buffer_query(query, {"input": inp})
    out = (res.get("data") or {}).get("createPost") or {}
    if "message" in out or res.get("errors"):
        sys.exit(parse_buffer_error(out, res))

    post = out["post"]
    result = {"platform": a.platform, "post_id": post["id"], "status": post["status"],
              "due_at": post.get("dueAt"), "media_urls": urls, "timestamp": datetime.now(timezone.utc).isoformat()}
    logger.info(f"post created: {post['id']} ({post['status']})")
    print(json.dumps(result, ensure_ascii=False, indent=2))



if __name__ == "__main__":
    main()
