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

// ④ カメラモーブ辞書 (クリックで cinematic_prompt に追記)
const CAMERA_MOVES: { label: string; prompt: string }[] = [
  { label: "🔍+ ズームイン",    prompt: "slow zoom in"               },
  { label: "🔍- ズームアウト",  prompt: "slow zoom out"              },
  { label: "← パン左",          prompt: "slow pan left"              },
  { label: "→ パン右",          prompt: "slow pan right"             },
  { label: "↑ ティルト上",      prompt: "tilt up slowly"             },
  { label: "↓ ティルト下",      prompt: "tilt down slowly"           },
  { label: "📌 固定",            prompt: "static camera"              },
  { label: "✨ スムーズ",       prompt: "cinematic smooth motion"    },
];

// ④ シーン別サンプルプロンプト
const SCENE_PRESETS: { category: string; icon: string; items: { label: string; prompt: string }[] }[] = [
  {
    category: "🏢 オフィス",
    icon: "🏢",
    items: [
      { label: "モダンオフィス",    prompt: "modern open office, glass walls, city view, soft daylight, professional, cinematic, slow zoom in" },
      { label: "エグゼクティブ",    prompt: "executive office, dark wood desk, bookshelf, warm ambient light, prestigious, cinematic smooth motion" },
      { label: "コワーキング",      prompt: "coworking space, industrial design, exposed brick, warm pendant lights, creative atmosphere, slow pan right" },
      { label: "夜のオフィス",      prompt: "night office, city lights background, blue hour, dramatic lighting, cinematic" },
    ],
  },
  {
    category: "🎙️ スタジオ",
    icon: "🎙️",
    items: [
      { label: "ニュースキャスター", prompt: "TV news studio, blue LED backdrop, professional lighting, clean background, static camera" },
      { label: "ポッドキャスト",    prompt: "podcast studio, acoustic panels, warm orange light, microphone visible, cozy atmosphere, static camera" },
      { label: "ホワイト背景",      prompt: "clean white studio background, soft box lighting, minimal, professional headshot style, static camera" },
      { label: "グラデーション",    prompt: "gradient dark blue to purple background, rim lighting, dramatic, product launch style, slow zoom in" },
    ],
  },
  {
    category: "🌿 屋外・自然",
    icon: "🌿",
    items: [
      { label: "都市・ビル街",      prompt: "urban cityscape, skyscrapers background, golden hour, bokeh, professional, slow pan left" },
      { label: "公園・緑",          prompt: "park, green trees, soft sunlight, natural bokeh background, relaxed atmosphere, cinematic smooth motion" },
      { label: "海辺・リゾート",    prompt: "seaside resort, ocean background, bright daylight, tropical, fresh atmosphere, slow zoom out" },
      { label: "山・自然",          prompt: "mountain landscape, clear sky, dramatic scenery, wide open space, inspiring, tilt up slowly" },
    ],
  },
  {
    category: "🏨 ホテル・ラグジュアリー",
    icon: "🏨",
    items: [
      { label: "ホテルロビー",      prompt: "luxury hotel lobby, marble floor, chandeliers, elegant atmosphere, warm lighting, slow pan right" },
      { label: "ラウンジ",          prompt: "high-end lounge, velvet sofa, ambient lighting, sophisticated, premium feel, cinematic smooth motion" },
      { label: "バンケット",        prompt: "hotel banquet hall, crystal chandelier, formal setting, prestigious event atmosphere, static camera" },
    ],
  },
  {
    category: "🏭 展示会・イベント",
    icon: "🏭",
    items: [
      { label: "展示ブース",        prompt: "trade show booth, product displays, colorful exhibits, professional event lighting, slow zoom in" },
      { label: "カンファレンス",    prompt: "conference hall, audience seats, stage lighting, professional event, cinematic" },
      { label: "ショールーム",      prompt: "modern showroom, product spotlights, clean minimal design, premium brand atmosphere, orbit around subject" },
    ],
  },
  {
    category: "💊 医療・クリニック",
    icon: "💊",
    items: [
      { label: "クリニック",        prompt: "clean medical clinic, white walls, professional lighting, trustworthy atmosphere, static camera" },
      { label: "研究室",            prompt: "laboratory, science equipment, blue-tinted lighting, innovative research atmosphere, slow zoom in" },
      { label: "ウェルネス",        prompt: "wellness center, soft lighting, calming atmosphere, plants, health and beauty spa, cinematic smooth motion" },
    ],
  },
  {
    category: "🍽️ 飲食・フード",
    icon: "🍽️",
    items: [
      { label: "レストラン",        prompt: "upscale restaurant interior, ambient lighting, elegant table setting, warm atmosphere, slow pan right" },
      { label: "カフェ",            prompt: "modern cafe, wooden decor, morning sunlight, cozy atmosphere, bokeh background, cinematic smooth motion" },
      { label: "キッチン",          prompt: "professional kitchen, stainless steel, bright lighting, clean and fresh, culinary setting, static camera" },
    ],
  },
  {
    category: "🎓 教育・研修",
    icon: "🎓",
    items: [
      { label: "教室・研修室",      prompt: "modern classroom, whiteboard background, educational setting, bright lighting, professional, static camera" },
      { label: "オンライン講座",    prompt: "minimal home studio, bookshelf background, ring light, clean and professional, slow zoom in" },
      { label: "セミナー",          prompt: "seminar room, presentation screen background, professional audience setting, cinematic smooth motion" },
    ],
  },
];


