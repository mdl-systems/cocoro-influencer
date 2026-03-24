"""FastAPI APIテスト

httpxのTestClientを使用してAPIエンドポイントをテストする。
実際のAI処理はモックアップ。
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.main import app
from src.api.models import JobResponse
from src.db.schema import Base, get_session

# テスト用インメモリSQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_session():
    """テスト用DBセッションオーバーライド"""
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture(autouse=True)
async def setup_test_db():
    """各テスト前にテーブルを作成し、テスト後に削除する"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def test_client():
    """テスト用HTTPクライアント"""
    app.dependency_overrides[get_session] = override_get_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ===========================================================
# ヘルスチェックテスト
# ===========================================================

class TestHealth:
    """ヘルスチェックエンドポイントのテスト"""

    async def test_root(self, test_client: AsyncClient) -> None:
        """GETルートがサービス情報を返す"""
        async with test_client as client:
            response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "cocoro-influencer API"
        assert data["status"] == "running"

    async def test_health(self, test_client: AsyncClient) -> None:
        """GETヘルスチェックがokを返す"""
        async with test_client as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ===========================================================
# ジョブAPIテスト
# ===========================================================

class TestJobsAPI:
    """ジョブAPIのテスト"""

    async def test_list_jobs_empty(self, test_client: AsyncClient) -> None:
        """ジョブが0件の場合、空リストを返す"""
        async with test_client as client:
            response = await client.get("/api/v1/jobs/")
        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0

    async def test_get_job_not_found(self, test_client: AsyncClient) -> None:
        """存在しないジョブIDで404を返す"""
        async with test_client as client:
            response = await client.get("/api/v1/jobs/999")
        assert response.status_code == 404

    async def test_list_jobs_after_create(self, test_client: AsyncClient) -> None:
        """ジョブ作成後にリストに表示される"""
        from src.db.schema import JobCRUD, async_session_factory

        # 直接DBにジョブを作成
        app.dependency_overrides[get_session] = override_get_session
        async with test_session_factory() as session:
            await JobCRUD.create(session, job_type="avatar", params='{"test": true}')
            await session.commit()

        async with test_client as client:
            response = await client.get("/api/v1/jobs/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["jobs"][0]["job_type"] == "avatar"
        assert data["jobs"][0]["status"] == "pending"


# ===========================================================
# アバターAPIテスト
# ===========================================================

class TestAvatarsAPI:
    """アバターAPIのテスト"""

    async def test_list_avatars_empty(self, test_client: AsyncClient) -> None:
        """アバターが0件の場合、空リストを返す"""
        async with test_client as client:
            response = await client.get("/api/v1/avatars/")
        assert response.status_code == 200
        data = response.json()
        assert data["avatars"] == []
        assert data["total"] == 0

    async def test_get_avatar_not_found(self, test_client: AsyncClient) -> None:
        """存在しないアバターIDで404を返す"""
        async with test_client as client:
            response = await client.get("/api/v1/avatars/999")
        assert response.status_code == 404

    async def test_generate_avatar_returns_job_id(self, test_client: AsyncClient) -> None:
        """アバター生成APIがjob_idを含むレスポンスを返す (202)
        
        バックグラウンドタスク（実際のAI生成）はモックして、
        APIのレスポンス（job_id返却）のみテストする。
        """
        from unittest.mock import patch, AsyncMock

        request_body = {
            "customer_name": "テスト顧客",
            "prompt": "ビジネススーツの日本人女性",
            "width": 512,
            "height": 512,
            "num_inference_steps": 1,
        }
        # バックグラウンドタスクをモックしてAI生成をスキップ
        with patch("src.api.routes.avatars._run_avatar_generation", new_callable=AsyncMock):
            async with test_client as client:
                response = await client.post("/api/v1/avatars/generate", json=request_body)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["job_id"] is not None
        assert "message" in data

    async def test_generate_avatar_creates_job(self, test_client: AsyncClient) -> None:
        """アバター生成後にジョブが作成されている"""
        from unittest.mock import patch, AsyncMock

        request_body = {
            "customer_name": "テスト顧客2",
            "prompt": "キャビンアテンダント風の女性",
            "width": 512,
            "height": 512,
            "num_inference_steps": 1,
        }
        # バックグラウンドタスクをモックしてAI生成をスキップ
        with patch("src.api.routes.avatars._run_avatar_generation", new_callable=AsyncMock):
            async with test_client as client:
                # アバター生成
                gen_response = await client.post("/api/v1/avatars/generate", json=request_body)
                assert gen_response.status_code == 202
                job_id = gen_response.json()["job_id"]

                # ジョブが作成されていることを確認
                job_response = await client.get(f"/api/v1/jobs/{job_id}")
                assert job_response.status_code == 200
                job_data = job_response.json()
                assert job_data["job_type"] == "avatar"
                assert job_data["id"] == job_id
