"""VoiceEngine: Style-Bert-VITS2 による日本語テキスト音声合成エンジン

テキストを入力として日本語音声WAVファイルを生成する。
Style-Bert-VITS2 をHTTP APIとして使用する。
英語・アルファベット文字列は日本語読みに変換してから送信する。
"""

import logging
import re
import wave
from pathlib import Path

import requests

from src.engines.base import BaseEngine

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 英語→カタカナ変換辞書 (固有名詞・よく使う単語)
# ──────────────────────────────────────────────────────────────
_EN_TO_JA: dict[str, str] = {
    # 製品・ブランド名
    "cocoro studio": "こころスタジオ",
    "cocoro": "こころ",
    "studio": "スタジオ",
    "ai": "エーアイ",
    "AI": "エーアイ",
    # 一般英単語
    "video": "ビデオ",
    "image": "イメージ",
    "model": "モデル",
    "web": "ウェブ",
    "app": "アプリ",
    "online": "オンライン",
    "service": "サービス",
    "system": "システム",
    "content": "コンテンツ",
    "user": "ユーザー",
    "data": "データ",
    "cloud": "クラウド",
    "live": "ライブ",
    "brand": "ブランド",
    "design": "デザイン",
    "marketing": "マーケティング",
    "business": "ビジネス",
    "channel": "チャンネル",
    "media": "メディア",
    "digital": "デジタル",
    "platform": "プラットフォーム",
    "solution": "ソリューション",
    "support": "サポート",
    "product": "プロダクト",
    "company": "カンパニー",
    "global": "グローバル",
    "smart": "スマート",
    "premium": "プレミアム",
    "pro": "プロ",
}


def _normalize_text_for_tts(text: str) -> str:
    """Style-Bert-VITS2用にテキストを正規化する。

    英単語・アルファベット列を日本語読みに変換して
    TTSが正しく読み上げられるようにする。
    大文字小文字を区別せずに変換する。
    """
    # 辞書変換: 長い単語/フレーズを優先して置換 (順序依存を避けるため長さでソート)
    for en, ja in sorted(_EN_TO_JA.items(), key=lambda x: -len(x[0])):
        # 単語境界を考慮して大文字小文字無視で置換
        pattern = re.compile(re.escape(en), re.IGNORECASE)
        text = pattern.sub(ja, text)

    # 残った連続アルファベット (辞書未登録) をそのまま残す
    # (Style-Bert-VITS2が自力で読もうとするため、あえて変換しない)
    return text

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
        model_id: int | None = None,
        speed_scale: float = 1.0,
        pitch_scale: float = 0.0,
        volume_scale: float = 1.0,
    ) -> Path:
        """テキストから音声WAVファイルを生成する

        Args:
            text: 読み上げるテキスト
            output_path: 出力WAVファイルパス
            speaker_id: 話者ID (Noneの場合はデフォルト値を使用)
            model_id: Style-Bert-VITS2 モデルID (Noneの場合はデフォルト値を使用)
            speed_scale: 話速 (1.0=標準)
            pitch_scale: ピッチ (0.0=標準)
            volume_scale: 音量 (1.0=標準)

        Returns:
            生成した音声ファイルのパス

        Raises:
            RuntimeError: VoiceEngineが未ロードまたはAPI呼び出し失敗
        """
        if not self._is_loaded or self._session is None:
            raise RuntimeError("VoiceEngine: ロードされていません。先のload()を呼んでください")

        speaker = speaker_id if speaker_id is not None else self._speaker_id
        mid = model_id if model_id is not None else 0

        # 出力ディレクトリ作成
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 英語テキストをStyle-Bert-VITS2が読める日本語読みに変換
        normalized_text = _normalize_text_for_tts(text)
        if normalized_text != text:
            logger.info(
                "VoiceEngine: テキスト正規化: '%s' → '%s'",
                text[:50], normalized_text[:50],
            )

        logger.info(
            "VoiceEngine: 音声生成開始 (model=%d, speaker=%d, text='%s')",
            mid, speaker, normalized_text[:50],
        )

        # Style-Bert-VITS2 API呼び出し (/voice エンドポイント)
        query_resp = self._session.get(
            f"{self._voicevox_url}/voice",
            params={"text": normalized_text, "model_id": mid, "speaker_id": speaker, "style": "Neutral"},
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
