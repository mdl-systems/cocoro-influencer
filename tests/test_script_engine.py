"""ScriptEngineのユニットテスト

LLM APIは実際に呼び出さずモックして、
ScriptEngineのロジック・パースをテストする。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.engines.base import BaseEngine
from src.engines.script_engine import Script, ScriptEngine, ScriptScene
from src.pipeline.script_parser import validate_script_json


# ===========================================================
# ScriptSceneとScriptのテスト
# ===========================================================

class TestScriptDataclasses:
    """ScriptSceneとScriptデータクラスのテスト"""

    def test_script_scene_default_fields(self) -> None:
        """ScriptSceneのデフォルトフィールド確認"""
        scene = ScriptScene(
            scene_id=1,
            scene_type="talking_head",
            text="こんにちは、私はcocoro AIです。",
        )
        assert scene.scene_id == 1
        assert scene.scene_type == "talking_head"
        assert scene.caption == ""
        assert scene.cinematic_prompt == ""

    def test_script_default_fields(self) -> None:
        """Scriptのデフォルトフィールド確認"""
        script = Script(
            title="テスト台本",
            scenes=[],
            avatar_prompt="professional Japanese female",
        )
        assert script.company_name == ""
        assert script.product_name == ""
        assert script.total_duration_estimate == "60s"


# ===========================================================
# ScriptEngineのインターフェーステスト
# ===========================================================

class TestScriptEngineInterface:
    """ScriptEngineのインターフェーステスト"""

    def test_script_engine_is_base_engine(self) -> None:
        """ScriptEngineがBaseEngineのサブクラスである"""
        engine = ScriptEngine()
        assert isinstance(engine, BaseEngine)

    def test_script_engine_default_provider(self) -> None:
        """デフォルトプロバイダーはgemini"""
        engine = ScriptEngine()
        assert engine._provider == "gemini"
        assert "gemini" in engine._model

    def test_script_engine_anthropic_provider(self) -> None:
        """anthropicプロバイダーを指定できる"""
        engine = ScriptEngine(provider="anthropic")
        assert engine._provider == "anthropic"
        assert "claude" in engine._model

    def test_script_engine_custom_model(self) -> None:
        """カスタムモデルを指定できる"""
        engine = ScriptEngine(provider="gemini", model="gemini-2.0-flash-exp")
        assert engine._model == "gemini-2.0-flash-exp"

    def test_script_engine_load_unload(self) -> None:
        """load/unloadが正しく動作する"""
        engine = ScriptEngine()
        assert not engine.is_loaded
        engine.load()
        assert engine.is_loaded
        engine.unload()
        assert not engine.is_loaded

    def test_script_engine_generate_without_load_raises(self) -> None:
        """ロード前のgenerate呼び出しでRuntimeError"""
        engine = ScriptEngine()
        with pytest.raises(RuntimeError, match="ロードされていません"):
            engine.generate(
                company_name="テスト株式会社",
                product_name="テスト製品",
            )


# ===========================================================
# ScriptEngineのJSON パーステスト
# ===========================================================

class TestScriptParsing:
    """台本JSONパース処理のテスト"""

    def _make_valid_json(self) -> str:
        """有効な台本JSONを返す"""
        return json.dumps({
            "title": "AIソリューション紹介動画",
            "scenes": [
                {
                    "scene_id": 1,
                    "scene_type": "talking_head",
                    "text": "こんにちは！AIソリューション株式会社の山田花子です。",
                    "caption": "山田花子 / AIソリューション",
                    "cinematic_prompt": "",
                },
                {
                    "scene_id": 2,
                    "scene_type": "cinematic",
                    "text": "最先端のAI技術で御社の業務を革新します。",
                    "caption": "AI技術で業務革新",
                    "cinematic_prompt": "modern office with AI holographic displays, futuristic technology",
                },
            ],
            "avatar_prompt": "professional Japanese female presenter in business suit, smile",
            "total_duration_estimate": "30s",
        }, ensure_ascii=False)

    def test_parse_valid_json(self) -> None:
        """有効なJSONをパースできる"""
        engine = ScriptEngine()
        engine.load()
        script = engine._parse_script_json(
            self._make_valid_json(),
            company_name="AIソリューション株式会社",
            product_name="AIプラットフォーム",
        )
        assert script.title == "AIソリューション紹介動画"
        assert len(script.scenes) == 2
        assert script.scenes[0].scene_type == "talking_head"
        assert script.scenes[1].scene_type == "cinematic"
        assert script.company_name == "AIソリューション株式会社"
        assert script.product_name == "AIプラットフォーム"

    def test_parse_json_with_markdown_fence(self) -> None:
        """```json ... ``` で囲まれたJSONをパースできる"""
        engine = ScriptEngine()
        engine.load()
        raw = "```json\n" + self._make_valid_json() + "\n```"
        script = engine._parse_script_json(raw)
        assert len(script.scenes) == 2

    def test_parse_invalid_json_raises(self) -> None:
        """不正なJSONでRuntimeError"""
        engine = ScriptEngine()
        engine.load()
        with pytest.raises(RuntimeError, match="パースに失敗"):
            engine._parse_script_json("これはJSONではありません")


# ===========================================================
# ScriptEngineのファイル保存・読み込みテスト
# ===========================================================

class TestScriptFileIO:
    """台本ファイル保存・読み込みのテスト"""

    def _make_test_script(self) -> Script:
        """テスト用Scriptオブジェクトを作成する"""
        return Script(
            title="テスト台本",
            scenes=[
                ScriptScene(
                    scene_id=1,
                    scene_type="talking_head",
                    text="テストテキスト",
                    caption="テスト",
                    cinematic_prompt="",
                )
            ],
            avatar_prompt="test avatar prompt",
            company_name="テスト株式会社",
            product_name="テスト製品",
        )

    def test_generate_saves_file(self, tmp_path: Path) -> None:
        """generateのoutput_pathにJSONが保存される"""
        engine = ScriptEngine(provider="gemini")
        engine.load()

        # APIをモック
        mock_script = self._make_test_script()
        with patch.object(engine, "_parse_script_json", return_value=mock_script):
            with patch.object(engine, "_call_gemini", return_value="{}"):
                output_path = tmp_path / "script.json"
                engine.generate(
                    company_name="テスト株式会社",
                    product_name="テスト製品",
                    output_path=output_path,
                )

        assert output_path.exists()
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert "scenes" in data
        assert "avatar_prompt" in data

    def test_load_from_file(self, tmp_path: Path) -> None:
        """ファイルから台本を読み込める"""
        script_data = {
            "title": "読み込みテスト",
            "scenes": [
                {
                    "scene_id": 1,
                    "scene_type": "talking_head",
                    "text": "テスト",
                    "caption": "TC",
                    "cinematic_prompt": "",
                }
            ],
            "avatar_prompt": "test",
            "company_name": "ABC",
            "product_name": "XYZ",
            "total_duration_estimate": "30s",
            "provider": "gemini",
            "model": "gemini-2.0-flash",
        }
        script_path = tmp_path / "script.json"
        script_path.write_text(json.dumps(script_data, ensure_ascii=False), encoding="utf-8")

        script = ScriptEngine.load_from_file(script_path)
        assert script.title == "読み込みテスト"
        assert len(script.scenes) == 1
        assert script.scenes[0].text == "テスト"
        assert script.company_name == "ABC"

    def test_load_from_file_not_found(self, tmp_path: Path) -> None:
        """存在しないファイルでFileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="台本ファイルが見つかりません"):
            ScriptEngine.load_from_file(tmp_path / "nonexistent.json")


