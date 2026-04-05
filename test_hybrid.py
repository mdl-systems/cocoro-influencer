import asyncio
import sys
import logging
import shutil
from pathlib import Path

sys.path.insert(0, r"f:\antigravity\hybrid-avatar-pipeline")
from main import Pipeline, JobSpec, SceneSpec
from config.settings import settings
import warnings

# 警告を非表示
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)

async def auto_approve(stage_name, file_path):
    print(f">>> AUTO-APPROVING {stage_name}: {file_path}")
    return "approve"

async def progress(pct, msg):
    print(f"[{pct}%] {msg}")

async def run_hybrid():
    job = JobSpec(
        job_id="hybrid_kling_expressive_001",
        avatar_path=r"C:\Users\taich\.gemini\antigravity\brain\15f72f86-09c9-4200-a708-e8e686391086\test_base_character_1775295899128.png", 
        scenes=[
            SceneSpec(
                scene_id="scene_000", 
                script_text="どうしてこんなことに気付かなかったの！？…ふふっ、でも、おかげで目が覚めたわ！完璧な動画を作ってみせる！", 
                camera_angle="upper_body", 
                duration=6.0, 
                background_prompt="Expressive avatar, highly emotional. Starts looking angry and fiercely frowning, then suddenly transitioning to a bright, wide laugh. Vivid facial expressions. Raising hands dynamically, vivid body language, highly detailed, expressive face, cinematic lighting, 8k resolution"
            ),
        ],
        output_path="output/hybrid_kling_expressive_001.mp4"
    )
    
    pipeline = Pipeline(settings)
    out_file = Path(job.output_path)
    if out_file.exists(): 
        out_file.unlink()
        
    result = await pipeline.run(job, approval_callback=auto_approve, progress_callback=progress)
    print(f">>> DONE: Success={result.success}, File={result.output_path}, Error={result.error}")

asyncio.run(run_hybrid())
