"""script_engine.py: LLM台本自動生成エンジン

Google Gemini または Anthropic Claude を使用して、
企業向けのインフルエンサー動画台本をJSON形式で生成する。
BaseEngineのサブクラスとして実装（ロード/アンロード不要のAPI呼び出し型）。
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.engines.base import BaseEngine

logger = logging.getLogger(__name__)

# デフォルトプロバイダー
DEFAULT_PROVIDER = "gemini"

# 台本生成用システムプロンプト
SYSTEM_PROMPT = """あなたは日本語のプロフェッショナル動画台本ライターです。
企業向けのAIインフルエンサー動画台本を作成してください。

台本はJSON形式で出力してください。出力はJSONのみ（マークダウンや説明文は不要）：
{
  "title": "動画タイトル",
  "scenes": [
    {
      "scene_id": 1,
      "scene_type": "talking_head",
      "text": "ナレーション・セリフ（そのままTTSに渡す）",
      "caption": "テロップ文字列（短く）",
      "cinematic_prompt": ""
    },
    {
      "scene_id": 2,
      "scene_type": "cinematic",
      "text": "ナレーション・セリフ",
      "caption": "テロップ",
      "cinematic_prompt": "シネマティック動画のプロンプト（英語）"
    }
  ],
  "total_duration_estimate": "60s",
  "avatar_prompt": "アバター画像生成プロンプト（英語）"
}

