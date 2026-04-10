"""Ollama接続テスト"""
import sys
sys.path.insert(0, "/home/cocoro-influencer")

from src.engines.script_engine import ScriptEngine

engine = ScriptEngine(provider="ollama")
engine.load()
print("Ollama接続OK!")
print(f"  model: {engine._model}")
print(f"  base_url: {engine._base_url}")
