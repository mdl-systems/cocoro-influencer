"use client";

import { useState } from "react";
import { SceneItem } from "../types";

const DEFAULT_SCENE: () => SceneItem = () => ({
  id: Math.random().toString(36).slice(2),
  text: "",
  pose: "neutral",
  camera_angle: "upper_body",
  cinematic_prompt: "modern office, professional lighting, subtle movement, cinematic",
});

// ① カメラ構図オプション
const CAMERA_OPTIONS: { value: SceneItem["camera_angle"]; icon: string; label: string; sub: string }[] = [
  { value: "close_up",   icon: "👤", label: "顔アップ",   sub: "Close-up"   },
  { value: "upper_body", icon: "🧑", label: "上半身",      sub: "Upper body" },
  { value: "full_body",  icon: "🚶", label: "全身",        sub: "Full body"  },
];

// ② ポーズオプション (7種)
const POSE_OPTIONS: { value: SceneItem["pose"]; icon: string; label: string }[] = [
  { value: "neutral",    icon: "😐", label: "通常"     },
  { value: "talking",    icon: "🗣",  label: "話す"     },
  { value: "greeting",   icon: "👋", label: "挨拶"     },
  { value: "presenting", icon: "📋", label: "プレゼン" },
  { value: "thinking",   icon: "🤔", label: "思考"     },
  { value: "walk",       icon: "🚶", label: "歩き"     },
  { value: "pointing",   icon: "☝️", label: "指差し"   },
];

// ③ カメラムーブ辞書 (クリックで cinematic_prompt に追記)
const CAMERA_MOVES: { label: string; prompt: string }[] = [
  { label: "🔍+ ズームイン",    prompt: "slow zoom in"               },
  { label: "🔍- ズームアウト",  prompt: "slow zoom out"              },
  { label: "← パン左",          prompt: "slow pan left"              },
  { label: "→ パン右",          prompt: "slow pan right"             },
  { label: "↑ ティルト上",      prompt: "tilt up slowly"             },
  { label: "↓ ティルト下",      prompt: "tilt down slowly"           },
  { label: "🔄 オービット",     prompt: "orbit around subject"       },
  { label: "📌 固定",            prompt: "static camera"              },
  { label: "🎬 手持ち",         prompt: "handheld camera, slight shake" },
  { label: "✨ スムーズ",       prompt: "cinematic smooth motion"    },
];

function SceneEditor({
  scenes,
  onChange,
}: {
  scenes: SceneItem[];
  onChange: (scenes: SceneItem[]) => void;
}) {
  const [showMoves, setShowMoves] = useState<Record<number, boolean>>({});

  const update = (idx: number, patch: Partial<SceneItem>) => {
    const next = scenes.map((s, i) => (i === idx ? { ...s, ...patch } : s));
    onChange(next);
  };
  const remove = (idx: number) => onChange(scenes.filter((_, i) => i !== idx));
  const add = () => onChange([...scenes, DEFAULT_SCENE()]);

  const appendMove = (idx: number, promptSnippet: string) => {
    const cur = scenes[idx].cinematic_prompt;
    const base = cur.replace(/, ?(slow zoom in|slow zoom out|slow pan left|slow pan right|tilt up slowly|tilt down slowly|orbit around subject|static camera|handheld camera, slight shake|cinematic smooth motion)/g, "").trim();
    update(idx, { cinematic_prompt: base ? `${base}, ${promptSnippet}` : promptSnippet });
  };

  return (
    <div className="space-y-3">
      {scenes.map((scene, i) => (
        <div key={scene.id} className="scene-card p-4 space-y-4 fade-in">

          {/* ── Header ── */}
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#4a6080] uppercase tracking-widest">Scene {i + 1}</span>
            {scenes.length > 1 && (
              <button onClick={() => remove(i)}
                className="text-xs text-red-400 hover:text-red-300 transition-colors px-2 py-0.5 rounded hover:bg-red-500/10">
                🗑️ 削除
              </button>
            )}
          </div>

          {/* ── 台本テキスト ── */}
          <textarea
            rows={3}
            value={scene.text}
            onChange={(e) => update(i, { text: e.target.value })}
            placeholder="台本テキストを入力... (AIが音声を合成します)"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-3 py-2 text-sm text-[#f0f6ff] placeholder-[#4a6080] resize-none transition-colors"
          />

          {/* ① カメラ構図アイコン選択 */}
          <div>
            <label className="block text-[10px] font-bold text-[#4a6080] uppercase tracking-widest mb-2">📷 カメラ構図</label>
            <div className="flex gap-1.5">
              {CAMERA_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => update(i, { camera_angle: opt.value })}
                  className={`option-card ${scene.camera_angle === opt.value ? "selected" : ""}`}
                >
                  <span className="text-xl leading-none">{opt.icon}</span>
                  <span className="text-[10px] font-semibold text-[#f0f6ff] leading-tight">{opt.label}</span>
                  <span className="text-[9px] text-[#4a6080] leading-tight">{opt.sub}</span>
                </button>
              ))}
            </div>
          </div>

          {/* ② ポーズアイコン選択 (7種) */}
          <div>
            <label className="block text-[10px] font-bold text-[#4a6080] uppercase tracking-widest mb-2">🕺 ポーズ</label>
            <div className="flex flex-wrap gap-1.5">
              {POSE_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => update(i, { pose: opt.value })}
                  className={`option-card ${scene.pose === opt.value ? "selected" : ""}`}
                  style={{ minWidth: "52px", maxWidth: "72px" }}
                >
                  <span className="text-lg leading-none">{opt.icon}</span>
                  <span className="text-[10px] font-semibold text-[#f0f6ff] leading-tight">{opt.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* ③ 背景プロンプト + カメラムーブ辞書 */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] font-bold text-[#4a6080] uppercase tracking-widest">🎬 背景・動きプロンプト</label>
              <button
                onClick={() => setShowMoves(prev => ({ ...prev, [i]: !prev[i] }))}
                className="text-[10px] text-[#3d7eff] hover:underline"
              >
                {showMoves[i] ? "▲ 閉じる" : "▼ カメラムーブ辞書"}
              </button>
            </div>
            <input
              type="text"
              value={scene.cinematic_prompt}
              onChange={(e) => update(i, { cinematic_prompt: e.target.value })}
              placeholder="modern office, professional lighting..."
              className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-3 py-1.5 text-xs text-[#f0f6ff] placeholder-[#4a6080] transition-colors mb-1.5"
            />
            {/* カメラムーブ辞書チップ */}
            {showMoves[i] && (
              <div className="flex flex-wrap gap-1.5 fade-in p-2 bg-[#080c14] rounded-lg border border-[#1f2d42]">
                <p className="w-full text-[9px] text-[#4a6080] mb-0.5">クリックでプロンプトに追加 →</p>
                {CAMERA_MOVES.map(m => (
                  <button key={m.prompt} onClick={() => appendMove(i, m.prompt)} className="cam-chip">
                    {m.label}
                  </button>
                ))}
              </div>
            )}
          </div>

        </div>
      ))}

      <button
        onClick={add}
        className="w-full py-2 rounded-xl text-sm font-medium text-[#3d7eff] border border-[#1f2d42] hover:border-[#3d7eff] hover:bg-[#3d7eff]/10 transition-all"
      >
        + シーンを追加
      </button>
    </div>
  );
}

export default SceneEditor;
