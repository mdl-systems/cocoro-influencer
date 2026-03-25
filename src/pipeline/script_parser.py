"""script_parser.py: 台本のパース・変換ユーティリティ

台本JSON/YAMLとパイプライン設定の相互変換を行うユーティリティ。
OrchestratorのPipelineConfigとScriptEngineのScriptオブジェクトを橋渡しする。
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def script_to_pipeline_config(
    script,  # ScriptEngine.Script
    output_dir: Path,
    lora_path: Path | None = None,
    bgm_path: Path | None = None,
    output_format: str = "youtube",
    voicevox_url: str = "http://localhost:50021",
    speaker_id: int = 3,
) -> dict:
    """ScriptオブジェクトをOrchestrator用設定辞書に変換する

    Args:
        script: ScriptEngine.Script オブジェクト
        output_dir: 出力ディレクトリ
        lora_path: LoRAファイルパス
        bgm_path: BGMファイルパス
        output_format: 出力フォーマット
        voicevox_url: VOICEVOX ENGINE URL
        speaker_id: VOICEVOX 話者ID

    Returns:
        PipelineConfigの初期化引数辞書
    """
    from src.pipeline.orchestrator import PipelineConfig
    from src.pipeline.orchestrator import ScriptScene as OrchestratorScene

    # ScriptEngineのSceneをOrchestratorのSceneに変換
    pipeline_scenes = [
        OrchestratorScene(
            text=scene.text,
            scene_type=scene.scene_type,
            cinematic_prompt=scene.cinematic_prompt,
            caption=scene.caption,
        )
        for scene in script.scenes
    ]

    return PipelineConfig(
        scenes=pipeline_scenes,
        avatar_prompt=script.avatar_prompt,
        output_dir=output_dir,
        lora_path=lora_path,
        bgm_path=bgm_path,
        output_format=output_format,
        voicevox_url=voicevox_url,
        speaker_id=speaker_id,
    )


def load_script_file(script_path: Path) -> "Script":  # type: ignore[name-defined]
    """台本JSONファイルを読み込む

    Args:
        script_path: .json ファイルパス

    Returns:
        ScriptEngine.Script オブジェクト
    """
    from src.engines.script_engine import ScriptEngine
    return ScriptEngine.load_from_file(script_path)


def validate_script_json(data: dict) -> list[str]:
    """台本JSONのバリデーション

    Args:
        data: 検証するJSON辞書

    Returns:
        エラーメッセージのリスト（空の場合は有効）
    """
    errors: list[str] = []

    if "scenes" not in data:
        errors.append("'scenes' フィールドが必要です")
    elif not isinstance(data["scenes"], list) or len(data["scenes"]) == 0:
        errors.append("'scenes' は空でないリストである必要があります")
    else:
        for i, scene in enumerate(data["scenes"]):
            if "text" not in scene or not scene["text"]:
                errors.append(f"シーン {i + 1}: 'text' フィールドが必要です")
            scene_type = scene.get("scene_type", "")
            if scene_type not in ("talking_head", "cinematic"):
                errors.append(f"シーン {i + 1}: 'scene_type' は 'talking_head' または 'cinematic' である必要があります")
            if scene_type == "cinematic" and not scene.get("cinematic_prompt"):
                errors.append(f"シーン {i + 1}: cinematic シーンには 'cinematic_prompt' が必要です")

    if "avatar_prompt" not in data:
        errors.append("'avatar_prompt' フィールドが必要です")

    return errors
