"""worker.py: cocoro-OSエージェントワーカー

cocoro-OSと通信してタスクを受け取り、
実行してその結果を報告するメインワーカーループ。
"""

import logging
import signal
import time
from types import FrameType

from src.agent.cocoro_client import CocoroClient, CocoroTaskResult
from src.agent.interface import CocoroAgentConfig
from src.agent.task_handler import TaskDispatcher

logger = logging.getLogger(__name__)


class CocoroWorker:
    """cocoro-OSエージェントワーカー

    起動するとcocoro-OSに登録し、タスクをポーリングして実行し続ける。
    SIGINTまたはSIGTERMで正常終了する。
    """

    def __init__(
        self,
        config: CocoroAgentConfig | None = None,
        poll_interval: float = 5.0,
        heartbeat_interval: float = 30.0,
    ) -> None:
        """ワーカーの初期化

        Args:
            config: エージェント設定 (Noneの場合はデフォルト設定)
            poll_interval: タスクポーリング間隔 (秒)
            heartbeat_interval: ハートビート送信間隔 (秒)
        """
        self._config = config or CocoroAgentConfig()
        self._poll_interval = poll_interval
        self._heartbeat_interval = heartbeat_interval
        self._client = CocoroClient(self._config)
        self._dispatcher = TaskDispatcher()
        self._running = False
        self._last_heartbeat = 0.0

    def register_handler(self, task_type: str, handler) -> None:  # type: ignore[type-arg]
        """カスタムタスクハンドラーを登録する

        Args:
            task_type: タスクタイプ識別子
            handler: ハンドラー関数 (CocoroTask) -> CocoroTaskResult
        """
        self._dispatcher.register(task_type, handler)

    def run(self) -> None:
        """ワーカーのメインループを開始する

        Ctrl+C またはSIGTERMで正常終了する。
        """
        # シグナルハンドラーを設定
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # cocoro-OSに登録
        try:
            agent_id = self._client.register()
            logger.info("CocoroWorker: 起動しました (agent_id=%s)", agent_id)
        except RuntimeError as e:
            logger.error("CocoroWorker: 登録に失敗しました: %s", e)
            return

        self._running = True
        self._last_heartbeat = time.time()

        try:
            self._main_loop()
        finally:
            # 終了時に登録解除
            self._client.unregister()
            logger.info("CocoroWorker: 停止しました")

    def _main_loop(self) -> None:
        """タスクポーリングと実行のメインループ"""
        logger.info(
            "CocoroWorker: ポーリング開始 (interval=%.1fs)",
            self._poll_interval,
        )

        while self._running:
            # ハートビート送信
            now = time.time()
            if now - self._last_heartbeat >= self._heartbeat_interval:
                if self._client.send_heartbeat():
                    logger.debug("CocoroWorker: ハートビート送信")
                self._last_heartbeat = now

            # タスクを1件取得
            try:
                task = self._client.poll_task()
            except RuntimeError as e:
                logger.warning("CocoroWorker: ポーリングエラー: %s", e)
                time.sleep(self._poll_interval)
                continue

            if task is None:
                # タスクなし → 待機
                time.sleep(self._poll_interval)
                continue

            # タスクを実行
            logger.info(
                "CocoroWorker: タスク受信 (task_id=%s, type=%s)",
                task.task_id, task.task_type,
            )
            result = self._dispatcher.dispatch(task)

            # 結果を報告
            try:
                self._client.report_result(result)
            except RuntimeError as e:
                logger.error(
                    "CocoroWorker: 結果報告に失敗しました (task_id=%s): %s",
                    task.task_id, e,
                )

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        """シグナル受信時にワーカーを停止する"""
        logger.info("CocoroWorker: 停止シグナルを受信しました (signal=%d)", signum)
        self._running = False

    def stop(self) -> None:
        """ワーカーを正常停止する"""
        self._running = False