ルール:
- シーン数は3〜6シーン
- scene_typeは "talking_head"（口が動くトーキングヘッド）または "cinematic"（シネマティック動画）
- textは自然な日本語の話し言葉
- cinematic_promptはsecene_typeが"cinematic"のときのみ英語で記述
- avatar_promptは企業イメージに合った日本人女性/男性の外見を英語で記述
"""


@dataclass
class ScriptScene:
    """台本の1シーン"""

    scene_id: int
    scene_type: str  # "talking_head" | "cinematic"
    text: str
    caption: str = ""
    cinematic_prompt: str = ""


@dataclass
class Script:
    """LLM生成台本"""

    title: str
    scenes: list[ScriptScene]
    avatar_prompt: str
    total_duration_estimate: str = "60s"
    # メタ情報
    company_name: str = ""
    product_name: str = ""
    provider: str = ""
    model: str = ""


class ScriptEngine(BaseEngine):
    """LLM台本自動生成エンジン

    Google Gemini または Anthropic Claude を使って、
    企業向けインフルエンサー動画台本をJSONで生成する。
    APIベースのため、load/unloadはno-op。
    """

    def __init__(
        self,
        provider: str = DEFAULT_PROVIDER,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """ScriptEngineの初期化

        Args:
            provider: LLMプロバイダー ("gemini" | "anthropic")
            model: モデル名 (Noneの場合はデフォルト)
            api_key: APIキー (Noneの場合は環境変数から取得)
        """
        super().__init__()  # BaseEngineの_is_loaded=Falseを初期化
        self._provider = provider
        self._api_key = api_key
        self._model = model or self._default_model(provider)

    def _default_model(self, provider: str) -> str:
        """プロバイダーごとのデフォルトモデルを返す"""
        defaults = {
            "gemini": "gemini-2.0-flash",
            "anthropic": "claude-3-5-haiku-latest",
        }
        return defaults.get(provider, "gemini-2.0-flash")

    def load(self) -> None:
        """APIベースのため、ロード処理は不要"""
        self._is_loaded = True
        logger.info("ScriptEngine: ロード完了 (provider=%s, model=%s)", self._provider, self._model)

    def unload(self) -> None:
        """APIベースのため、アンロード処理は不要"""
        self._is_loaded = False
        logger.info("ScriptEngine: アンロード完了")

    def generate(
        self,
        company_name: str,
        product_name: str,
        target_audience: str = "20代〜40代のビジネスパーソン",
        tone: str = "プロフェッショナルで親しみやすい",
        duration: str = "60秒",
        output_path: Path | None = None,
        **kwargs: Any,
    ) -> Script:
        """LLMを使って台本を生成する

        Args:
            company_name: 企業名
            product_name: 紹介する製品/サービス名
            target_audience: ターゲット視聴者
            tone: 動画のトーン・雰囲気
            duration: 動画の目標長さ
            output_path: 台本JSONの保存先 (Noneの場合は保存しない)
            **kwargs: その他のパラメータ

        Returns:
            生成されたScriptオブジェクト

        Raises:
            RuntimeError: LLM APIの呼び出しに失敗した場合
        """
        if not self._is_loaded:
            raise RuntimeError("ScriptEngineがロードされていません。load()を呼び出してください。")

        user_prompt = (
            f"企業名: {company_name}\n"
            f"紹介する製品/サービス: {product_name}\n"
            f"ターゲット視聴者: {target_audience}\n"
            f"トーン・雰囲気: {tone}\n"
            f"動画の長さ: {duration}\n\n"
            "上記の情報をもとに、AIインフルエンサー動画の台本をJSONで生成してください。"
        )

        logger.info(
            "ScriptEngine: 台本生成開始 (company=%s, product=%s, provider=%s)",
            company_name, product_name, self._provider,
        )

        if self._provider == "gemini":
            raw_json = self._call_gemini(user_prompt)
        elif self._provider == "anthropic":
            raw_json = self._call_anthropic(user_prompt)
        else:
            raise RuntimeError(f"不明なプロバイダー: {self._provider}")

        # JSONをパース
        script = self._parse_script_json(
            raw_json,
            company_name=company_name,
            product_name=product_name,
        )

        # ファイル保存
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(self._script_to_dict(script), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("ScriptEngine: 台本を保存しました → %s", output_path)

        logger.info("ScriptEngine: 台本生成完了 (scenes=%d)", len(script.scenes))
        return script

    def _call_gemini(self, user_prompt: str) -> str:
        """Google Gemini APIを呼び出す"""
        from google import genai
        from google.genai import types

        api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Google Gemini APIキーが見つかりません。"
                "環境変数 GEMINI_API_KEY を設定してください。"
            )

        client = genai.Client(api_key=api_key)

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=user_prompt)],
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.7,
                    max_output_tokens=4096,
                ),
            )
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API呼び出しエラー: {e}") from e

    def _call_anthropic(self, user_prompt: str) -> str:
        """Anthropic Claude APIを呼び出す"""
        import anthropic

        api_key = self._api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Anthropic APIキーが見つかりません。"
                "環境変数 ANTHROPIC_API_KEY を設定してください。"
            )

        client = anthropic.Anthropic(api_key=api_key)

        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text
        except Exception as e:
            raise RuntimeError(f"Anthropic API呼び出しエラー: {e}") from e

    def _parse_script_json(
        self,
        raw_json: str,
        company_name: str = "",
        product_name: str = "",
    ) -> Script:
        """LLMのJSON出力をScriptオブジェクトに変換する"""
        # JSONの前後の余分な文字を除去
        cleaned = raw_json.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"台本JSONのパースに失敗しました: {e}\n内容: {cleaned[:200]}") from e

        scenes = [
            ScriptScene(
                scene_id=s.get("scene_id", i + 1),
                scene_type=s.get("scene_type", "talking_head"),
                text=s.get("text", ""),
                caption=s.get("caption", ""),
                cinematic_prompt=s.get("cinematic_prompt", ""),
            )
            for i, s in enumerate(data.get("scenes", []))
        ]

        return Script(
            title=data.get("title", f"{company_name} - {product_name}"),
            scenes=scenes,
            avatar_prompt=data.get("avatar_prompt", "professional Japanese female presenter"),
            total_duration_estimate=data.get("total_duration_estimate", "60s"),
            company_name=company_name,
            product_name=product_name,
            provider=self._provider,
            model=self._model,
        )

    @staticmethod
    def _script_to_dict(script: Script) -> dict:
        """Scriptオブジェクトを辞書に変換する"""
        return {
            "title": script.title,
            "company_name": script.company_name,
            "product_name": script.product_name,
            "avatar_prompt": script.avatar_prompt,
            "total_duration_estimate": script.total_duration_estimate,
            "provider": script.provider,
            "model": script.model,
            "scenes": [
                {
                    "scene_id": s.scene_id,
                    "scene_type": s.scene_type,
                    "text": s.text,
                    "caption": s.caption,
                    "cinematic_prompt": s.cinematic_prompt,
                }
                for s in script.scenes
            ],
        }

    @staticmethod
    def load_from_file(script_path: Path) -> Script:
        """保存した台本JSONファイルを読み込む

        Args:
            script_path: 台本JSONファイルのパス

        Returns:
            Scriptオブジェクト
        """
        if not script_path.exists():
            raise FileNotFoundError(f"台本ファイルが見つかりません: {script_path}")

        data = json.loads(script_path.read_text(encoding="utf-8"))
        scenes = [
            ScriptScene(
                scene_id=s["scene_id"],
                scene_type=s["scene_type"],
                text=s["text"],
                caption=s.get("caption", ""),
                cinematic_prompt=s.get("cinematic_prompt", ""),
            )
            for s in data["scenes"]
        ]
        return Script(
            title=data.get("title", ""),
            scenes=scenes,
            avatar_prompt=data.get("avatar_prompt", ""),
            total_duration_estimate=data.get("total_duration_estimate", "60s"),
            company_name=data.get("company_name", ""),
            product_name=data.get("product_name", ""),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
        )
