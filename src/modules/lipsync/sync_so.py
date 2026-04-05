import os
import time
import httpx
import logging
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)

class LipSyncAPIClient:
    """
    LipSync API Client (using official syncsdk for API v2).
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("LIPSYNC_API_KEY")
        if not self.api_key:
            raise ValueError("LIPSYNC_API_KEY is not set in environment or initialization.")
            
        try:
            from sync import AsyncSync
            self.client = AsyncSync(api_key=self.api_key)
        except ImportError:
            raise ImportError("Please install syncsdk: pip install syncsdk")

    async def submit_lipsync_task(self, video_url: str, audio_url: str) -> str:
        """
        リップシンクジョブを送信し、Task ID (video id) を返す
        """
        logger.info(f"Submitting LipSync task for video: {video_url} with audio: {audio_url}")
        
        from sync.common import Video, Audio
        response = await self.client.generations.create(
            model="lipsync-2",
            input=[
                Video(url=video_url),
                Audio(url=audio_url)
            ]
        )
        task_id = response.id
        if not task_id:
            raise RuntimeError(f"LipSync API failed to return task_id: {response}")
        return task_id

    async def wait_for_task(self, task_id: str, poll_interval_sec: int = 10, timeout_sec: int = 900) -> str:
        """
        Task ID の完了をポーリングし、完成したリップシンク動画のURLを返す
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout_sec:
            response = await self.client.generations.get(task_id)
            status = getattr(response, "status", getattr(response, "state", "UNKNOWN"))
            status = str(status).upper()
            
            if status == "COMPLETED" or status == "SUCCESS":
                video_url = getattr(response, "videoUrl", getattr(response, "outputUrl", getattr(response, "url", None)))
                if hasattr(response, "output") and getattr(response.output, "url", None):
                    video_url = response.output.url
                
                logger.info(f"LipSync task {task_id} completed: {video_url}")
                return video_url
            elif status in ["FAILED", "CANCELED", "ERROR"]:
                raise RuntimeError(f"LipSync task {task_id} failed: {response}")
            
            logger.info(f"LipSync task {task_id} is running ({status})... waiting.")
            await asyncio.sleep(poll_interval_sec)
            
        raise TimeoutError(f"LipSync task {task_id} timed out after {timeout_sec} seconds.")
