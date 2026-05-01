"use client";

import { useCallback, useEffect, useRef, useState } from "react";;
import { VideoItem } from "../types";

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

export default VideoLibrary;
