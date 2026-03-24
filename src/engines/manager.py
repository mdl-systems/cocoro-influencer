"""EngineManager: GPUメモリを一元管理するエンジンマネージャー

RTX 5090 (32GB VRAM) 上で複数AIモデルを安全に切り替えるため、
同時に1つのエンジンのみロードする。
"""

import logging
from threading import Lock

from src.engines.base import BaseEngine

logger = logging.getLogger(__name__)


class EngineManager:
    """エンジンのロード/アンロードを一元管理するシングルトン

    GPUメモリ制約のため、同時に1つのエンジンのみロードする。
    get() で別エンジンを要求すると、現在のエンジンを自動アンロードする。
    """

    _instance: "EngineManager | None" = None
    _lock: Lock = Lock()

    def __new__(cls) -> "EngineManager":
        """シングルトンパターン: インスタンスは1つだけ"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        """エンジン辞書とアクティブエンジン追跡の初期化"""
        if self._initialized:
            return
        self._engines: dict[str, BaseEngine] = {}
        self._active: str | None = None
        self._initialized: bool = True
        logger.info("EngineManager: 初期化完了")

    def register(self, name: str, engine: BaseEngine) -> None:
        """エンジンを名前付きで登録する

        Args:
            name: エンジンの識別名 (例: "flux", "wan")
            engine: BaseEngineのサブクラスインスタンス
        """
        if not isinstance(engine, BaseEngine):
            raise TypeError(
                f"engineはBaseEngineのサブクラスである必要があります: {type(engine)}"
            )
        self._engines[name] = engine
        logger.info("EngineManager: '%s' を登録しました", name)

    def get(self, name: str) -> BaseEngine:
        """エンジンを取得しロードする

        現在アクティブな別エンジンがあれば先にアンロードする。

        Args:
            name: 取得するエンジンの識別名

        Returns:
            ロード済みのエンジンインスタンス

        Raises:
            KeyError: 未登録のエンジン名を指定した場合
        """
        if name not in self._engines:
            raise KeyError(f"未登録のエンジン: '{name}'")

        # 別のエンジンがアクティブならアンロード
        if self._active is not None and self._active != name:
            logger.info(
                "EngineManager: '%s' をアンロードして '%s' に切替",
                self._active,
                name,
            )
            self._engines[self._active].unload()

        # 指定エンジンをロード
        engine = self._engines[name]
        if not engine.is_loaded:
            engine.load()
        self._active = name

        return engine

    @property
    def active_engine_name(self) -> str | None:
        """現在アクティブなエンジン名を返す"""
        return self._active

    def unload_all(self) -> None:
        """全エンジンをアンロードする"""
        for name, engine in self._engines.items():
            if engine.is_loaded:
                engine.unload()
                logger.info("EngineManager: '%s' をアンロードしました", name)
        self._active = None

    @classmethod
    def reset(cls) -> None:
        """シングルトンをリセットする (テスト用)"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.unload_all()
            cls._instance = None
