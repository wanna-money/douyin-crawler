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
        if item["media_type"] == "video":
            # 只下载封面图，不下载视频本体（节省带宽）
            cover_url = item.get("cover_url")
            if cover_url:
                cover_dest = os.path.join(self.base_dir, f"{aweme_id}_cover.jpg")
                if not os.path.exists(cover_dest):
                    try:
                        await self.client.download_file(cover_url, cover_dest)
                    except Exception:
                        pass
                if os.path.exists(cover_dest):
                    item["cover_path"] = cover_dest
        elif item["media_type"] == "image":
            for idx, url in enumerate(item.get("image_urls", [])):
                dest = os.path.join(self.base_dir, f"{aweme_id}_{idx}.jpg")
                if not os.path.exists(dest):
                    await self.client.download_file(url, dest)
                paths.append(dest)
        return paths
