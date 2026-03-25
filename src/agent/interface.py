"""cocoro-OS統合用インターフェース定義 (Phase 5)

cocoro-agentとしてcocoro-OSに統合する際の設定と能力一覧を定義する。
schema v7準拠。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CocoroAgentConfig:
    """cocoro-OS エージェント設定 (schema v7)

    cocoro-netネットワーク上のCORE_URLに接続し、
    worker/specialist としてジョブを受け取る。
    """

    # エージェント識別
    agent_type: str = "worker"
    agent_role: str = "specialist"

    # cocoro-OS接続情報
    cocoro_core_url: str = "http://192.168.50.92:8001"
    cocoro_api_key: str = "cocoro-2026"

    # スキーマ・ネットワーク
    schema_version: str = "v7"
    cocoro_net: str = "172.30.0.0/24"

    # エージェント能力一覧
    capabilities: list[str] = field(default_factory=lambda: [
        "generate_avatar",    # FLUX.2 + LoRA でアバター画像生成
        "generate_script",    # LLM (Gemini/Claude) で台本生成
        "pipeline_run",       # フルパイプライン実行 (台本→動画)
        "generate_video",     # Wan 2.6 I2V でシネマティック動画生成
        "generate_talking_head",  # EchoMimic でリップシンク動画生成
        "generate_voice",     # VOICEVOX で音声合成
        "health_check",       # ヘルスチェック
    ])

    # リソース情報
    gpu_vram_gb: int = 32     # RTX 5090 32GB
    gpu_model: str = "RTX 5090"
