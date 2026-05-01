"use client";

import { useState } from "react";
import { SceneItem, ScenePreset } from "../types";

// ─────────────────────────── D-1 PresetPanel ───────────────
const PRESET_KEY = "cocoro_presets";

function PresetPanel({
  customerName,
  scenes,
  onLoad,
}: {
  customerName: string;
  scenes: SceneItem[];
  onLoad: (preset: ScenePreset) => void;
}) {
  const [presets, setPresets] = useState<ScenePreset[]>(() => {
    try { return JSON.parse(localStorage.getItem(PRESET_KEY) || "[]"); }
    catch { return []; }
  });
  const [open, setOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);

  const save = () => {
    if (!saveName.trim()) { alert("プリセット名を入力してください"); return; }
    const preset: ScenePreset = {
      id: crypto.randomUUID(),
      name: saveName.trim(),
      createdAt: new Date().toISOString(),
      customerName,
      scenes: JSON.parse(JSON.stringify(scenes)),
    };
    const updated = [preset, ...presets].slice(0, 20);
    setPresets(updated);
    localStorage.setItem(PRESET_KEY, JSON.stringify(updated));
    setSaveName("");
    setSaving(false);
  };

  const del = (id: string) => {
    const updated = presets.filter(p => p.id !== id);
    setPresets(updated);
    localStorage.setItem(PRESET_KEY, JSON.stringify(updated));
  };

  return (
    <div className="glass p-4 space-y-3 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-[#8ba0bc] uppercase tracking-widest">💾 プリセット</span>
        <button onClick={() => setOpen(v => !v)} className="text-xs text-[#4a6080] hover:text-[#8ba0bc] transition-colors">
          {open ? "▲ 閉じる" : `▼ ${presets.length > 0 ? `${presets.length}件保存中` : "保存なし"}`}
        </button>
      </div>

      {saving ? (
        <div className="flex gap-2">
          <input
            autoFocus value={saveName} onChange={e => setSaveName(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") save(); if (e.key === "Escape") setSaving(false); }}
            placeholder="プリセット名を入力..."
            className="flex-1 bg-[#080c14] border border-[#1f2d42] focus:border-emerald-500 outline-none rounded-lg px-3 py-1.5 text-xs text-[#f0f6ff] placeholder-[#4a6080]"
          />
          <button onClick={save} className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold">保存</button>
          <button onClick={() => setSaving(false)} className="px-3 py-1.5 rounded-lg bg-[#1f2d42] text-[#8ba0bc] text-xs">✕</button>
        </div>
      ) : (
        <button onClick={() => setSaving(true)}
          className="w-full py-2 rounded-lg text-xs font-semibold border border-dashed border-[#1f2d42] hover:border-emerald-500/50 text-[#4a6080] hover:text-emerald-400 transition-all">
          + 現在の設定をプリセット保存
        </button>
      )}

      {open && (
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {presets.length === 0 && <p className="text-xs text-[#4a6080] text-center py-4">保存済みプリセットはありません</p>}
          {presets.map(p => (
            <div key={p.id} className="flex items-center gap-2 bg-[#080c14] rounded-lg px-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-[#f0f6ff] truncate">{p.name}</p>
                <p className="text-[10px] text-[#4a6080]">
                  {p.customerName} · {p.scenes.length}シーン · {new Date(p.createdAt).toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
              <button onClick={() => { onLoad(p); setOpen(false); }}
                className="text-xs px-2 py-1 rounded bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 transition-all shrink-0">
                読込
              </button>
              <button onClick={() => del(p.id)}
                className="text-xs px-2 py-1 rounded bg-red-600/10 hover:bg-red-600/30 text-red-400 border border-red-500/20 transition-all shrink-0">
                削除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default PresetPanel;
