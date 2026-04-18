import os
import time
import httpx
import logging
import jwt
from pathlib import Path
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)

class KlingAPIClient:
    """
    Kling AI (Kuaishou) API Client for Image-to-Video generation.
    Authenticates using JWT generated from Access Key and Secret Key.
    """

    def __init__(self, access_key: str = None, secret_key: str = None):
        self.access_key = access_key or os.getenv("KLING_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("KLING_SECRET_KEY")
        
        if not self.access_key or not self.secret_key:
            raise ValueError("KLING_ACCESS_KEY and KLING_SECRET_KEY are not set in environment or initialization.")
            
        self.base_url = "https://api.klingai.com/v1/videos/image2video"

    def _generate_token(self) -> str:
        """
        AK/SKから5分間有効なJWTトークンを生成する
        """
        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 300,  # 5分間有効
            "nbf": int(time.time()) - 5
        }
        headers = {"alg": "HS256", "typ": "JWT"}
        token = jwt.encode(payload, self.secret_key, algorithm="HS256", headers=headers)
        if isinstance(token, bytes):
            token = token.decode('utf-8')
        return token

    @property
    def headers(self):
        """常に有効なAuthorizationヘッダーを取得"""
        return {
            "Authorization": f"Bearer {self._generate_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def submit_i2v_task(
        self,
        image_url: str,
        prompt: str,
        duration: int = 5,
        aspect_ratio: str = "9:16",
    ) -> str:
        """
        Kling APIにImage-to-Videoジョブを送信し、Task IDを返す

        Args:
            image_url: ローカル画像パスまたはURL
            prompt: 動画生成プロンプト
            duration: 動画長（秒）: 5 or 10
            aspect_ratio: アスペクト比 "9:16"(縦)/ "16:9"(横)/ "1:1"(正方形)
                          ショート動画・全身ポーズは "9:16" を指定すること。
        """
        logger.info(f"Submitting Kling I2V task: image={image_url} ratio={aspect_ratio} duration={duration}s")
        import base64 as _b64, os as _os
        if _os.path.exists(image_url):
            with open(image_url, "rb") as _imgf:
                image_data = _b64.b64encode(_imgf.read()).decode()
        else:
            image_data = image_url
        
        payload = {
            "model_name": "kling-v1-6",   # v1-6 は縦長動画・高品質対応
            "image": image_data,
            "prompt": prompt,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,  # 縦長コンテンツは必ず "9:16" を指定
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(self.base_url, headers=self.headers, json=payload)
            logger.info(f"Kling API response: {resp.status_code}")
            if resp.status_code >= 400:
                logger.error(f"Kling API error: {resp.text}")
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("data", {}).get("task_id")
            if not task_id:
                raise RuntimeError(f"Kling API failed to return task_id: {data}")
            return task_id

    async def wait_for_task(self, task_id: str, poll_interval_sec: int = 10, timeout_sec: int = 900) -> str:
        """
        Task ID の完了をポーリングし、完成した動画のURLを返す
        """
        url = f"https://api.klingai.com/v1/videos/image2video/{task_id}"
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while time.time() - start_time < timeout_sec:
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                
                # Check top-level code
                if data.get("code") != 0:
                    raise RuntimeError(f"Kling API task query failed: {data}")
                    
                task_data = data.get("data", {})
                status = task_data.get("task_status", "").lower()
                
                if status == "succeed":
                    # video_url is usually inside data.task_result.videos[0].url
                    videos = task_data.get("task_result", {}).get("videos", [])
                    if videos and isinstance(videos, list):
                        video_url = videos[0].get("url")
                        if video_url:
                            logger.info(f"Kling I2V task {task_id} completed: {video_url}")
                            return video_url
                    raise RuntimeError(f"Kling I2V task succeeded but no video url found: {data}")
                    
                elif status in ["failed", "error"]:
                    raise RuntimeError(f"Kling I2V task {task_id} failed: {data}")
                
                logger.info(f"Kling I2V task {task_id} is running ({status})... waiting {poll_interval_sec}s.")
                await asyncio.sleep(poll_interval_sec)
                
            raise TimeoutError(f"Kling I2V task {task_id} timed out after {timeout_sec} seconds.")
