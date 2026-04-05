"""
FastAPI ゲートウェイサーバー

gpurental.jpポータルからバッチ処理をキックするインターフェース。
ジョブの作成・進捗確認・結果取得を提供。
"""

import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger("api.server")


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_FOR_APPROVAL = "waiting_for_approval"


class JobStore:
    """インメモリジョブストア"""
    def __init__(self):
        self._jobs: Dict[str, dict] = {}

    def create(self, job_data: dict) -> str:
        job_id = str(uuid.uuid4())[:8]
        self._jobs[job_id] = {
            "id": job_id,
            "status": JobStatus.QUEUED,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "progress": 0,
            "result": None,
            "error": None,
            "approval_stage": None,
            "preview_url": None,
            "approval_action": None,
            **job_data,
        }
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs):
        if job_id in self._jobs:
            self._jobs[job_id].update(kwargs, updated_at=datetime.utcnow().isoformat())

    def list_all(self) -> List[dict]:
        return list(self._jobs.values())


# ──────────────────────────────────────────────────────

def create_app():
    """FastAPIアプリケーション生成"""
    try:
        from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import RedirectResponse
        from pydantic import BaseModel, Field
        import shutil
    except ImportError:
        logger.error("FastAPIが未インストールです。pip install fastapi uvicorn")
        raise

    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config.settings import load_settings
    from main import Pipeline, JobSpec, SceneSpec

    settings = load_settings()
    store = JobStore()
    pipeline = Pipeline(settings)

    app = FastAPI(
        title="Avatar Video Pipeline API",
        description="3Dアバターから実写風AI動画を自動生成するAPI",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://gpurental.jp", "http://localhost:*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = Path(__file__).parent / "static"
    output_dir = Path(__file__).parent.parent / "output"
    tmp_dir = Path(__file__).parent.parent / "tmp"
    static_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    tmp_dir.mkdir(exist_ok=True)
    
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")
    app.mount("/tmp", StaticFiles(directory=str(tmp_dir)), name="tmp")

    # Pydanticモデル
    class SceneInput(BaseModel):
        script_text: str
        pose: str = "neutral"
        expression: str = "neutral"
        duration: float = 5.0
        camera_angle: str = "upper_body"
        appearance_prompt: Optional[str] = None
        background_prompt: Optional[str] = None

    class JobCreateRequest(BaseModel):
        avatar_path: str
        scenes: List[SceneInput]
        bgm_path: Optional[str] = None
        bg_image_path: Optional[str] = None
        resolution: tuple = (1280, 720)

    class JobResponse(BaseModel):
        id: str
        status: str
        progress: int
        created_at: str
        result: Optional[str] = None
        error: Optional[str] = None
        approval_stage: Optional[str] = None
        preview_url: Optional[str] = None
        status_message: Optional[str] = None
        
    class ApprovalRequest(BaseModel):
        action: str  # "approve", "retry", "reject"

    class AnalyzeRequest(BaseModel):
        url: str
        
    class AnalyzeResponse(BaseModel):
        title: str
        transcript: str
        scenes: List[SceneInput]

    # バックグラウンドタスク
    async def _run_pipeline(job_id: str, job_spec: JobSpec):
        store.update(job_id, status=JobStatus.RUNNING, progress=1)
        
        async def approval_callback(stage_name: str, preview_path: str) -> str:
            try:
                preview_path_obj = Path(preview_path).resolve()
                proj_root = Path(__file__).parent.parent.resolve()
                rel = preview_path_obj.relative_to(proj_root)
                preview_url = f"/{rel.as_posix()}?t={datetime.utcnow().timestamp()}"
            except Exception as e:
                logger.error(f"URL generation failed for {preview_path}: {e}")
                preview_url = str(preview_path)
                
            store.update(job_id, status=JobStatus.WAITING_FOR_APPROVAL, approval_stage=stage_name, preview_url=preview_url, approval_action=None)
            
            # Wait for user action
            while True:
                job_data = store.get(job_id)
                if not job_data:
                    return "reject"
                action = job_data.get("approval_action")
                if action:
                    store.update(job_id, status=JobStatus.RUNNING, approval_stage=None, preview_url=None, approval_action=None)
                    return action
                await asyncio.sleep(1)

        async def progress_callback(progress: int, message: str):
            store.update(job_id, progress=progress, status_message=message)

        try:
            result = await pipeline.run(job_spec, approval_callback=approval_callback, progress_callback=progress_callback)
            if result.success:
                store.update(job_id, status=JobStatus.COMPLETED, progress=100, result=result.output_path)
            else:
                store.update(job_id, status=JobStatus.FAILED, error=result.error)
        except Exception as e:
            store.update(job_id, status=JobStatus.FAILED, error=str(e))

    # ── エンドポイント ─────────────

    @app.get("/")
    async def root():
        return RedirectResponse(url="/static/index.html")

    @app.get("/api/info")
    async def info():
        return {"service": "Avatar Video Pipeline", "version": "0.1.0", "status": "running"}

    @app.get("/health")
    async def health():
        return {"status": "ok", "gpu_vram": settings.gpu.vram_limit}

    @app.post("/v1/upload")
    async def upload_file(file: UploadFile = File(...)):
        uploads_dir = tmp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in [".jpg", ".jpeg", ".png", ".webp", ".vrm"]:
            raise HTTPException(status_code=400, detail="サポートされていない形式です")
        
        safe_filename = f"{uuid.uuid4().hex[:8]}{file_ext}"
        file_path = uploads_dir / safe_filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {"filename": file.filename, "path": f"tmp/uploads/{safe_filename}", "url": f"/tmp/uploads/{safe_filename}"}

    async def _process_whisper_and_build_scenes(audio_file_path: str, fallback_title: str, fallback_duration: float) -> AnalyzeResponse:
        import math
        segments_raw = []
        try:
            import whisper as whisper_mod
            model = whisper_mod.load_model("tiny")  # tiny fits all VRAM
            result = model.transcribe(audio_file_path, language="ja", fp16=False)
            segments_raw = result.get("segments", [])
        except Exception as e:
            import traceback
            with open(tmp_dir / "analyze_whisper_err.txt", "w") as f:
                f.write(traceback.format_exc())
            logger.warning(f"Whisper failed: {e} - falling back to duration-based segmentation")

        scenes = []
        if segments_raw:
            chunk_text = []
            chunk_start = 0.0
            CHUNK_SEC = 8.0
            for seg in segments_raw:
                chunk_text.append(seg['text'].strip())
                if seg['end'] - chunk_start >= CHUNK_SEC or seg is segments_raw[-1]:
                    combined = ' '.join(chunk_text)
                    chunk_dur = min(CHUNK_SEC, seg['end'] - chunk_start)
                    scenes.append(SceneInput(
                        script_text=combined,
                        pose="neutral" if len(scenes) % 2 == 0 else "walk",
                        expression="smile",
                        duration=round(chunk_dur, 1),
                        camera_angle="full_body" if len(scenes) % 3 == 0 else "upper_body",
                        background_prompt="cinematic environment, dynamic lighting"
                    ))
                    chunk_text = []
                    chunk_start = seg['end']
                    if len(scenes) >= 10:
                        break
        else:
            num_scenes = max(1, min(math.ceil(fallback_duration / 8), 10))
            for i in range(num_scenes):
                chunk_dur = min(8.0, fallback_duration - i * 8)
                scenes.append(SceneInput(
                    script_text=f"《{fallback_title}》 シーン{i+1}: ここに台本を入力してください",
                    pose="neutral" if i % 2 == 0 else "walk",
                    expression="smile",
                    duration=round(chunk_dur, 1),
                    camera_angle="full_body" if i % 3 == 0 else "upper_body",
                    background_prompt="cinematic, urban environment, dynamic lighting"
                ))

        full_transcript = " ".join([seg['text'] for seg in segments_raw]).strip() if segments_raw else "（音声やセリフが正確に検出されませんでした）"
        return AnalyzeResponse(title=fallback_title, transcript=full_transcript, scenes=scenes)

    @app.post("/v1/analyze", response_model=AnalyzeResponse)
    async def analyze_video(req: AnalyzeRequest):
        import yt_dlp, tempfile, os, math, sys
        
        class SafeStream:
            def __init__(self, stream):
                self.stream = stream
            def write(self, data):
                try: return self.stream.write(data)
                except OSError: pass
            def flush(self):
                try: self.stream.flush()
                except OSError: pass
            def __getattr__(self, name):
                return getattr(self.stream, name)
                
        if sys.stdout: sys.stdout = SafeStream(sys.stdout)
        if sys.stderr: sys.stderr = SafeStream(sys.stderr)
        
        analyze_dir = tmp_dir / "analyze"
        analyze_dir.mkdir(parents=True, exist_ok=True)
        audio_path = str(analyze_dir / "audio.%(ext)s")
        
        class YTDLogger:
            def debug(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): pass
            
        dummy_logger = YTDLogger()
        
        title = "Unknown Video"
        duration = 32
        actual_audio_file = None
        
        ydl_opts_meta = {'quiet': True, 'skip_download': True, 'logger': dummy_logger}
        try:
            with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
                info = ydl.extract_info(req.url, download=False)
                title = info.get('title', 'Unknown Video')
                duration = info.get('duration', 32)
        except Exception as e:
            logger.warning(f"Metadata fetch failed: {e}")

        ydl_opts_audio = {
            'quiet': True,
            'format': 'bestaudio/best',
            'outtmpl': audio_path,
            'logger': dummy_logger,
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '64'}],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                ydl.download([req.url])
            for f in analyze_dir.iterdir():
                if f.suffix == '.mp3':
                    actual_audio_file = str(f)
                    break
        except Exception as e:
            logger.warning(f"Audio download failed: {e}")

        if not actual_audio_file:
            raise HTTPException(status_code=400, detail="動画のダウンロードに失敗しました。ボット対策等でブロックされた可能性があります。別のURLを試すか、「動画ファイルを直接アップロード」機能をご利用ください。")

        resp = await _process_whisper_and_build_scenes(actual_audio_file, title, duration)
        
        try:
            if actual_audio_file and os.path.exists(actual_audio_file):
                os.remove(actual_audio_file)
        except Exception:
            pass
            
        return resp

    @app.post("/v1/analyze/file", response_model=AnalyzeResponse)
    async def analyze_uploaded_file(file: UploadFile = File(...)):
        import os
        analyze_dir = tmp_dir / "analyze_upload"
        analyze_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = analyze_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        title = file.filename
        resp = await _process_whisper_and_build_scenes(str(file_path), title, 32.0)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
            
        return resp

    @app.post("/v1/jobs", response_model=JobResponse)
    async def create_job(req: JobCreateRequest, bg: BackgroundTasks):
        scenes = []
        for i, s in enumerate(req.scenes):
            kwargs = {
                "scene_id": f"s_{i:03d}",
                "script_text": s.script_text,
                "pose": s.pose,
                "expression": s.expression,
                "duration": s.duration,
                "camera_angle": s.camera_angle,
            }
            if s.appearance_prompt:
                kwargs["appearance_prompt"] = s.appearance_prompt
            if s.background_prompt:
                kwargs["background_prompt"] = s.background_prompt
                
            scenes.append(SceneSpec(**kwargs))

        job_spec = JobSpec(avatar_path=req.avatar_path, scenes=scenes)
        job_id = store.create({"avatar": req.avatar_path, "scene_count": len(scenes)})
        bg.add_task(_run_pipeline, job_id, job_spec)
        return store.get(job_id)

    @app.get("/v1/jobs/{job_id}", response_model=JobResponse)
    async def get_job(job_id: str):
        job = store.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return job

    @app.get("/v1/jobs")
    async def list_jobs():
        return store.list_all()

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        job = store.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        store.update(job_id, status=JobStatus.CANCELLED)
        return {"id": job_id, "status": "cancelled"}

    @app.post("/v1/jobs/{job_id}/approve")
    async def approve_job(job_id: str, req: ApprovalRequest):
        job = store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] != JobStatus.WAITING_FOR_APPROVAL:
            raise HTTPException(status_code=400, detail="Job is not waiting for approval")
            
        store.update(job_id, approval_action=req.action)
        return {"status": "ok", "action": req.action}

    @app.post("/v1/upload")
    async def upload_file(file: UploadFile = File(...)):
        try:
            upload_dir = tmp_dir / "uploads"
            upload_dir.mkdir(exist_ok=True)
            file_path = upload_dir / file.filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            # URL should map to /tmp/uploads/... since tmp is mounted at /tmp
            return {"success": True, "path": str(file_path), "url": f"/tmp/uploads/{file.filename}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


if __name__ == "__main__":
    import uvicorn
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config.settings import load_settings
    s = load_settings()
    app = create_app()
    uvicorn.run(app, host=s.api.host, port=s.api.port)