function SceneEditor({
  scenes,
  onChange,
}: {
  scenes: SceneItem[];
  onChange: (scenes: SceneItem[]) => void;
}) {
  const [showMoves, setShowMoves] = useState<Record<number, boolean>>({});
  const [showPresets, setShowPresets] = useState<Record<number, boolean>>({});
  const [selectedCategory, setSelectedCategory] = useState<Record<number, number>>({});

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

          {/* ③ 背景プロンプト + プリセット + カメラムーブ辞書 */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] font-bold text-[#4a6080] uppercase tracking-widest">🎬 背景・動きプロンプト</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowPresets(prev => ({ ...prev, [i]: !prev[i] }))}
                  className="text-[10px] text-emerald-400 hover:underline"
                >
                  {showPresets[i] ? "▲ 閉じる" : "🎥 カメラワークプリセット"}
                </button>
                <button
                  onClick={() => setShowMoves(prev => ({ ...prev, [i]: !prev[i] }))}
                  className="text-[10px] text-[#3d7eff] hover:underline"
                >
                  {showMoves[i] ? "▲ 閉じる" : "▼ カメラムーブ"}
                </button>
              </div>
            </div>

            {/* シーンプリセットピッカー */}
            {showPresets[i] && (
              <div className="mb-2 p-2 bg-[#080c14] rounded-lg border border-[#1f2d42] space-y-2 fade-in">
                <p className="text-[9px] text-[#4a6080]">カメラの動き方をプリセットから選択 → 背景はアバター写真のメラをそのまま使用します</p>
                {/* カテゴリタブ */}
                <div className="flex flex-wrap gap-1">
                  {SCENE_PRESETS.map((cat, ci) => (
                    <button key={ci}
                      onClick={() => setSelectedCategory(prev => ({ ...prev, [i]: ci }))}
                      className={`text-[10px] px-2 py-0.5 rounded-md transition-colors ${
                        (selectedCategory[i] ?? 0) === ci
                          ? "bg-emerald-600 text-white"
                          : "bg-[#0d1521] text-[#4a6080] hover:text-[#8ba0bc] border border-[#1f2d42]"
                      }`}>
                      {cat.icon} {cat.category.replace(/^[^\s]+\s/, "")}
                    </button>
                  ))}
                </div>
                {/* プリセットチップ */}
                <div className="flex flex-wrap gap-1.5">
                  {SCENE_PRESETS[selectedCategory[i] ?? 0]?.items.map((item, pi) => (
                    <button key={pi}
                      onClick={() => {
                        update(i, { cinematic_prompt: item.prompt });
                        setShowPresets(prev => ({ ...prev, [i]: false }));
                      }}
                      className="text-[10px] px-2 py-1 rounded-lg bg-[#0d1521] border border-emerald-800/50 text-emerald-300 hover:bg-emerald-900/30 hover:border-emerald-500 transition-all">
                      ✦ {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

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
