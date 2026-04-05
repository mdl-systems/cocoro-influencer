"""
TTS（Text-to-Speech）統合エンジン

複数のTTSバックエンドに対応し、台本テキストから音声ファイルを生成する。
対応エンジン:
  - StyleBERT-VITS2: 高品質日本語合成（ローカルGPU）
  - OpenAI TTS: クラウドAPI（フォールバック）
"""

import asyncio
import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tts.engine")


class TTSBase(ABC):
    """TTS抽象基底クラス"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str = "default",
        speed: float = 1.0,
    ) -> dict:
        """
        テキストから音声を合成。

        Args:
            text: 合成するテキスト
            output_path: 出力WAVファイルパス
            voice: 音声モデル/ボイスID
            speed: 再生速度 (1.0 = 通常)

        Returns:
            {"path": 出力パス, "duration": 秒数}
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass


class StyleBERTVITS2Engine(TTSBase):
    """
    StyleBERT-VITS2 TTS エンジン

    ローカルのStyleBERT-VITS2 APiサーバーと通信して音声合成。
    GPU上で動作し、高品質な日本語音声を生成。
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:5000",
        model_name: str = "jvnv-F1-jp",
    ):
        self.api_url = api_url
        self.model_name = model_name

    async def health_check(self) -> bool:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/voice",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str = "default",
        speed: float = 1.0,
    ) -> dict:
        import aiohttp

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        params = {
            "text": text,
            "model_name": self.model_name,
            "speaker_id": 0,
            "speed": speed,
            "language": "JP",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_url}/voice",
                params=params,
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"StyleBERT-VITS2 error: {resp.status}")

                audio_data = await resp.read()
                with open(output_path, "wb") as f:
                    f.write(audio_data)

        # 音声の長さを取得
        duration = await self._get_duration(output_path)

        logger.info(f"TTS完了: {output_path} ({duration:.1f}秒)")

        return {"path": output_path, "duration": duration}

    @staticmethod
    async def _get_duration(wav_path: str) -> float:
        """WAVファイルの長さを取得（FFprobe使用）"""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    wav_path,
                ],
                capture_output=True,
                text=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return 5.0  # フォールバック


class OpenAITTSEngine(TTSBase):
    """
    OpenAI TTS エンジン（フォールバック用）

    OpenAI APIを使用してクラウドで音声合成。
    GPU不要だがネットワーク接続が必要。
    """

    def __init__(self, api_key: str, voice: str = "nova"):
        self.api_key = api_key
        self.voice = voice

    async def health_check(self) -> bool:
        return bool(self.api_key and self.api_key != "sk-xxxxxxxxxxxxxxxxxxxxxxxx")

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str = "default",
        speed: float = 1.0,
    ) -> dict:
        import aiohttp

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "tts-1-hd",
            "input": text,
            "voice": voice if voice != "default" else self.voice,
            "speed": speed,
            "response_format": "wav",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/audio/speech",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise RuntimeError(f"OpenAI TTS error: {resp.status} {error}")

                audio_data = await resp.read()
                with open(output_path, "wb") as f:
                    f.write(audio_data)

        duration = await StyleBERTVITS2Engine._get_duration(output_path)
        logger.info(f"TTS完了 (OpenAI): {output_path} ({duration:.1f}秒)")

        return {"path": output_path, "duration": duration}


class TTSManager:
    """
    TTS管理クラス

    設定に基づいてエンジンを選択し、フォールバック機能を提供。
    """

    def __init__(self, settings):
        self.settings = settings
        self.engines = {}

        # エンジンの初期化
        self.engines["style_bert_vits2"] = StyleBERTVITS2Engine(
            api_url=f"http://127.0.0.1:5000",
            model_name=settings.tts.style_bert_model,
        )

        if settings.tts.openai_api_key:
            self.engines["openai"] = OpenAITTSEngine(
                api_key=settings.tts.openai_api_key,
                voice=settings.tts.openai_tts_voice,
            )

        self.primary_engine = settings.tts.engine

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str = "default",
        speed: float = 1.0,
    ) -> dict:
        """
        音声合成を実行。プライマリエンジン失敗時はフォールバック。
        """
        # プライマリエンジンを試行
        primary = self.engines.get(self.primary_engine)
        if primary:
            try:
                if await primary.health_check():
                    return await primary.synthesize(text, output_path, voice, speed)
                else:
                    logger.warning(f"プライマリTTS ({self.primary_engine}) が利用不可")
            except Exception as e:
                logger.warning(f"プライマリTTSエラー: {e}")

        # フォールバック
        for name, engine in self.engines.items():
            if name == self.primary_engine:
                continue
            try:
                if await engine.health_check():
                    logger.info(f"フォールバック: {name}")
                    return await engine.synthesize(text, output_path, voice, speed)
            except Exception as e:
                logger.warning(f"フォールバックTTSエラー ({name}): {e}")

        raise RuntimeError("利用可能なTTSエンジンがありません")
