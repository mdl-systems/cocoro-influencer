import asyncio
import os
import sys

sys.path.insert(0, r"f:\antigravity\hybrid-avatar-pipeline")
from config.settings import load_settings
from api.clients.lipsync import LipSyncAPIClient

async def test_synclabs():
    # .env \u304b\u3089 API Key \u3092\u8aad\u307f\u8fbc\u3080
    settings = load_settings()
    k = os.environ.get("LIPSYNC_API_KEY")
    if not k:
        print("LIPSYNC_API_KEY not found!")
        return

    client = LipSyncAPIClient(k)
    
    # Dummy short video (catbox URL) and dummy audio (catbox URL)
    # \u4ee5\u524d\u306ekling\u52d5\u753b\u306eurl:
    video_url = "https://files.catbox.moe/kling_dummy.mp4" # I don't have the explicit catbox dummy but I'll use a random dummy here just to test auth
    audio_url = "https://files.catbox.moe/audio_dummy.wav"
    
    try:
        print("Authorizing with SyncLabs...")
        import httpx
        async with httpx.AsyncClient() as c:
            resp = await c.get("https://api.synclabs.so/video", headers=client.headers)
            print("Auth check status:", resp.status_code)
            if resp.status_code == 200 or resp.status_code == 204:
                print("Auth SUCCESS! SyncLabs API is active.")
            else:
                print("Auth response:", resp.text)
    except Exception as e:
        print("Error details:", e)

asyncio.run(test_synclabs())
