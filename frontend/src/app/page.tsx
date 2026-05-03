"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Job, SceneItem, ScenePreset, QueueItem, QueueItemSettings } from "./types";
import AvatarUploadSection from "./components/AvatarUploadSection";
import SceneEditor from "./components/SceneEditor";
import ScriptGenerator from "./components/ScriptGenerator";
import SceneRegenerator from "./components/SceneRegenerator";
import PipelineRunner from "./components/PipelineRunner";
import JobHistory from "./components/JobHistory";
import VideoLibrary from "./components/VideoLibrary";
import PresetPanel from "./components/PresetPanel";
import QueueTab from "./components/QueueTab";

// DEFAULT_SCENE (SceneEditorでも定義済みだが StudioPage 初期化用に保持)
const DEFAULT_SCENE = (): SceneItem => ({
  id: Math.random().toString(36).slice(2),
  text: "",
  pose: "neutral",
  camera_angle: "upper_body",
  cinematic_prompt: "modern office, professional lighting, subtle movement, cinematic",
});

const DEFAULT_SETTINGS: QueueItemSettings = {
  outputFormat: "shorts",
  transition: "none",
  bgmName: null,
  bgmVolume: 0.12,
  enableSubtitles: false,
  modelId: 0,
  speakerId: 0,
  watermarkName: null,
  watermarkPosition: "bottom-right",
};

// ─────────────────────────── Main Page ───────────────────────

type Tab = "studio" | "scene" | "jobs" | "library" | "batch";

