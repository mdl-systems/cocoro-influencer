"use client";

import { useEffect, useRef, useState } from "react";
import { Job, SceneItem, SceneJobState } from "../types";
import ProgressBar from "./ProgressBar";

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

export default SceneRegenerator;