# ===========================================================
# ScriptParserのバリデーションテスト
# ===========================================================

class TestScriptParserValidation:
    """台本JSONバリデーションのテスト"""

    def test_valid_json_no_errors(self) -> None:
        """有効なJSONにエラーなし"""
        data = {
            "scenes": [
                {
                    "scene_id": 1,
                    "scene_type": "talking_head",
                    "text": "こんにちは",
                    "caption": "あいさつ",
                }
            ],
            "avatar_prompt": "test",
        }
        errors = validate_script_json(data)
        assert errors == []

    def test_missing_scenes(self) -> None:
        """scenesなしでエラー"""
        errors = validate_script_json({"avatar_prompt": "test"})
        assert any("scenes" in e for e in errors)

    def test_empty_scenes(self) -> None:
        """空のscenesでエラー"""
        errors = validate_script_json({"scenes": [], "avatar_prompt": "test"})
        assert any("scenes" in e and "空" in e for e in errors)

    def test_missing_text_in_scene(self) -> None:
        """シーンにtextなしでエラー"""
        data = {
            "scenes": [{"scene_id": 1, "scene_type": "talking_head"}],
            "avatar_prompt": "test",
        }
        errors = validate_script_json(data)
        assert any("text" in e for e in errors)

    def test_invalid_scene_type(self) -> None:
        """不正なscene_typeでエラー"""
        data = {
            "scenes": [{"scene_id": 1, "scene_type": "invalid", "text": "test"}],
            "avatar_prompt": "test",
        }
        errors = validate_script_json(data)
        assert any("scene_type" in e for e in errors)

    def test_cinematic_missing_prompt(self) -> None:
        """cinematicシーンにcinematic_promptなしでエラー"""
        data = {
            "scenes": [{"scene_id": 1, "scene_type": "cinematic", "text": "test"}],
            "avatar_prompt": "test",
        }
        errors = validate_script_json(data)
        assert any("cinematic_prompt" in e for e in errors)

    def test_missing_avatar_prompt(self) -> None:
        """avatar_promptなしでエラー"""
        data = {
            "scenes": [{"scene_id": 1, "scene_type": "talking_head", "text": "test"}],
        }
        errors = validate_script_json(data)
        assert any("avatar_prompt" in e for e in errors)
