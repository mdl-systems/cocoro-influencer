"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Job, SceneItem, QueueItem, QueueItemSettings } from "../types";
import ProgressBar from "./ProgressBar";

function BatchRunner({
  queue,
  onUpdate,
}: {
  queue: QueueItem[];
  onUpdate: (id: string, updates: Partial<QueueItem>) => void;
}) {
  const isStartingRef = useRef(false);
  const pollRefs = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  useEffect(() => {
    const running = queue.find(i => i.status === "running");
    if (running || isStartingRef.current) return;
    const next = queue.find(i => i.status === "pending");
    if (!next) return;
    isStartingRef.current = true;
    startItem(next).finally(() => { isStartingRef.current = false; });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue]);

  useEffect(() => () => {
    pollRefs.current.forEach(t => clearInterval(t));
  }, []);

  const startItem = async (item: QueueItem) => {
    onUpdate(item.id, { status: "running", statusMsg: "ジョブ送信中..." });
    try {
      const res = await fetch("/api/v1/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: item.customerName,
          avatar_prompt: null,
          output_format: item.settings.outputFormat,
          enable_subtitles: item.settings.enableSubtitles,
          bgm_name: item.settings.bgmName,
          bgm_volume: item.settings.bgmVolume,
          model_id: item.settings.modelId,
          speaker_id: item.settings.speakerId,
          transition: item.settings.transition,
          transition_duration: 0.5,
          watermark_name: item.settings.watermarkName,
          watermark_position: item.settings.watermarkPosition,
          watermark_scale: 0.15,
          script: item.scenes.map(s => ({
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
      const jobId: number = data.job_id;
      onUpdate(item.id, { jobId, statusMsg: `ジョブ #${jobId} 実行中...` });

      const timer = setInterval(async () => {
        try {
          const r = await fetch(`/api/v1/jobs/${jobId}`);
          const d = await r.json();
          onUpdate(item.id, { progress: d.progress ?? 0, statusMsg: d.status_message ?? "生成中..." });
          if (d.status === "done") {
            clearInterval(timer);
            pollRefs.current.delete(item.id);
            const videoUrl = d.output_path
              ? d.output_path.replace("/data/outputs/", "/outputs/") + "?t=" + Date.now()
              : null;
            onUpdate(item.id, { status: "done", progress: 100, videoUrl });
          } else if (d.status === "error") {
            clearInterval(timer);
            pollRefs.current.delete(item.id);
            onUpdate(item.id, { status: "error", errorMsg: d.error_message || "不明なエラー" });
          }
        } catch { /* keep polling */ }
      }, 5000);
      pollRefs.current.set(item.id, timer);
    } catch (e) {
      onUpdate(item.id, { status: "error", errorMsg: e instanceof Error ? e.message : String(e) });
    }
  };

  return null;
}

// ─────────────────────────── D-2 QueueTab ───────────────────
function QueueTab({
  queue,
  onClearDone,
  onRemove,
}: {
  queue: QueueItem[];
  onClearDone: () => void;
  onRemove: (id: string) => void;
}) {
  const pending = queue.filter(i => i.status === "pending").length;
  const running = queue.filter(i => i.status === "running").length;
  const done    = queue.filter(i => i.status === "done").length;
  const errored = queue.filter(i => i.status === "error").length;

  if (queue.length === 0) {
    return (
      <div className="py-24 text-center text-[#4a6080] fade-in">
        <p className="text-5xl mb-4">📋</p>
        <p className="text-sm">キューは空です</p>
        <p className="text-xs mt-2">スタジオで台本を設定し「➕ キューに追加」を押してください</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 fade-in">
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "待機中", value: pending, color: "text-amber-400",   icon: "⏳" },
          { label: "実行中", value: running, color: "text-blue-400",    icon: "⚡" },
          { label: "完了",   value: done,    color: "text-emerald-400", icon: "✅" },
          { label: "エラー", value: errored, color: "text-red-400",     icon: "❌" },
        ].map(s => (
          <div key={s.label} className="glass p-4 text-center">
            <p className="text-xl">{s.icon}</p>
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-[10px] text-[#4a6080]">{s.label}</p>
          </div>
        ))}
      </div>

      {done > 0 && (
        <div className="flex justify-end">
          <button onClick={onClearDone}
            className="text-xs text-[#4a6080] hover:text-[#8ba0bc] border border-[#1f2d42] px-3 py-1.5 rounded-lg transition-colors">
            ✅ 完了済みをクリア ({done}件)
          </button>
        </div>
      )}

      <div className="glass overflow-hidden">
        {queue.map((item, idx) => (
          <div key={item.id} className={`px-5 py-4 border-b border-[#1f2d42] last:border-0 ${
            item.status === "running" ? "bg-blue-500/5" :
            item.status === "done"    ? "bg-emerald-500/5" :
            item.status === "error"   ? "bg-red-500/5" : ""
          }`}>
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="text-xs font-bold text-[#4a6080]">#{idx + 1}</span>
                  <span className="text-sm font-semibold text-[#f0f6ff] truncate">{item.customerName}</span>
                  <span className="text-[10px] text-[#4a6080]">{item.scenes.length}シーン</span>
                  {item.status === "pending" && <span className="text-xs text-amber-400">⏳ 待機中</span>}
                  {item.status === "running" && <span className="text-xs text-blue-400 animate-pulse">⚡ 実行中</span>}
                  {item.status === "done"    && <span className="text-xs text-emerald-400">✅ 完了</span>}
                  {item.status === "error"   && <span className="text-xs text-red-400">❌ エラー</span>}
                  {item.jobId && <span className="text-[10px] text-[#4a6080]">job#{item.jobId}</span>}
                </div>
                <div className="flex gap-1.5 flex-wrap mb-2">
                  <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">
                    {item.settings.outputFormat === "youtube" ? "🖥 YouTube" : "📱 Shorts"}
                  </span>
                  {item.settings.transition !== "none" && (
                    <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">✨ {item.settings.transition}</span>
                  )}
                  {item.settings.bgmName && (
                    <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">🎵 {item.settings.bgmName}</span>
                  )}
                  {item.settings.enableSubtitles && (
                    <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">📝 字幕</span>
                  )}
                </div>
                {(item.status === "running" || item.status === "done") && (
                  <ProgressBar value={item.progress} label={item.statusMsg} running={item.status === "running"} />
                )}
                {item.errorMsg && <p className="text-xs text-red-400 mt-1">{item.errorMsg}</p>}
                {item.status === "done" && item.videoUrl && (
                  <div className="mt-3 rounded-xl overflow-hidden border border-emerald-500/30 bg-black flex justify-center">
                    <video src={item.videoUrl} controls autoPlay loop muted className="max-h-48 w-auto" />
                  </div>
                )}
              </div>
              {(item.status === "pending" || item.status === "error") && (
                <button onClick={() => onRemove(item.id)}
                  className="text-xs text-[#4a6080] hover:text-red-400 transition-colors shrink-0 mt-1">✕</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default QueueTab;
