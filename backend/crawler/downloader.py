import os
from backend.crawler.client import DouyinClient


class Downloader:
    def __init__(self, client: DouyinClient, base_dir: str = "downloads"):
        self.client = client
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    async def download(self, item: dict) -> list[str]:
        aweme_id = item["aweme_id"]
        paths = []
        if item["media_type"] == "video" and item.get("video_url"):
            dest = os.path.join(self.base_dir, f"{aweme_id}.mp4")
            if not os.path.exists(dest):
                await self.client.download_file(item["video_url"], dest)
            paths.append(dest)
        elif item["media_type"] == "image":
            for idx, url in enumerate(item.get("image_urls", [])):
                dest = os.path.join(self.base_dir, f"{aweme_id}_{idx}.jpg")
                if not os.path.exists(dest):
                    await self.client.download_file(url, dest)
                paths.append(dest)
        return paths
