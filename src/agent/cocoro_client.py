"""cocoro_client.py: cocoro-OS REST API クライアント

cocoro-OSのCORE_URLに対してHTTPリクエストを送り、
エージェントの登録・タスク受信・結果送信を行うクライアント。
schema v7に準拠。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.agent.interface import CocoroAgentConfig

logger = logging.getLogger(__name__)


# ===========================================================
# タスクデータクラス
# ===========================================================

@dataclass
class CocoroTask:
    """cocoro-OSから受け取るタスク定義"""

    task_id: str
    task_type: str           # "generate_avatar" | "generate_video" | etc.
    payload: dict            # タスク固有のパラメータ
    priority: int = 5        # 優先度 (1=最高, 10=最低)
    created_at: str = ""


@dataclass
class CocoroTaskResult:
    """cocoro-OSに送信するタスク結果"""

    task_id: str
    status: str              # "success" | "error"
    output: dict = field(default_factory=dict)   # 出力情報 (ファイルパスなど)
    error_message: str = ""


# ===========================================================
# cocoro-OS APIクライアント
# ===========================================================

class CocoroClient:
    """cocoro-OS REST API クライアント

    cocoro-OSのCORE_URLとHTTPで通信し、
    エージェント登録・タスクポーリング・結果報告を行う。
    """

    def __init__(self, config: CocoroAgentConfig, agent_id: str | None = None) -> None:
        """クライアント初期化

        Args:
            config: エージェント設定
            agent_id: エージェントID（省略時は自動割り当て）
        """
        self._config = config
        self._agent_id = agent_id
        self._registered = False
        self._headers = {
            "X-API-Key": config.cocoro_api_key,
            "Content-Type": "application/json",
            "X-Schema-Version": config.schema_version,
        }
        self._base_url = config.cocoro_core_url.rstrip("/")
        logger.info(
            "CocoroClient: 初期化 (url=%s, schema=%s)",
            self._base_url, config.schema_version
        )

    @property
    def agent_id(self) -> str | None:
        """登録済みエージェントID"""
        return self._agent_id

    @property
    def is_registered(self) -> bool:
        """cocoro-OSに登録済みかどうか"""
        return self._registered

    def register(self) -> str:
        """cocoro-OSにエージェントを登録する

        Returns:
            割り当てられたエージェントID

        Raises:
            httpx.HTTPError: API呼び出し失敗
            RuntimeError: 登録失敗
        """
        payload = {
            "agent_type": self._config.agent_type,
            "agent_role": self._config.agent_role,
            "capabilities": self._config.capabilities,
            "schema": self._config.schema_version,
            "cocoro_net": self._config.cocoro_net,
        }

        logger.info("CocoroClient: cocoro-OSに登録します...")
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self._base_url}/agents/register",
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()
                data = response.json()

            self._agent_id = data.get("agent_id") or data.get("id")
            if not self._agent_id:
                raise RuntimeError(f"agent_idが返されませんでした: {data}")

            self._registered = True
            logger.info("CocoroClient: 登録完了 (agent_id=%s)", self._agent_id)
            return self._agent_id

        except httpx.HTTPError as e:
            raise RuntimeError(f"cocoro-OS登録エラー: {e}") from e

    def poll_task(self) -> CocoroTask | None:
        """タスクキューからタスクを1件取得する

        Returns:
            タスクオブジェクト (キューが空の場合はNone)

        Raises:
            RuntimeError: 未登録の場合
        """
        if not self._registered or not self._agent_id:
            raise RuntimeError("register()を先に呼び出してください")

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self._base_url}/agents/{self._agent_id}/tasks/next",
                    headers=self._headers,
                )
                if response.status_code == 204:
                    return None  # タスクなし
                response.raise_for_status()
                data = response.json()

            return CocoroTask(
                task_id=data["task_id"],
                task_type=data["task_type"],
                payload=data.get("payload", {}),
                priority=data.get("priority", 5),
                created_at=data.get("created_at", ""),
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None  # タスクなし
            raise RuntimeError(f"タスクポーリングエラー: {e}") from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"タスクポーリングエラー: {e}") from e

    def report_result(self, result: CocoroTaskResult) -> None:
        """タスク実行結果をcocoro-OSに報告する

        Args:
            result: タスク結果オブジェクト

        Raises:
            RuntimeError: API呼び出し失敗
        """
        payload = {
            "task_id": result.task_id,
            "agent_id": self._agent_id,
            "status": result.status,
            "output": result.output,
            "error_message": result.error_message,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self._base_url}/tasks/{result.task_id}/result",
                    json=payload,
                    headers=self._headers,
                )
                response.raise_for_status()

            logger.info(
                "CocoroClient: 結果を報告しました (task_id=%s, status=%s)",
                result.task_id, result.status
            )

        except httpx.HTTPError as e:
            raise RuntimeError(f"結果報告エラー: {e}") from e

    def send_heartbeat(self) -> bool:
        """ハートビートを送信してエージェントの alive を報告する

        Returns:
            True: 成功 / False: 失敗
        """
        if not self._agent_id:
            return False
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.put(
                    f"{self._base_url}/agents/{self._agent_id}/heartbeat",
                    headers=self._headers,
                )
                return response.status_code < 300
        except httpx.HTTPError:
            return False

    def unregister(self) -> None:
        """cocoro-OSからエージェントを登録解除する"""
        if not self._agent_id:
            return
        try:
            with httpx.Client(timeout=5.0) as client:
                client.delete(
                    f"{self._base_url}/agents/{self._agent_id}",
                    headers=self._headers,
                )
            logger.info("CocoroClient: 登録解除しました (agent_id=%s)", self._agent_id)
        except httpx.HTTPError as e:
            logger.warning("CocoroClient: 登録解除に失敗しました: %s", e)
        finally:
            self._registered = False
