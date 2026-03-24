"""cocoro-OS統合用インターフェース定義

Phase 5で実装予定。現時点ではインターフェース定義のみ。
cocoro-agentとしてcocoro-OSに統合する際に使用する。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CocoroAgentConfig:
    """cocoro-OS エージェント設定"""

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
        "generate_avatar",
        "generate_video",
        "generate_talking_head",
        "publish_content",
    ])
