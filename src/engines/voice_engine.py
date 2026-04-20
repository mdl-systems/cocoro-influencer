"""VoiceEngine: VOICEVOX による日本語テキスト音声合成エンジン

テキストを入力として日本語音声WAVファイルを生成する。
VOICEVOX ENGINEをHTTP APIとして使用する。
"""

import logging
import wave
from pathlib import Path

import requests

from src.engines.base import BaseEngine

logger = logging.getLogger(__name__)

# VOICEVOX ENGINEのデフォルトURL
DEFAULT_VOICEVOX_URL = "http://localhost:5000"

# デフォルト話者ID (ずんだもん=3, 四国めたん=2, etc.)
DEFAULT_SPEAKER_ID = 3


class VoiceEngine(BaseEngine):
    """VOICEVOX による日本語テキスト音声合成エンジン

    VOICEVOX ENGINEがローカルで起動している必要がある。
    テキスト → WAV音声ファイルを生成する。
    """

    def __init__(
        self,
        voicevox_url: str = DEFAULT_VOICEVOX_URL,
        speaker_id: int = DEFAULT_SPEAKER_ID,
    ) -> None:
        """VoiceEngineの初期化

        Args:
            voicevox_url: VOICEVOX ENGINE の URL
            speaker_id: 話者ID
        """
        super().__init__()
        self._voicevox_url: str = voicevox_url.rstrip("/")
        self._speaker_id: int = speaker_id
        self._session: requests.Session | None = None

    def load(self) -> None:
        """VOICEVOX ENGINEへの接続確認

        VOICEVOX ENGINEはHTTPサービスのため、
        接続テストのみ行う。
        """
        logger.info("VoiceEngine: VOICEVOX ENGINE接続確認 (%s)", self._voicevox_url)
        self._session = requests.Session()

        try:
            resp = self._session.get(f"{self._voicevox_url}/status", timeout=5)
            resp.raise_for_status()
            version = resp.text.strip('"')
            logger.info("VoiceEngine: VOICEVOX ENGINE v%s に接続しました", version)
        except requests.ConnectionError:
            logger.warning(
                "VoiceEngine: VOICEVOX ENGINEに接続できません (%s)。"
                "起動しているか確認してください。",
                self._voicevox_url,
            )

        self._is_loaded = True
        logger.info("VoiceEngine: ロード完了")

    def unload(self) -> None:
        """VoiceEngineのアンロード"""
        if self._session is not None:
            self._session.close()
            self._session = None
        super().unload()
        logger.info("VoiceEngine: アンロード完了")

    def generate(
        self,
        *,
        text: str,
        output_path: Path,
        speaker_id: int | None = None,
        speed_scale: float = 1.0,
        pitch_scale: float = 0.0,
        volume_scale: float = 1.0,
    ) -> Path:
        """テキストから音声WAVファイルを生成する

        Args:
            text: 読み上げるテキスト
            output_path: 出力WAVファイルパス
            speaker_id: 話者ID (Noneの場合はデフォルト値を使用)
            speed_scale: 話速 (1.0=標準)
            pitch_scale: ピッチ (0.0=標準)
            volume_scale: 音量 (1.0=標準)

        Returns:
            生成した音声ファイルのパス

        Raises:
            RuntimeError: VoiceEngineが未ロードまたはAPI呼び出し失敗
        """
        if not self._is_loaded or self._session is None:
            raise RuntimeError("VoiceEngine: ロードされていません。先にload()を呼んでください")

        speaker = speaker_id if speaker_id is not None else self._speaker_id

        # 出力ディレクトリ作成
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "VoiceEngine: 音声生成開始 (speaker=%d, text='%s')",
            speaker,
            text[:50],
        )

        # Style-Bert-VITS2 API呼び出し (/voice エンドポイント)
        query_resp = self._session.get(
            f"{self._voicevox_url}/voice",
            params={"text": text, "model_id": 0, "speaker_id": 0, "style": "Neutral"},
            timeout=60,
        )
        query_resp.raise_for_status()
        output_path.write_bytes(query_resp.content)

        # 生成した音声の長さをログ出力
        try:
            with wave.open(str(output_path), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
                logger.info(
                    "VoiceEngine: 音声生成完了 (%s, %.1f秒)", output_path, duration
                )
        except Exception:
            logger.info("VoiceEngine: 音声生成完了 (%s)", output_path)

        return output_path
