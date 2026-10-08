import base64
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("grok_media", HERE / "grok_media.py")
grok_media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grok_media)


class GrokMediaTest(unittest.TestCase):
    def test_relative_video_url_and_auth_header(self):
        def fake_curl(args, timeout):
            Path(args[args.index("-o") + 1]).write_bytes(b"video")
            return 200, ""

        with tempfile.TemporaryDirectory() as tmp, patch.object(grok_media, "_curl", side_effect=fake_curl) as curl:
            path, url = grok_media.save_video(
                {"video": {"url": "/v1/videos/id/content"}}, tmp, "id", "secret", "https://relay.test/v1"
            )
        self.assertEqual(url, "https://relay.test/v1/videos/id/content")
        args = curl.call_args.args[0]
        self.assertIn("Authorization: Bearer secret", args)
        self.assertTrue(args[args.index("-o") + 1].endswith(".mp4"))

    def test_save_base64_image(self):
        raw = b"jpeg-bytes"
        with tempfile.TemporaryDirectory() as tmp:
            paths = grok_media.save_image_items(
                [{"b64_json": base64.b64encode(raw).decode()}], tmp, "image"
            )
            self.assertEqual(Path(paths[0]).read_bytes(), raw)

    def test_cost_ticks_conversion(self):
        ticks = 12_100_000_000
        self.assertEqual(ticks / 10_000_000_000, 1.21)


if __name__ == "__main__":
    unittest.main()
