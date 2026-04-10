"""台本生成テスト"""
import sys
sys.path.insert(0, "/home/cocoro-influencer")

from src.engines.script_engine import ScriptEngine
from pathlib import Path

engine = ScriptEngine(provider="ollama")
engine.load()

script = engine.generate(
    company_name="テスト株式会社",
    product_name="AIインフルエンサーシステム",
    target_audience="20代〜40代のビジネスパーソン",
    tone="プロフェッショナルで親しみやすい",
    duration="30秒",
    output_path=Path("outputs/test_script.json"),
)
print("台本生成成功!")
print(f"タイトル: {script.title}")
print(f"シーン数: {len(script.scenes)}")
for s in script.scenes:
    print(f"  [{s.scene_id}] {s.scene_type}: {s.text[:50]}...")
print(f"アバター: {script.avatar_prompt[:80]}...")
