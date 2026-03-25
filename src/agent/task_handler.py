"""task_handler.py: cocoro-OSタスクハンドラー

cocoro-OSから受け取ったタスクを処理し、
既存のエンジン（FluxEngine, VoiceEngine等）とパイプラインを呼び出す。
タスクタイプ別のハンドラー関数を定義する。
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.agent.cocoro_client import CocoroTask, CocoroTaskResult

logger = logging.getLogger(__name__)

# ハンドラー関数の型エイリアス
TaskHandlerFunc = Callable[[CocoroTask], CocoroTaskResult]


@dataclass
class TaskDispatcher:
    """タスクタイプ別ハンドラーを管理するディスパッチャー

    各タスクタイプに対応するハンドラー関数を登録し、
    受け取ったタスクを適切なハンドラーに委譲する。
    """

    _handlers: dict[str, TaskHandlerFunc]

    def __init__(self) -> None:
        """デフォルトハンドラーを登録して初期化"""
        self._handlers = {}
        # デフォルトハンドラーを登録
        self.register("generate_avatar", handle_generate_avatar)
        self.register("generate_script", handle_generate_script)
        self.register("pipeline_run", handle_pipeline_run)
        self.register("health_check", handle_health_check)

    def register(self, task_type: str, handler: TaskHandlerFunc) -> None:
        """タスクハンドラーを登録する

        Args:
            task_type: タスクタイプ識別子
            handler: ハンドラー関数
        """
        self._handlers[task_type] = handler
        logger.debug("TaskDispatcher: ハンドラーを登録しました (task_type=%s)", task_type)

    def dispatch(self, task: CocoroTask) -> CocoroTaskResult:
        """タスクを適切なハンドラーに委譲して実行する

        Args:
            task: 実行するタスク

        Returns:
            タスク実行結果
        """
        handler = self._handlers.get(task.task_type)
        if handler is None:
            logger.warning(
                "TaskDispatcher: 未知のタスクタイプ: %s", task.task_type
            )
            return CocoroTaskResult(
                task_id=task.task_id,
                status="error",
                error_message=f"未知のタスクタイプ: {task.task_type}",
            )

        logger.info(
            "TaskDispatcher: タスクを実行します (task_id=%s, type=%s)",
            task.task_id, task.task_type,
        )
        try:
            result = handler(task)
            logger.info(
                "TaskDispatcher: タスク完了 (task_id=%s, status=%s)",
                task.task_id, result.status,
            )
            return result
        except Exception as e:
            logger.exception(
                "TaskDispatcher: タスク実行エラー (task_id=%s)", task.task_id
            )
            return CocoroTaskResult(
                task_id=task.task_id,
                status="error",
                error_message=str(e),
            )


# ===========================================================
# タスクハンドラー関数群
# ===========================================================

def handle_generate_avatar(task: CocoroTask) -> CocoroTaskResult:
    """アバター画像生成タスクを処理する

    payload:
        customer_name: 顧客名
        prompt: 生成プロンプト
        lora_path: LoRAパス (オプション)
        width: 幅 (default: 1024)
        height: 高さ (default: 1024)
        steps: 推論ステップ数 (default: 30)
    """
    from src.engines.flux_engine import FluxEngine
    from src.engines.manager import EngineManager

    payload = task.payload
    customer_name = payload.get("customer_name", f"task_{task.task_id}")
    prompt = payload.get("prompt", "professional Japanese female presenter in business suit")
    lora_path_str = payload.get("lora_path")

    output_dir = Path("outputs") / customer_name.replace(" ", "_")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "avatar.png"

    # FluxEngineで生成
    manager = EngineManager()
    manager.register("flux", FluxEngine())
    engine = manager.get("flux")
    result_path = engine.generate(
        prompt=prompt,
        output_path=output_path,
        lora_path=Path(lora_path_str) if lora_path_str else None,
        width=payload.get("width", 1024),
        height=payload.get("height", 1024),
        num_inference_steps=payload.get("steps", 30),
    )
    manager.unload_all()

    return CocoroTaskResult(
        task_id=task.task_id,
        status="success",
        output={
            "image_path": str(result_path),
            "customer_name": customer_name,
        },
    )


def handle_generate_script(task: CocoroTask) -> CocoroTaskResult:
    """LLM台本生成タスクを処理する

    payload:
        company_name: 企業名
        product_name: 製品/サービス名
        target_audience: ターゲット視聴者
        tone: トーン
        duration: 動画長さ
        provider: LLMプロバイダー (default: gemini)
    """
    from src.engines.script_engine import ScriptEngine

    payload = task.payload
    company_name = payload.get("company_name", "")
    product_name = payload.get("product_name", "")
    provider = payload.get("provider", "gemini")

    output_dir = Path("outputs") / company_name.replace(" ", "_")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "script.json"

    engine = ScriptEngine(provider=provider)
    engine.load()
    script = engine.generate(
        company_name=company_name,
        product_name=product_name,
        target_audience=payload.get("target_audience", "20代〜40代のビジネスパーソン"),
        tone=payload.get("tone", "プロフェッショナルで親しみやすい"),
        duration=payload.get("duration", "60秒"),
        output_path=output_path,
    )

    return CocoroTaskResult(
        task_id=task.task_id,
        status="success",
        output={
            "script_path": str(output_path),
            "title": script.title,
            "scene_count": len(script.scenes),
            "avatar_prompt": script.avatar_prompt,
        },
    )


def handle_pipeline_run(task: CocoroTask) -> CocoroTaskResult:
    """フルパイプライン実行タスクを処理する

    payload:
        company_name: 企業名
        product_name: 製品/サービス名
        script_path: 既存台本パス (省略時はLLM生成)
        lora_path: LoRAパス (オプション)
        output_format: 出力フォーマット (default: youtube)
    """
    from src.engines.script_engine import ScriptEngine
    from src.pipeline.orchestrator import Orchestrator
    from src.pipeline.script_parser import script_to_pipeline_config

    payload = task.payload
    company_name = payload.get("company_name", f"task_{task.task_id}")
    output_dir = Path("outputs") / company_name.replace(" ", "_")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 台本の取得
    script_path_str = payload.get("script_path")
    if script_path_str:
        script = ScriptEngine.load_from_file(Path(script_path_str))
    else:
        engine = ScriptEngine(provider=payload.get("provider", "gemini"))
        engine.load()
        script = engine.generate(
            company_name=company_name,
            product_name=payload.get("product_name", "サービス"),
            output_path=output_dir / "script.json",
        )

    # PipelineConfigに変換して実行
    pipeline_config = script_to_pipeline_config(
        script,
        output_dir=output_dir,
        lora_path=Path(payload["lora_path"]) if payload.get("lora_path") else None,
        output_format=payload.get("output_format", "youtube"),
    )

    orchestrator = Orchestrator(pipeline_config)
    final_path = orchestrator.run()

    return CocoroTaskResult(
        task_id=task.task_id,
        status="success",
        output={
            "video_path": str(final_path),
            "company_name": company_name,
        },
    )


def handle_health_check(task: CocoroTask) -> CocoroTaskResult:
    """ヘルスチェックタスク (常にsuccess)"""
    return CocoroTaskResult(
        task_id=task.task_id,
        status="success",
        output={"message": "cocoro-influencer agent is healthy"},
    )
