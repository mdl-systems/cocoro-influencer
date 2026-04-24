"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ─────────────────────────── Types ───────────────────────────

interface VideoItem {
  id: string;
  url: string;
  filename: string;
  customer_name: string;
  size_bytes: number;
  created_at: string;
  is_final: boolean;
}

interface Job {
  id: number;
  job_type: string;
  status: "pending" | "running" | "done" | "error" | "waiting_for_approval";
  params: string | null;
  output_path: string | null;
  error_message: string | null;
  progress: number | null;
  status_message: string | null;
  approval_stage: string | null;
  preview_url: string | null;
  created_at: string;
  updated_at: string;
}

interface SceneItem {
  id: string;
  text: string;
  pose: "neutral" | "greeting" | "walk";
  camera_angle: "upper_body" | "full_body" | "close_up";
  cinematic_prompt: string;
}

interface SceneJobState {
  jobId: number | null;
  status: "idle" | "running" | "done" | "error";
  progress: number;
  statusMsg: string;
  previewUrl: string | null;
}

// ─────────────────────────── Constants ───────────────────────

const JOB_TYPE_LABELS: Record<string, string> = {
  avatar:       "🎨 アバター生成",
  voice:        "🎤 音声合成",
  talking_head: "🗣️ トーキングヘッド",
  cinematic:    "🎬 シネマティック",
  compose:      "✂️ 動画合成",
  pipeline:     "🚀 フルパイプライン",
  instantid:    "🧬 InstantID",
};

const STATUS_STYLE: Record<string, string> = {
  pending:              "bg-amber-500/10 text-amber-300 border-amber-500/30",
  running:              "bg-blue-500/10 text-blue-300 border-blue-500/30",
  done:                 "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  error:                "bg-red-500/10 text-red-300 border-red-500/30",
  waiting_for_approval: "bg-violet-500/10 text-violet-300 border-violet-500/30",
};

// ─────────────────────────── Sub-components ──────────────────

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${STATUS_STYLE[status] ?? "bg-gray-500/10 text-gray-300 border-gray-500/30"}`}>
      {status === "running" && <span className="w-1.5 h-1.5 rounded-full bg-blue-400 pulse-dot" />}
      {status === "pending" && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
      {status === "done"    && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
      {status === "error"   && <span className="w-1.5 h-1.5 rounded-full bg-red-400" />}
      {status}
    </span>
  );
}

function ProgressBar({ value, label, running }: { value: number; label?: string; running?: boolean }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center text-xs text-[#8ba0bc]">
        <span className="truncate max-w-[70%]">{label || "処理中..."}</span>
        <span className="font-mono font-bold text-[#f0f6ff] ml-2">{value}%</span>
      </div>
      <div className="h-2.5 rounded-full bg-[#1a2236] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${running && value < 100 ? "progress-shimmer" : "bg-gradient-to-r from-blue-500 to-violet-500"}`}
          style={{ width: `${Math.max(value, 2)}%` }}
        />
      </div>
    </div>
  );
}

// ─────────────────────────── DropZone ────────────────────────

