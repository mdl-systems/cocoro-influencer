"use client";

import { useState } from "react";
import { SceneItem } from "../types";

function ScriptGenerator({ onScriptReady }: { onScriptReady: (scenes: SceneItem[]) => void }) {
  const [open, setOpen] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [productName, setProductName] = useState("");
  const [target, setTarget] = useState("20代〜40代のビジネスパーソン");
  const [tone, setTone] = useState("プロフェッショナルで親しみやすい");
  const [duration, setDuration] = useState("60秒");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    if (!companyName || !productName) { alert("会社名と商品・サービス名を入力してください"); return; }
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/v1/pipeline/script/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: companyName,
          product_name: productName,
          target_audience: target,
          tone,
          duration,
          provider: "ollama",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      const scenes: SceneItem[] = (data.scenes ?? []).map((s: Record<string, string>) => ({
        id: Math.random().toString(36).slice(2),
        text: s.text ?? "",
        pose: (s.pose as SceneItem["pose"]) ?? "neutral",
        camera_angle: (s.camera_angle as SceneItem["camera_angle"]) ?? "upper_body",
        cinematic_prompt: s.cinematic_prompt ?? "modern office, professional lighting, cinematic",
      }));
      if (scenes.length === 0) throw new Error("台本シーンが生成されませんでした");
      onScriptReady(scenes);
      setOpen(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full py-2 rounded-xl text-sm font-medium text-violet-400 border border-violet-500/30 hover:border-violet-400 hover:bg-violet-500/10 transition-all"
      >
        AI で台本を自動生成 (Ollama / Qwen2.5:32b)
      </button>
    );
  }

  return (
    <div className="scene-card p-4 space-y-3 fade-in" style={{ borderColor: "rgba(139,92,246,0.4)" }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-violet-400 uppercase tracking-widest">AI 台本生成</span>
        <button onClick={() => setOpen(false)} className="text-xs text-[#4a6080] hover:text-[#8ba0bc]">閉じる</button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">会社名 *</label>
          <input value={companyName} onChange={e => setCompanyName(e.target.value)}
            placeholder="例: 株式会社サンプル"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
        </div>
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">商品・サービス名 *</label>
          <input value={productName} onChange={e => setProductName(e.target.value)}
            placeholder="例: AI動画生成サービス"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">トーン</label>
          <input value={tone} onChange={e => setTone(e.target.value)}
            placeholder="プロフェッショナルで親しみやすい"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
        </div>
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">尺・長さ</label>
          <select value={duration} onChange={e => setDuration(e.target.value)}
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-2 py-1.5 text-sm text-[#f0f6ff] transition-colors">
            <option value="30秒">30秒</option>
            <option value="60秒">60秒</option>
            <option value="90秒">90秒</option>
            <option value="120秒">120秒</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs text-[#4a6080] mb-1">ターゲット層</label>
        <input value={target} onChange={e => setTarget(e.target.value)}
          placeholder="20代〜40代のビジネスパーソン"
          className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
      </div>

      {error && <p className="text-xs text-red-400">エラー: {error}</p>}

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="w-full py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all text-white"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            Ollama (Qwen2.5:32b) で生成中...
          </span>
        ) : "台本を生成"}
      </button>
    </div>
  );
}

export default ScriptGenerator;
