"""エンジンのユニットテスト

GPUがない環境でもテストできるように設計。
- BaseEngine / EngineManager: モックエンジンでテスト
- FluxEngine: インターフェース確認のみ (実際のモデルロードはスキップ)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.engines.base import BaseEngine
from src.engines.flux_engine import FluxEngine
from src.engines.manager import EngineManager


# ===== テスト用モックエンジン =====


class MockEngine(BaseEngine):
    """テスト用のモックエンジン"""

    def __init__(self) -> None:
        super().__init__()
        self.load_count: int = 0
        self.unload_count: int = 0
        self.generate_count: int = 0

    def load(self) -> None:
        """モックロード"""
        self._is_loaded = True
        self.load_count += 1

    def unload(self) -> None:
        """モックアンロード"""
        self.unload_count += 1
        super().unload()

    def generate(self, **kwargs: object) -> Path:
        """モック生成"""
        self.generate_count += 1
        return Path("/tmp/mock_output.png")


class AnotherMockEngine(BaseEngine):
    """2つ目のテスト用モックエンジン"""

    def __init__(self) -> None:
        super().__init__()
        self.load_count: int = 0
        self.unload_count: int = 0

    def load(self) -> None:
        self._is_loaded = True
        self.load_count += 1

    def unload(self) -> None:
        self.unload_count += 1
        super().unload()

    def generate(self, **kwargs: object) -> Path:
        return Path("/tmp/mock_output_2.png")


# ===== フィクスチャ =====


@pytest.fixture(autouse=True)
def _reset_engine_manager() -> None:
    """各テスト前にEngineManagerのシングルトンをリセット"""
    EngineManager.reset()


# ===== BaseEngine テスト =====


class TestBaseEngine:
    """BaseEngineの抽象クラステスト"""

    def test_base_engine_is_abstract(self) -> None:
        """BaseEngineは直接インスタンス化できない"""
        with pytest.raises(TypeError):
            BaseEngine()  # type: ignore[abstract]

    def test_mock_engine_can_be_instantiated(self) -> None:
        """サブクラスはインスタンス化できる"""
        engine = MockEngine()
        assert not engine.is_loaded

    def test_mock_engine_load_unload(self) -> None:
        """load/unloadのライフサイクルが正常に動作する"""
        engine = MockEngine()

        assert not engine.is_loaded
        engine.load()
        assert engine.is_loaded
        engine.unload()
        assert not engine.is_loaded

    def test_mock_engine_generate(self) -> None:
        """generateが正常にPathを返す"""
        engine = MockEngine()
        engine.load()
        result = engine.generate(prompt="test")
        assert isinstance(result, Path)
        assert engine.generate_count == 1


# ===== EngineManager テスト =====


class TestEngineManager:
    """EngineManagerのテスト"""

    def test_engine_manager_singleton(self) -> None:
        """EngineManagerはシングルトンである"""
        manager1 = EngineManager()
        manager2 = EngineManager()
        assert manager1 is manager2

    def test_engine_manager_register_and_get(self) -> None:
        """エンジンの登録と取得が正常に動作する"""
        manager = EngineManager()
        engine = MockEngine()

        manager.register("mock", engine)
        retrieved = manager.get("mock")

        assert retrieved is engine
        assert engine.is_loaded
        assert engine.load_count == 1

    def test_engine_manager_get_unknown_raises(self) -> None:
        """未登録のエンジン名でKeyErrorが発生する"""
        manager = EngineManager()
        with pytest.raises(KeyError, match="未登録のエンジン"):
            manager.get("unknown")

    def test_engine_manager_unloads_previous(self) -> None:
        """別エンジンget時に前のエンジンがunloadされる"""
        manager = EngineManager()
        engine_a = MockEngine()
        engine_b = AnotherMockEngine()

        manager.register("a", engine_a)
        manager.register("b", engine_b)

        # エンジンAをロード
        manager.get("a")
        assert engine_a.is_loaded
        assert manager.active_engine_name == "a"

        # エンジンBに切替 → Aがアンロードされる
        manager.get("b")
        assert not engine_a.is_loaded
        assert engine_b.is_loaded
        assert engine_a.unload_count == 1
        assert manager.active_engine_name == "b"

    def test_engine_manager_same_engine_no_reload(self) -> None:
        """同じエンジンを再取得してもリロードしない"""
        manager = EngineManager()
        engine = MockEngine()

        manager.register("mock", engine)
        manager.get("mock")
        manager.get("mock")

        assert engine.load_count == 1  # 1回しかロードしない

    def test_engine_manager_register_type_check(self) -> None:
        """BaseEngine以外を登録するとTypeErrorが発生する"""
        manager = EngineManager()
        with pytest.raises(TypeError):
            manager.register("invalid", "not_an_engine")  # type: ignore[arg-type]

    def test_engine_manager_reset(self) -> None:
        """resetでシングルトンがリセットされる"""
        manager1 = EngineManager()
        manager1.register("mock", MockEngine())
        EngineManager.reset()
        manager2 = EngineManager()
        assert manager1 is not manager2


# ===== FluxEngine テスト =====


class TestFluxEngine:
    """FluxEngineのインターフェーステスト (GPUなしでも実行可)"""

    def test_flux_engine_interface(self) -> None:
        """FluxEngineがload/unload/generateメソッドを持つ"""
        engine = FluxEngine()
        assert hasattr(engine, "load")
        assert hasattr(engine, "unload")
        assert hasattr(engine, "generate")
        assert hasattr(engine, "load_lora")
        assert hasattr(engine, "is_loaded")
        assert callable(engine.load)
        assert callable(engine.unload)
        assert callable(engine.generate)

    def test_flux_engine_is_base_engine(self) -> None:
        """FluxEngineはBaseEngineのサブクラスである"""
        engine = FluxEngine()
        assert isinstance(engine, BaseEngine)

    def test_flux_engine_initial_state(self) -> None:
        """FluxEngineの初期状態が正しい"""
        engine = FluxEngine()
        assert not engine.is_loaded
        assert engine._pipe is None
        assert engine._current_lora is None

    def test_flux_engine_custom_model_id(self) -> None:
        """カスタムモデルIDを設定できる"""
        engine = FluxEngine(model_id="custom/model")
        assert engine._model_id == "custom/model"

    def test_flux_engine_generate_without_load_raises(self) -> None:
        """ロード前にgenerateするとRuntimeErrorが発生する"""
        engine = FluxEngine()
        with pytest.raises(RuntimeError, match="モデルが未ロード"):
            engine.generate(
                prompt="test",
                output_path=Path("/tmp/test.png"),
            )

    def test_flux_engine_load_lora_without_load_raises(self) -> None:
        """ロード前にload_loraするとRuntimeErrorが発生する"""
        engine = FluxEngine()
        with pytest.raises(RuntimeError, match="モデルが未ロード"):
            engine.load_lora(Path("/tmp/test.safetensors"))
