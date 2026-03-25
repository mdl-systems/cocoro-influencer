"""test_agent.py: Phase 5 cocoro-OS統合テスト

cocoro-OSのAPIサーバーは実際には呼び出さずモックして、
CocoroClient / TaskDispatcher / CocoroWorkerのロジックをテストする。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import httpx
import pytest

from src.agent.cocoro_client import CocoroClient, CocoroTask, CocoroTaskResult
from src.agent.interface import CocoroAgentConfig
from src.agent.task_handler import TaskDispatcher
from src.agent.worker import CocoroWorker


# ===========================================================
# CocoroAgentConfigのテスト
# ===========================================================

class TestCocoroAgentConfig:
    """エージェント設定のテスト"""

    def test_default_config(self) -> None:
        """デフォルト設定値の確認"""
        config = CocoroAgentConfig()
        assert config.agent_type == "worker"
        assert config.agent_role == "specialist"
        assert config.cocoro_core_url == "http://192.168.50.92:8001"
        assert config.cocoro_api_key == "cocoro-2026"
        assert config.schema_version == "v7"
        assert "generate_avatar" in config.capabilities
        assert "generate_script" in config.capabilities
        assert "pipeline_run" in config.capabilities
        assert "health_check" in config.capabilities

    def test_custom_config(self) -> None:
        """カスタム設定値が設定できる"""
        config = CocoroAgentConfig(
            cocoro_core_url="http://localhost:8001",
            agent_type="tester",
        )
        assert config.cocoro_core_url == "http://localhost:8001"
        assert config.agent_type == "tester"
        assert config.cocoro_api_key == "cocoro-2026"  # デフォルト値は引き継ぐ


# ===========================================================
# CocoroClientのテスト
# ===========================================================

class TestCocoroClient:
    """cocoro-OSクライアントのテスト"""

    def _make_client(self) -> CocoroClient:
        """テスト用クライアントを作成する"""
        config = CocoroAgentConfig(
            cocoro_core_url="http://localhost:8001",
        )
        return CocoroClient(config)

    def test_initial_state(self) -> None:
        """初期状態の確認"""
        client = self._make_client()
        assert not client.is_registered
        assert client.agent_id is None

    def test_register_success(self) -> None:
        """正常な登録処理"""
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.json.return_value = {"agent_id": "test-agent-001"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__ = MagicMock(return_value=mock_http.return_value)
            mock_http.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.return_value.post.return_value = mock_response

            agent_id = client.register()

        assert agent_id == "test-agent-001"
        assert client.is_registered
        assert client.agent_id == "test-agent-001"

    def test_register_http_error_raises(self) -> None:
        """HTTP エラー時にRuntimeErrorを送出する"""
        client = self._make_client()

        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__ = MagicMock(return_value=mock_http.return_value)
            mock_http.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.return_value.post.side_effect = httpx.ConnectError("接続拒否")

            with pytest.raises(RuntimeError, match="登録エラー"):
                client.register()

    def test_poll_task_without_register_raises(self) -> None:
        """未登録状態でpoll_taskするとRuntimeError"""
        client = self._make_client()
        with pytest.raises(RuntimeError, match="register"):
            client.poll_task()

    def test_poll_task_returns_none_on_empty(self) -> None:
        """タスクがない場合はNoneを返す"""
        client = self._make_client()
        client._registered = True
        client._agent_id = "test-001"

        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__ = MagicMock(return_value=mock_http.return_value)
            mock_http.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.return_value.get.return_value = mock_response

            task = client.poll_task()

        assert task is None

    def test_poll_task_returns_task(self) -> None:
        """タスクがある場合はCocoroTaskを返す"""
        client = self._make_client()
        client._registered = True
        client._agent_id = "test-001"

        task_data = {
            "task_id": "task-xyz",
            "task_type": "health_check",
            "payload": {},
            "priority": 3,
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = task_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__ = MagicMock(return_value=mock_http.return_value)
            mock_http.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.return_value.get.return_value = mock_response

            task = client.poll_task()

        assert task is not None
        assert task.task_id == "task-xyz"
        assert task.task_type == "health_check"
        assert task.priority == 3

    def test_report_result(self) -> None:
        """結果報告が正常に呼ばれる"""
        client = self._make_client()
        client._registered = True
        client._agent_id = "test-001"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_http:
            mock_http.return_value.__enter__ = MagicMock(return_value=mock_http.return_value)
            mock_http.return_value.__exit__ = MagicMock(return_value=False)
            mock_http.return_value.post.return_value = mock_response

            result = CocoroTaskResult(
                task_id="task-xyz",
                status="success",
                output={"message": "ok"},
            )
            client.report_result(result)  # エラーなし = 成功

        mock_http.return_value.post.assert_called_once()


# ===========================================================
# TaskDispatcherのテスト
# ===========================================================

class TestTaskDispatcher:
    """タスクディスパッチャーのテスト"""

    def test_unknown_task_type_returns_error(self) -> None:
        """未知のタスクタイプはエラー結果を返す"""
        dispatcher = TaskDispatcher()
        task = CocoroTask(
            task_id="t001",
            task_type="unknown_type",
            payload={},
        )
        result = dispatcher.dispatch(task)
        assert result.status == "error"
        assert "未知のタスクタイプ" in result.error_message

    def test_health_check_task(self) -> None:
        """health_checkタスクがsuccessを返す"""
        dispatcher = TaskDispatcher()
        task = CocoroTask(
            task_id="t002",
            task_type="health_check",
            payload={},
        )
        result = dispatcher.dispatch(task)
        assert result.status == "success"
        assert result.task_id == "t002"

    def test_custom_handler_registration(self) -> None:
        """カスタムハンドラーが登録・実行できる"""
        dispatcher = TaskDispatcher()

        def my_handler(task: CocoroTask) -> CocoroTaskResult:
            return CocoroTaskResult(
                task_id=task.task_id,
                status="success",
                output={"custom": True},
            )

        dispatcher.register("my_task", my_handler)
        task = CocoroTask(task_id="t003", task_type="my_task", payload={})
        result = dispatcher.dispatch(task)
        assert result.status == "success"
        assert result.output["custom"] is True

    def test_handler_exception_returns_error(self) -> None:
        """ハンドラー内の例外がエラー結果として返される"""
        dispatcher = TaskDispatcher()

        def failing_handler(task: CocoroTask) -> CocoroTaskResult:
            raise RuntimeError("ハンドラーでエラーが発生しました")

        dispatcher.register("fail_task", failing_handler)
        task = CocoroTask(task_id="t004", task_type="fail_task", payload={})
        result = dispatcher.dispatch(task)
        assert result.status == "error"
        assert "ハンドラーでエラーが発生しました" in result.error_message


# ===========================================================
# CocoroWorkerのテスト
# ===========================================================

class TestCocoroWorker:
    """ワーカーのテスト"""

    def test_worker_initial_state(self) -> None:
        """ワーカーの初期状態確認"""
        worker = CocoroWorker()
        assert not worker._running
        assert isinstance(worker._dispatcher, TaskDispatcher)
        assert isinstance(worker._client, CocoroClient)

    def test_worker_register_failure_exits_cleanly(self) -> None:
        """登録失敗時にrunが正常にreturnする"""
        worker = CocoroWorker()
        with patch.object(worker._client, "register", side_effect=RuntimeError("接続失敗")):
            worker.run()  # 例外が外に出ないことを確認
        assert not worker._running

    def test_worker_custom_handler(self) -> None:
        """カスタムハンドラーが登録できる"""
        worker = CocoroWorker()

        def my_handler(task: CocoroTask) -> CocoroTaskResult:
            return CocoroTaskResult(task_id=task.task_id, status="success")

        worker.register_handler("my_task", my_handler)
        # ディスパッチャーにハンドラーが登録されていることを確認
        assert "my_task" in worker._dispatcher._handlers

    def test_worker_stop(self) -> None:
        """stop()でワーカーが停止する"""
        worker = CocoroWorker()
        worker._running = True
        worker.stop()
        assert not worker._running
