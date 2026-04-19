"""BaseEngine: 全AIモデルエンジンの抽象基底クラス

全てのエンジン (FluxEngine, WanEngine等) はこのクラスを継承し、
load/unload/generate メソッドを実装する。
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

try:
    import torch  # type: ignore[import-untyped]
except ImportError:
    torch = None  # cocoro APIサーバーではtorch不要

logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """AIモデルエンジンの抽象基底クラス

    全エンジンは以下のライフサイクルに従う:
    1. コンストラクタでパラメータ設定
    2. load() でモデルをGPUにロード
    3. generate() で推論実行
    4. unload() でGPUメモリを解放
    """

    def __init__(self) -> None:
        """エンジンの初期化"""
        self._is_loaded: bool = False

    @property
    def is_loaded(self) -> bool:
        """エンジンがロード済みかどうか"""
        return self._is_loaded

    @abstractmethod
    def load(self) -> None:
        """モデルをGPUにロードする

        サブクラスで実装する際は、ロード完了後に
        self._is_loaded = True を設定すること。
        """
        ...

    def unload(self) -> None:
        """モデルをアンロードしてGPUメモリを解放する

        サブクラスでオーバーライドする場合は、
        super().unload() を呼び出すこと。
        """
        self._is_loaded = False
        if torch is not None:
            torch.cuda.empty_cache()
        logger.info("%s: GPUメモリを解放しました", self.__class__.__name__)

    @abstractmethod
    def generate(self, **kwargs: object) -> Path:
        """推論を実行し、生成物のパスを返す

        Args:
            **kwargs: エンジン固有の引数

        Returns:
            生成されたファイルのパス
        """
        ...