function DropZone({
  label,
  sublabel,
  accent,
  onChange,
  preview,
}: {
  label: string;
  sublabel: string;
  accent: string;
  onChange: (file: File) => void;
  preview?: string | null;
}) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDrag(false);
      const file = e.dataTransfer.files[0];
      if (file) onChange(file);
    },
    [onChange]
  );

  return (
    <div
      className={`drop-zone rounded-xl p-4 cursor-pointer select-none text-center ${drag ? "active" : ""}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onChange(f); }}
      />
      {preview ? (
        <img src={preview} alt="preview" className="w-full h-32 object-cover rounded-lg mb-2" />
      ) : (
        <div className="text-4xl mb-2">📷</div>
      )}
      <p className={`text-sm font-semibold ${accent}`}>{label}</p>
      <p className="text-xs text-[#4a6080] mt-0.5">{sublabel}</p>
    </div>
  );
}

// ─────────────────────────── Avatar Upload Section ───────────

function AvatarUploadSection({
  customerName,
  onUploaded,
}: {
  customerName: string;
  onUploaded: () => void;
}) {
  const [faceFile, setFaceFile] = useState<File | null>(null);
  const [fbFile, setFbFile] = useState<File | null>(null);
  const [facePreview, setFacePreview] = useState<string | null>(null);
  const [fbPreview, setFbPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [pollStatus, setPollStatus] = useState<string>("");
  const [pollProgress, setPollProgress] = useState<number>(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const previewFile = (file: File, setter: (url: string) => void) => {
    const r = new FileReader();
    r.onload = (e) => setter(e.target?.result as string);
    r.readAsDataURL(file);
  };

  const handleFace = (f: File) => { setFaceFile(f); previewFile(f, setFacePreview); };
  const handleFb   = (f: File) => { setFbFile(f);   previewFile(f, setFbPreview);   };

  const stopPoll = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };

  const startPoll = useCallback((jid: number) => {
    stopPoll();
    let count = 0;
    pollRef.current = setInterval(async () => {
      count++;
      if (count > 480) { stopPoll(); setPollStatus("⏰ タイムアウト (80分)"); return; }
      try {
        const res = await fetch(`/api/v1/jobs/${jid}`);
        const d: Job = await res.json();
        if (d.status === "done") {
          stopPoll();
          setPollProgress(100);
          setPollStatus("🎉 InstantIDポーズ画像の生成が完了しました！");
          onUploaded();
        } else if (d.status === "error") {
          stopPoll();
          setPollStatus(`❌ エラー: ${d.error_message || "詳細はログを確認"}`);
        } else {
          setPollProgress(d.progress ?? 0);
          setPollStatus(d.status_message ? `⏳ ${d.status_message}` : `⏳ InstantIDポーズ生成中 (job#${jid})`);
        }
      } catch { /* network error, keep polling */ }
    }, 10000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onUploaded]);

  useEffect(() => () => stopPoll(), []);

  const handleUpload = async () => {
    if (!customerName) { alert("先に顧客名を入力してください"); return; }
    if (!faceFile)    { alert("顔写真を選択してください"); return; }
    setUploading(true);
    setPollStatus("アップロード中...");
    const fd = new FormData();
    fd.append("file", faceFile);
    if (fbFile) fd.append("fullbody_file", fbFile);
    try {
      const res = await fetch(`/api/v1/avatars/upload?customer_name=${encodeURIComponent(customerName)}`, {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) { setPollStatus(`❌ ${JSON.stringify(data)}`); return; }
      if (data.job_id) {
        setJobId(data.job_id);
        setPollStatus(`✅ 保存完了 → InstantID生成開始 (job#${data.job_id})`);
        startPoll(data.job_id);
      } else {
        setPollStatus("✅ " + (data.message || "アップロード完了"));
        onUploaded();
      }
    } catch (e) {
      setPollStatus(`❌ ネットワークエラー: ${e}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <DropZone
          label="顔写真（必須）"
          sublabel="正面・クローズアップ推奨"
          accent="text-yellow-400"
          onChange={handleFace}
          preview={facePreview}
        />
        <DropZone
          label="全身写真（推奨）"
          sublabel="頭〜足まで全体"
          accent="text-blue-400"
          onChange={handleFb}
          preview={fbPreview}
        />
      </div>

      <button
        onClick={handleUpload}
        disabled={uploading || !faceFile}
        className="w-full py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.98] text-white"
      >
        {uploading ? "アップロード中..." : "📤 アップロード & InstantID生成"}
      </button>

      {pollStatus && (
        <div className="space-y-2 fade-in">
          <p className="text-xs text-[#8ba0bc]">{pollStatus}</p>
          {jobId && pollProgress > 0 && pollProgress < 100 && (
            <ProgressBar value={pollProgress} running label="InstantIDポーズ生成" />
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Scene Editor ────────────────────

const DEFAULT_SCENE: () => SceneItem = () => ({
  id: Math.random().toString(36).slice(2),
  text: "",
  pose: "neutral",
  camera_angle: "upper_body",
  cinematic_prompt: "modern office, professional lighting, subtle movement, cinematic",
});

function SceneEditor({
  scenes,
  onChange,
}: {
  scenes: SceneItem[];
  onChange: (scenes: SceneItem[]) => void;
}) {
  const update = (idx: number, patch: Partial<SceneItem>) => {
    const next = scenes.map((s, i) => (i === idx ? { ...s, ...patch } : s));
    onChange(next);
  };
  const remove = (idx: number) => onChange(scenes.filter((_, i) => i !== idx));
  const add = () => onChange([...scenes, DEFAULT_SCENE()]);

  return (
    <div className="space-y-3">
      {scenes.map((scene, i) => (
        <div key={scene.id} className="scene-card p-4 space-y-3 fade-in">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#4a6080] uppercase tracking-widest">
              Scene {i + 1}
            </span>
            {scenes.length > 1 && (
              <button
                onClick={() => remove(i)}
                className="text-xs text-red-400 hover:text-red-300 transition-colors px-2 py-0.5 rounded hover:bg-red-500/10"
              >
                🗑️ 削除
              </button>
            )}
          </div>

          <textarea
            rows={3}
            value={scene.text}
            onChange={(e) => update(i, { text: e.target.value })}
            placeholder="台本テキストを入力... (AIが音声を合成します)"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-3 py-2 text-sm text-[#f0f6ff] placeholder-[#4a6080] resize-none transition-colors"
          />

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-[#4a6080] mb-1">ポーズ</label>
              <select
                value={scene.pose}
                onChange={(e) => update(i, { pose: e.target.value as SceneItem["pose"] })}
                className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-2 py-1.5 text-xs text-[#f0f6ff] transition-colors"
              >
                <option value="neutral">neutral (通常)</option>
                <option value="greeting">greeting (挨拶)</option>
                <option value="walk">walk (歩き)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-[#4a6080] mb-1">カメラ構図</label>
              <select
                value={scene.camera_angle}
                onChange={(e) => update(i, { camera_angle: e.target.value as SceneItem["camera_angle"] })}
                className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-2 py-1.5 text-xs text-[#f0f6ff] transition-colors"
              >
                <option value="upper_body">上半身</option>
                <option value="full_body">全身</option>
                <option value="close_up">顔アップ</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs text-[#4a6080] mb-1">背景プロンプト</label>
            <input
              type="text"
              value={scene.cinematic_prompt}
              onChange={(e) => update(i, { cinematic_prompt: e.target.value })}
              placeholder="modern office, professional lighting..."
              className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-3 py-1.5 text-xs text-[#f0f6ff] placeholder-[#4a6080] transition-colors"
            />
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

// ──────────────────────────── AI 台本生成 ─────────────────────

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
      const params = new URLSearchParams({
        company_name: companyName,
        product_name: productName,
        target_audience: target,
        tone,
        duration,
        provider: "ollama",
      });
      const res = await fetch(`/api/v1/pipeline/script/generate?${params}`, { method: "POST" });
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


// ─────────────────────────── Scene Regenerator ───────────

function SceneRegenerator({
  customerName,
  scenes,
}: {
  customerName: string;
  scenes: SceneItem[];
}) {
  const [sceneJobs, setSceneJobs] = useState<Record<number, SceneJobState>>({});
  const pollRefs = useRef<Record<number, ReturnType<typeof setInterval>>>({});

  const stopPoll = (idx: number) => {
    if (pollRefs.current[idx]) {
      clearInterval(pollRefs.current[idx]);
      delete pollRefs.current[idx];
    }
  };

  useEffect(() => () => Object.keys(pollRefs.current).forEach(k => clearInterval(pollRefs.current[Number(k)])), []);

  const startPoll = (idx: number, jobId: number) => {
    stopPoll(idx);
    let count = 0;
    pollRefs.current[idx] = setInterval(async () => {
      count++;
      if (count > 360) { // 30分タイムアウト
        stopPoll(idx);
        setSceneJobs(prev => ({ ...prev, [idx]: { ...prev[idx], status: "error", statusMsg: "⏰ タイムアウト" } }));
        return;
      }
      try {
        const res = await fetch(`/api/v1/jobs/${jobId}`);
        const d: Job = await res.json();
        if (d.status === "done") {
          stopPoll(idx);
          let url: string | null = null;
          if (d.output_path) {
            url = d.output_path.replace("/data/outputs/", "/outputs/") + "?t=" + Date.now();
          }
          setSceneJobs(prev => ({ ...prev, [idx]: { jobId, status: "done", progress: 100, statusMsg: "✅ 完了", previewUrl: url } }));
        } else if (d.status === "error") {
          stopPoll(idx);
          setSceneJobs(prev => ({ ...prev, [idx]: { jobId, status: "error", progress: 0, statusMsg: `❌ ${d.error_message || "エラー"}`, previewUrl: null } }));
        } else {
          setSceneJobs(prev => ({ ...prev, [idx]: { ...prev[idx], progress: d.progress ?? 0, statusMsg: d.status_message ?? "生成中..." } }));
        }
      } catch { /* keep polling */ }
    }, 5000);
  };

  const handleRegenerate = async (idx: number) => {
    if (!customerName) { alert("顧客名を入力してください"); return; }
    const scene = scenes[idx];
    if (!scene?.text.trim()) { alert(`Scene ${idx + 1} の台本を入力してください`); return; }

    setSceneJobs(prev => ({ ...prev, [idx]: { jobId: null, status: "running", progress: 0, statusMsg: "ジョブ送信中...", previewUrl: null } }));

    try {
      const res = await fetch("/api/v1/pipeline/scene/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: customerName,
          scene_index: idx,
          text: scene.text,
          pose: scene.pose,
          camera_angle: scene.camera_angle,
          cinematic_prompt: scene.cinematic_prompt || "modern office, professional lighting, cinematic",
          appearance_prompt: "",
          scene_type: "talking_head",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      const jobId: number = data.job_id;
      setSceneJobs(prev => ({ ...prev, [idx]: { ...prev[idx], jobId, statusMsg: `ジョブ #${jobId} 実行中...` } }));
      startPoll(idx, jobId);
    } catch (e: unknown) {
      setSceneJobs(prev => ({ ...prev, [idx]: { jobId: null, status: "error", progress: 0, statusMsg: `❌ ${e instanceof Error ? e.message : String(e)}`, previewUrl: null } }));
    }
  };

  if (scenes.length === 0) {
    return <p className="text-sm text-[#4a6080] text-center py-8">まずスタジオタブでシーンを追加してください</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-[#4a6080]">各シーンを個別に生成できます。全体パイプラインとは独立して実行されます。</p>
      {scenes.map((scene, idx) => {
        const job = sceneJobs[idx];
        const isRunning = job?.status === "running";
        return (
          <div key={scene.id} className={`scene-card p-4 space-y-3 ${
            isRunning ? "border-blue-500/50 shadow-blue-500/10 shadow-lg" :
            job?.status === "done" ? "border-emerald-500/50" :
            job?.status === "error" ? "border-red-500/50" : ""
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-[#4a6080] uppercase tracking-widest">Scene {idx + 1}</span>
                {job?.status === "running"  && <span className="text-xs text-blue-400 animate-pulse">⏳ 生成中</span>}
                {job?.status === "done"     && <span className="text-xs text-emerald-400">✅ 完了</span>}
                {job?.status === "error"    && <span className="text-xs text-red-400">❌ エラー</span>}
                {job?.jobId && <span className="text-xs text-[#4a6080]">job#{job.jobId}</span>}
              </div>
              <button
                onClick={() => handleRegenerate(idx)}
                disabled={isRunning}
                className="text-xs font-semibold px-3 py-1 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 hover:border-indigo-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                ♻️ 単体生成
              </button>
            </div>

            {/* 台本プレビュー */}
            <p className="text-xs text-[#8ba0bc] line-clamp-2">{scene.text || <span className="text-[#4a6080] italic">台本未入力</span>}</p>

            {/* 進捗バー */}
            {job && job.status !== "idle" && (
              <div className="space-y-2">
                <ProgressBar
                  value={job.progress}
                  label={job.statusMsg}
                  running={isRunning}
                />

                {/* 完了プレビュー */}
                {job.status === "done" && job.previewUrl && (
                  <div className="mt-2 rounded-xl overflow-hidden border border-emerald-500/30 bg-black flex justify-center fade-in">
                    <video
                      src={job.previewUrl}
                      controls
                      autoPlay
                      loop
                      muted
                      className="max-h-64 w-auto"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PipelineRunner({
  customerName,
  scenes,
  onGoToLibrary,
  onNewVideo,
}: {
  customerName: string;
  scenes: SceneItem[];
  onGoToLibrary?: () => void;
  onNewVideo?: () => void;
}) {
  const [jobId, setJobId] = useState<number | null>(null);
  const [status, setStatus] = useState<Job["status"] | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [approvalStage, setApprovalStage] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef<number>(0);

  const stopAll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  };
  useEffect(() => () => stopAll(), []);

  const startPoll = useCallback((jid: number) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/v1/jobs/${jid}`);
        const d: Job = await res.json();
        setProgress(d.progress ?? 0);
        setStatusMsg(d.status_message ?? "");
        setStatus(d.status);
        if (d.status === "done") {
          stopAll();
          setRunning(false);
          setProgress(100);
          setApprovalStage(null);
          if (d.output_path) {
            const url = d.output_path.replace("/data/outputs/", "/outputs/") + "?t=" + Date.now();
            setVideoUrl(url);
          }
        } else if (d.status === "error") {
          stopAll();
          setRunning(false);
          setApprovalStage(null);
          setErrorMsg(d.error_message || "不明なエラー");
        } else if (d.status === "waiting_for_approval") {
          setApprovalStage(d.approval_stage ?? null);
          setPreviewUrl(d.preview_url ?? null);
        } else {
          setApprovalStage(null);
        }
      } catch { /* keep polling */ }
    }, 3000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleApproval = async (action: "approve" | "retry" | "reject") => {
    if (!jobId) return;
    setApprovalStage(null);
    setPreviewUrl(null);
    try {
      await fetch(`/api/v1/jobs/${jobId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
    } catch (e) { console.error("承認送信エラー", e); }
  };



  const handleRun = async () => {
    if (!customerName) { alert("顧客名を入力してください"); return; }
    if (scenes.some(s => !s.text.trim())) { alert("全シーンの台本を入力してください"); return; }

    stopAll();
    setRunning(true);
    setStatus("pending");
    setProgress(0);
    setStatusMsg("ジョブをキューに追加中...");
    setErrorMsg("");
    setVideoUrl(null);
    setApprovalStage(null);
    setPreviewUrl(null);
    setElapsed(0);
    startRef.current = Date.now();

    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);

    try {
      const res = await fetch("/api/v1/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: customerName,
          avatar_prompt: null,
          output_format: "shorts",
          script: scenes.map(s => ({
            text: s.text,
            scene_type: "talking_head",
            cinematic_prompt: s.cinematic_prompt || "modern office, bright lighting, cinematic",
            caption: "",
            pose: s.pose,
            camera_angle: s.camera_angle,
            appearance_prompt: "",
          })),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      setJobId(data.job_id);
      startPoll(data.job_id);
    } catch (e: unknown) {
      stopAll();
      setRunning(false);
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="space-y-4">
      <button
        onClick={handleRun}
        disabled={running}
        className="w-full py-3.5 rounded-xl font-bold text-base bg-gradient-to-r from-blue-600 via-violet-600 to-purple-600 hover:from-blue-500 hover:via-violet-500 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.98] text-white shadow-lg shadow-violet-500/20"
      >
        {running ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            生成中... ({fmtTime(elapsed)})
          </span>
        ) : "🚀 動画を生成する"}
      </button>

      {(running || status) && (
        <div className="glass p-5 space-y-3 fade-in">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">生成ステータス</h3>
            <div className="flex items-center gap-2">
              {jobId && <span className="text-xs text-[#4a6080]">job#{jobId}</span>}
              {status && <StatusBadge status={status} />}
              {running && <span className="text-xs text-[#3d7eff] font-mono">{fmtTime(elapsed)}</span>}
            </div>
          </div>

          <ProgressBar value={progress} label={statusMsg || "処理中..."} running={running} />

          {/* 承認待ちUI */}
          {approvalStage && (
            <div className="bg-violet-500/10 border border-violet-500/30 rounded-xl p-4 space-y-3 fade-in">
              <p className="text-sm font-semibold text-violet-300">承認待ち: {approvalStage}</p>
              {previewUrl && (
                <div className="flex justify-center">
                  {previewUrl.endsWith(".mp4") ? (
                    <video src={previewUrl} controls autoPlay loop className="max-h-48 rounded-lg border border-violet-500/30" />
                  ) : previewUrl.match(/\.(wav|mp3)$/) ? (
                    <audio src={previewUrl} controls className="w-full" />
                  ) : (
                    <img src={previewUrl} alt="preview" className="max-h-48 rounded-lg border border-violet-500/30 object-contain" />
                  )}
                </div>
              )}
              <div className="grid grid-cols-3 gap-2">
                <button onClick={() => handleApproval("approve")}
                  className="py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors">
                  承認
                </button>
                <button onClick={() => handleApproval("retry")}
                  className="py-2 rounded-lg text-sm font-semibold bg-amber-600 hover:bg-amber-500 text-white transition-colors">
                  再生成
                </button>
                <button onClick={() => handleApproval("reject")}
                  className="py-2 rounded-lg text-sm font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors">
                  中断
                </button>
              </div>
            </div>
          )}

          {errorMsg && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              <p className="text-xs text-red-300">エラー: {errorMsg}</p>
            </div>
          )}
        </div>
      )}

      {videoUrl && (
        <div className="glass overflow-hidden fade-in">
          <div className="px-5 py-3 border-b border-[#1f2d42] flex items-center justify-between">
            <h3 className="text-sm font-semibold text-emerald-400">✅ 生成完了！</h3>
            <a
              href={videoUrl}
              download="cocoro_video.mp4"
              className="text-xs text-[#3d7eff] hover:underline"
            >
              ⬇️ ダウンロード
            </a>
          </div>
          <div className="bg-black flex justify-center">
            <video
              src={videoUrl}
              controls
              autoPlay
              loop
              className="max-h-[480px] w-auto"
            />
          </div>
          {/* ✅ 完了後アクションボタン */}
          <div className="px-5 py-4 border-t border-[#1f2d42] space-y-3">
            <p className="text-xs text-[#4a6080]">
              📦 この動画は <span className="text-[#8ba0bc] font-mono">/data/outputs/videos/</span> に自動アーカイブされました
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={onGoToLibrary}
                className="py-2.5 rounded-xl text-sm font-semibold bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-300 border border-emerald-500/30 hover:border-emerald-400 transition-all"
              >
                📁 ライブラリで確認
              </button>
              <button
                onClick={onNewVideo}
                className="py-2.5 rounded-xl text-sm font-semibold bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 hover:border-blue-400 transition-all"
              >
                ➕ 新しい動画を作成
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Job History ─────────────────────

function JobHistory({ jobs, loading }: { jobs: Job[]; loading: boolean }) {
  if (loading) return <div className="py-12 text-center text-[#4a6080] text-sm">読み込み中...</div>;
  if (jobs.length === 0) return (
    <div className="py-16 text-center text-[#4a6080]">
      <p className="text-5xl mb-3">📭</p>
      <p className="text-sm">ジョブがありません</p>
    </div>
  );

  return (
    <div className="divide-y divide-[#1f2d42]">
      {jobs.map(job => (
        <div key={job.id} className="px-6 py-4 hover:bg-[#111827] transition-colors">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium">
                  {JOB_TYPE_LABELS[job.job_type] ?? job.job_type}
                </span>
                <span className="text-xs text-[#4a6080]">#{job.id}</span>
              </div>
              {job.status === "running" && job.progress != null && (
                <div className="mt-2 max-w-sm">
                  <ProgressBar value={job.progress} label={job.status_message ?? undefined} running />
                </div>
              )}
              {job.output_path && (
                <p className="text-xs text-[#4a6080] truncate mt-0.5">
                  → {job.output_path.split("/").slice(-2).join("/")}
                </p>
              )}
              {job.error_message && (
                <p className="text-xs text-red-400 mt-0.5 truncate">{job.error_message}</p>
              )}
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              <StatusBadge status={job.status} />
              <span className="text-xs text-[#4a6080]">
                {new Date(job.created_at).toLocaleString("ja-JP")}
              </span>
              {job.status === "done" && job.output_path?.endsWith(".mp4") && (
                <a
                  href={job.output_path.replace("/data/outputs/", "/outputs/") + "?t=" + Date.now()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-[#3d7eff] hover:underline"
                >
                  🎥 再生
                </a>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────── Video Library (Veo3-style) ──────

function fmtSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("ja-JP", {
    month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function VideoCard({
  video,
  onClick,
}: {
  video: VideoItem;
  onClick: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);

  return (
    <div className="video-card fade-in" onClick={onClick}>
      {/* Thumbnail area */}
      <div className="video-thumb">
        <video
          ref={videoRef}
          src={video.url}
          muted
          playsInline
          preload="metadata"
          onMouseEnter={() => videoRef.current?.play()}
          onMouseLeave={() => { videoRef.current?.pause(); if (videoRef.current) videoRef.current.currentTime = 0; }}
        />
        <div className="video-thumb-overlay">
          <div className="play-btn">▶</div>
        </div>
        {/* Badges */}
        <div className="absolute top-2 left-2 flex flex-col gap-1">
          {video.is_final && <span className="badge-final">FINAL</span>}
        </div>
        <div className="absolute bottom-2 left-2">
          <span className="badge-customer">{video.customer_name}</span>
        </div>
        <div className="absolute bottom-2 right-2 text-[10px] text-white/60 font-mono">
          {fmtSize(video.size_bytes)}
        </div>
      </div>

      {/* Meta */}
      <div className="p-3 space-y-1">
        <p className="text-xs font-medium text-[#f0f6ff] truncate" title={video.filename}>
          {video.filename}
        </p>
        <p className="text-[10px] text-[#4a6080]">{fmtDate(video.created_at)}</p>
      </div>
    </div>
  );
}

function VideoLightbox({
  video,
  onClose,
}: {
  video: VideoItem;
  onClose: () => void;
}) {
  // Escキーで閉じる
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="lightbox-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="lightbox-inner">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#1f2d42]">
          <div className="flex items-center gap-2">
            {video.is_final && <span className="badge-final">FINAL</span>}
            <span className="badge-customer">{video.customer_name}</span>
          </div>
          <div className="flex items-center gap-3">
            <a
              href={video.url}
              download={video.filename}
              className="text-xs text-[#3d7eff] hover:underline flex items-center gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              ⬇ DL ({fmtSize(video.size_bytes)})
            </a>
            <button
              onClick={onClose}
              className="text-[#4a6080] hover:text-[#f0f6ff] transition-colors text-lg leading-none"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Player */}
        <div className="bg-black flex justify-center">
          <video
            src={video.url}
            controls
            autoPlay
            loop
            className="max-h-[70vh] w-full object-contain"
          />
        </div>

        {/* Footer */}
        <div className="px-5 py-3 text-xs text-[#4a6080] flex justify-between">
          <span className="truncate max-w-[70%] font-mono text-[#8ba0bc]">{video.filename}</span>
          <span>{fmtDate(video.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

function VideoLibrary() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [customers, setCustomers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCustomer, setSelectedCustomer] = useState<string | null>(null);
  const [finalOnly, setFinalOnly] = useState(false);
  const [lightboxVideo, setLightboxVideo] = useState<VideoItem | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCustomer) params.set("customer", selectedCustomer);
      if (finalOnly) params.set("final_only", "true");
      const [vRes, cRes] = await Promise.all([
        fetch(`/api/v1/videos/?${params}`),
        fetch("/api/v1/videos/customers"),
      ]);
      if (vRes.ok) {
        const d = await vRes.json();
        setVideos(d.videos ?? []);
      }
      if (cRes.ok) {
        const c = await cRes.json();
        setCustomers(c);
      }
    } catch (e) {
      console.error("動画一覧取得エラー", e);
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, [selectedCustomer, finalOnly]);

  useEffect(() => { fetchVideos(); }, [fetchVideos]);

  return (
    <div className="space-y-5 fade-in">
      {/* ─ ツールバー ─ */}
      <div className="flex flex-wrap items-center gap-3">
        {/* 顧客フィルター */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setSelectedCustomer(null)}
            className={`filter-chip ${selectedCustomer === null ? "active" : ""}`}
          >
            すべて
          </button>
          {customers.map(c => (
            <button
              key={c}
              onClick={() => setSelectedCustomer(prev => prev === c ? null : c)}
              className={`filter-chip ${selectedCustomer === c ? "active" : ""}`}
            >
              {c}
            </button>
          ))}
        </div>

        {/* 最終動画フィルター */}
        <button
          onClick={() => setFinalOnly(f => !f)}
          className={`filter-chip flex items-center gap-1 ${finalOnly ? "active" : ""}`}
        >
          ⭐ 最終動画のみ
        </button>

        {/* スペーサー */}
        <div className="flex-1" />

        {/* 更新 */}
        <span className="text-[10px] text-[#4a6080]">
          {lastRefresh.toLocaleTimeString("ja-JP")} 更新
        </span>
        <button
          onClick={fetchVideos}
          disabled={loading}
          className="filter-chip flex items-center gap-1 disabled:opacity-50"
        >
          {loading ? "⏳" : "🔄"} 更新
        </button>
      </div>

      {/* ─ カウント ─ */}
      <p className="text-xs text-[#4a6080]">
        {loading ? "読み込み中..." : `${videos.length} 件の動画`}
      </p>

      {/* ─ グリッド ─ */}
      {!loading && videos.length === 0 && (
        <div className="py-24 text-center text-[#4a6080]">
          <p className="text-5xl mb-4">🎬</p>
          <p className="text-sm">動画がまだありません</p>
          <p className="text-xs mt-1">スタジオタブから動画を生成してください</p>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {videos.map(video => (
          <VideoCard
            key={video.id}
            video={video}
            onClick={() => setLightboxVideo(video)}
          />
        ))}
      </div>

      {/* ─ ライトボックス ─ */}
      {lightboxVideo && (
        <VideoLightbox
          video={lightboxVideo}
          onClose={() => setLightboxVideo(null)}
        />
      )}
    </div>
  );
}

// ─────────────────────────── Main Page ───────────────────────

type Tab = "studio" | "scene" | "jobs" | "library";

export default function StudioPage() {
  const [tab, setTab] = useState<Tab>("studio");
  const [customerName, setCustomerName] = useState("cocoro_customer");
  const [scenes, setScenes] = useState<SceneItem[]>([DEFAULT_SCENE()]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");

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
          ] as { key: Tab; label: string }[]).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-all ${
                tab === key
                  ? "border-[#3d7eff] text-[#f0f6ff]"
                  : "border-transparent text-[#4a6080] hover:text-[#8ba0bc]"
              }`}
            >
              {label}
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
      </main>
    </div>
  );
}