export default function StudioPage() {
  const [tab, setTab] = useState<Tab>("studio");
  const [customerName, setCustomerName] = useState("cocoro_customer");
  const [scenes, setScenes] = useState<SceneItem[]>([DEFAULT_SCENE()]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");

  // ── D-2 バッチキュー ──────────────────────────────────────────
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [addedFlash, setAddedFlash] = useState(false);

  const fetchJobs = useCallback(async () => {
    try {
      const [jobsRes, healthRes] = await Promise.all([
        fetch("/api/v1/jobs/"),
        fetch("/health"),
      ]);
      if (healthRes.ok) setApiStatus("online");
      if (jobsRes.ok) {
        const d = await jobsRes.json();
        setJobs(d.jobs ?? []);
      }
    } catch {
      setApiStatus("offline");
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    const id = setInterval(fetchJobs, 5000);
    return () => clearInterval(id);
  }, [fetchJobs]);

  const runningCount = jobs.filter(j => j.status === "running").length;
  const doneCount    = jobs.filter(j => j.status === "done").length;

  // 新しい動画を作成: 顧客名にタイムスタンプを付与してフレッシュな状態にする
  const handleNewVideo = () => {
    const ts = new Date().toISOString().slice(0,16).replace(/[-T:]/g, "").slice(0,12);
    const base = customerName.replace(/_\d{8,}$/, "");  // 既存タイムスタンプを除去
    setCustomerName(`${base}_${ts}`);
    setScenes([DEFAULT_SCENE()]);
    setTab("studio");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ── バッチキュー操作 ──────────────────────────────────────────
  const handleAddToQueue = (settings: QueueItemSettings) => {
    if (!customerName.trim()) { alert("顧客名を入力してください"); return; }
    if (scenes.some(s => !s.text.trim())) { alert("全シーンの台本を入力してください"); return; }

    const item: QueueItem = {
      id: Math.random().toString(36).slice(2),
      customerName,
      scenes: [...scenes],
      settings,
      addedAt: new Date().toISOString(),
      status: "pending",
      jobId: null,
      progress: 0,
      statusMsg: "待機中",
      videoUrl: null,
      errorMsg: null,
    };
    setQueue(prev => [...prev, item]);

    // フラッシュ演出
    setAddedFlash(true);
    setTimeout(() => setAddedFlash(false), 2000);

    // バッチタブに切り替え
    setTab("batch");
  };

  const handleQueueUpdate = (id: string, updates: Partial<QueueItem>) => {
    setQueue(prev => prev.map(i => i.id === id ? { ...i, ...updates } : i));
  };

  const handleClearDone = () => {
    setQueue(prev => prev.filter(i => i.status !== "done"));
  };

  const handleRemoveFromQueue = (id: string) => {
    setQueue(prev => prev.filter(i => i.id !== id));
  };

  // バッチキューの待機アイテム数
  const queuePending = queue.filter(i => i.status === "pending").length;
  const queueRunning = queue.filter(i => i.status === "running").length;

  return (
    <div className="min-h-screen">
      {/* ── Header ── */}
      <header className="sticky top-0 z-20 border-b border-[#1f2d42] bg-[#080c14]/90 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center text-lg shadow-lg shadow-violet-500/30">
              🤖
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight">COCORO Studio</h1>
              <p className="text-[10px] text-[#4a6080] leading-none">AI インフルエンサー動画生成</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Stats */}
            <div className="hidden sm:flex items-center gap-3 text-xs text-[#8ba0bc]">
              <span>📋 {jobs.length} jobs</span>
              {runningCount > 0 && (
                <span className="flex items-center gap-1 text-blue-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 pulse-dot" />
                  {runningCount} 実行中
                </span>
              )}
              <span className="text-emerald-400">✅ {doneCount} 完了</span>
              {/* バッチキュー状態 */}
              {(queuePending > 0 || queueRunning > 0) && (
                <span className="flex items-center gap-1 text-violet-400">
                  📋 Queue: {queuePending}待機 {queueRunning > 0 ? `/ ${queueRunning}実行中` : ""}
                </span>
              )}
            </div>

            {/* API Status */}
            <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
              apiStatus === "online"
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                : apiStatus === "offline"
                ? "bg-red-500/10 text-red-400 border-red-500/30"
                : "bg-gray-500/10 text-[#4a6080] border-[#1f2d42]"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${
                apiStatus === "online" ? "bg-emerald-400 pulse-dot" : "bg-red-400"
              }`} />
              API {apiStatus === "online" ? "オンライン" : apiStatus === "offline" ? "オフライン" : "確認中"}
            </span>
          </div>
        </div>

        {/* Tab bar */}
        <div className="max-w-6xl mx-auto px-6 flex gap-0 border-t border-[#1f2d42]">
          {([
            { key: "studio",  label: "🎬 スタジオ" },
            { key: "scene",   label: "♻️ シーン生成" },
            { key: "library", label: "📁 ライブラリ" },
            { key: "jobs",    label: `📋 ジョブ${jobs.length > 0 ? ` (${jobs.length})` : ""}` },
            {
              key: "batch",
              label: `🗂 バッチ${queue.length > 0 ? ` (${queue.length})` : ""}`,
              badge: addedFlash,
            },
          ] as { key: Tab; label: string; badge?: boolean }[]).map(({ key, label, badge }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`relative px-5 py-2.5 text-sm font-medium border-b-2 transition-all ${
                tab === key
                  ? "border-[#3d7eff] text-[#f0f6ff]"
                  : "border-transparent text-[#4a6080] hover:text-[#8ba0bc]"
              }`}
            >
              {label}
              {badge && (
                <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
              )}
            </button>
          ))}
        </div>
      </header>

      {/* ── Main ── */}
      <main className="max-w-6xl mx-auto px-6 py-8">

        {/* ─ STUDIO TAB ─ */}
        {tab === "studio" && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-6 items-start">

            {/* Left: Config */}
            <div className="space-y-6">

              {/* 顧客設定 */}
              <section className="glass p-6 space-y-4 fade-in">
                <h2 className="text-sm font-bold text-[#8ba0bc] uppercase tracking-widest">
                  顧客設定
                </h2>
                <div>
                  <label className="block text-xs font-medium text-[#4a6080] mb-1.5">
                    顧客名 / プロジェクト名
                  </label>
                  <input
                    type="text"
                    value={customerName}
                    onChange={e => setCustomerName(e.target.value)}
                    placeholder="例: sample_company"
                    className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-xl px-4 py-2.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors"
                  />
                </div>

                <div>
                  <h3 className="text-xs font-medium text-[#4a6080] mb-3">
                    📷 キャラクター画像アップロード
                  </h3>
                  <AvatarUploadSection
                    customerName={customerName}
                    onUploaded={fetchJobs}
                  />
                </div>
              </section>

              {/* 台本エディタ */}
              <section className="glass p-6 space-y-4 fade-in">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-[#8ba0bc] uppercase tracking-widest">
                    台本エディタ
                  </h2>
                  <span className="text-xs text-[#4a6080]">{scenes.length} シーン</span>
                </div>
                <ScriptGenerator onScriptReady={setScenes} />
                <SceneEditor scenes={scenes} onChange={setScenes} />
              </section>
            </div>

            {/* Right: Run + Status */}
            <div className="space-y-4 lg:sticky lg:top-[105px] fade-in">
              <section className="glass p-6 space-y-5">
                <h2 className="text-sm font-bold text-[#8ba0bc] uppercase tracking-widest">
                  🚀 動画生成
                </h2>

                {/* Summary */}
                <div className="bg-[#080c14] rounded-xl p-4 space-y-2 text-xs text-[#8ba0bc]">
                  <div className="flex justify-between">
                    <span>顧客名</span>
                    <span className="text-[#f0f6ff] font-medium">{customerName || "未設定"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>シーン数</span>
                    <span className="text-[#f0f6ff] font-medium">{scenes.length} シーン</span>
                  </div>
                  <div className="flex justify-between">
                    <span>出力フォーマット</span>
                    <span className="text-[#f0f6ff] font-medium">shorts (480x832 / 16fps)</span>
                  </div>
                  <div className="flex justify-between">
                    <span>推定時間</span>
                    <span className="text-amber-400 font-medium">約 {scenes.length * 15}〜{scenes.length * 25} 分</span>
                  </div>
                </div>

                <PipelineRunner
                  customerName={customerName}
                  scenes={scenes}
                  onGoToLibrary={() => setTab("library")}
                  onNewVideo={handleNewVideo}
                  onAddToQueue={handleAddToQueue}
                />
              </section>
            </div>
          </div>
        )}

        {/* ─ SCENE TAB ─ */}
        {tab === "scene" && (
          <div className="max-w-2xl mx-auto fade-in">
            <section className="glass p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-[#8ba0bc] uppercase tracking-widest">♻️ シーン個別生成</h2>
                <span className="text-xs text-[#4a6080]">{scenes.length} シーン</span>
              </div>
              <div className="bg-[#080c14] rounded-xl p-3 text-xs text-[#4a6080] space-y-1">
                <p>・アバター画像生成をスキップし、音声 → Wan2.1 → Wav2Lip のみ実行</p>
                <p>・既存のInstantID生成済み画像を使用（アップロード済みが前提）</p>
                <p>・シーンごとに独立実行。完了後にプレビュー動画で確認できます</p>
              </div>
              <SceneRegenerator customerName={customerName} scenes={scenes} />
            </section>
          </div>
        )}

        {/* ─ JOBS TAB ─ */}
        {tab === "jobs" && (
          <div className="space-y-4 fade-in">
            {/* Stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "総ジョブ",  value: jobs.length,    icon: "📋", color: "from-violet-500 to-indigo-500" },
                { label: "実行中",    value: runningCount,   icon: "⚡", color: "from-blue-500 to-cyan-500"   },
                { label: "完了",      value: doneCount,      icon: "✅", color: "from-emerald-500 to-teal-500" },
                { label: "エラー",    value: jobs.filter(j => j.status === "error").length, icon: "❌", color: "from-red-500 to-rose-500" },
              ].map(c => (
                <div key={c.label} className="glass p-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xl">{c.icon}</span>
                    <span className={`text-2xl font-bold bg-gradient-to-r ${c.color} bg-clip-text text-transparent`}>{c.value}</span>
                  </div>
                  <p className="text-xs text-[#4a6080]">{c.label}</p>
                </div>
              ))}
            </div>

            <div className="glass overflow-hidden">
              <div className="px-6 py-3.5 border-b border-[#1f2d42] flex items-center justify-between">
                <h2 className="text-sm font-semibold">ジョブ履歴</h2>
                <button
                  onClick={fetchJobs}
                  className="text-xs text-[#4a6080] hover:text-[#8ba0bc] transition-colors"
                >
                  🔄 更新
                </button>
              </div>
              <JobHistory jobs={jobs} loading={loadingJobs} />
            </div>
          </div>
        )}

        {/* ─ LIBRARY TAB ─ */}
        {tab === "library" && (
          <div className="fade-in">
            <VideoLibrary />
          </div>
        )}

        {/* ─ BATCH TAB ─ */}
        {tab === "batch" && (
          <div className="fade-in">
            {/* バッチヘッダー */}
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-base font-bold text-[#f0f6ff]">🗂 バッチキュー</h2>
                <p className="text-xs text-[#4a6080] mt-0.5">複数の顧客・台本を連続して自動生成します</p>
              </div>
              <button
                onClick={() => setTab("studio")}
                className="filter-chip flex items-center gap-1.5"
              >
                ➕ スタジオで台本を追加
              </button>
            </div>

            {/* バッチキュー本体 (BatchRunner + QueueTab) */}
            <QueueTab
              queue={queue}
              onUpdate={handleQueueUpdate}
              onClearDone={handleClearDone}
              onRemove={handleRemoveFromQueue}
            />
          </div>
        )}
      </main>
    </div>
  );
}
