"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

// ─── 削除確認ダイアログ ─────────────────────────────────────
function DeleteConfirmDialog({
  video,
  onConfirm,
  onCancel,
}: {
  video: VideoItem;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-[#0d1521] border border-red-500/40 rounded-2xl p-6 max-w-sm w-full mx-4 space-y-4 shadow-2xl">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🗑️</span>
          <div>
            <p className="text-sm font-bold text-red-400">動画を削除しますか？</p>
            <p className="text-[10px] text-[#4a6080] mt-0.5">この操作は元に戻せません</p>
          </div>
        </div>
        <p className="text-xs text-[#8ba0bc] font-mono bg-[#080c14] rounded-lg px-3 py-2 truncate">
          {video.filename}
        </p>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={onCancel}
            className="py-2 rounded-xl text-sm font-semibold bg-[#1f2d42] hover:bg-[#253547] text-[#8ba0bc] transition-colors"
          >
            キャンセル
          </button>
          <button
            onClick={onConfirm}
            className="py-2 rounded-xl text-sm font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors"
          >
            削除する
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── VideoCard ───────────────────────────────────────────────
function VideoCard({
  video,
  onClick,
  onDelete,
}: {
  video: VideoItem;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);

  return (
    <div className="video-card fade-in group" onClick={onClick}>
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
        {/* 削除ボタン (ホバー時のみ表示) */}
        <button
          onClick={onDelete}
          className="absolute top-2 right-2 w-7 h-7 rounded-full bg-red-600/80 hover:bg-red-500 text-white text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-lg"
          title="動画を削除"
        >
          🗑
        </button>
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

// ─── VideoLightbox ───────────────────────────────────────────
function VideoLightbox({
  video,
  onClose,
  onDelete,
}: {
  video: VideoItem;
  onClose: () => void;
  onDelete: () => void;
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
            {/* 削除ボタン */}
            <button
              onClick={onDelete}
              className="text-xs px-2 py-1 rounded-lg bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-500/30 transition-colors"
            >
              🗑 削除
            </button>
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

// ─── VideoLibrary (メイン) ───────────────────────────────────
function VideoLibrary() {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [customers, setCustomers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCustomer, setSelectedCustomer] = useState<string | null>(null);
  const [finalOnly, setFinalOnly] = useState(false);
  const [lightboxVideo, setLightboxVideo] = useState<VideoItem | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  // 削除確認ダイアログ
  const [deleteTarget, setDeleteTarget] = useState<VideoItem | null>(null);
  const [deleting, setDeleting] = useState(false);

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

  // ─── 削除処理 ───────────────────────────────────────────────
  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await fetch(`/api/v1/videos/${deleteTarget.id}`, { method: "DELETE" });
      if (res.ok || res.status === 204) {
        // ライトボックスが開いていれば閉じる
        if (lightboxVideo?.id === deleteTarget.id) setLightboxVideo(null);
        // 一覧から除去
        setVideos(prev => prev.filter(v => v.id !== deleteTarget.id));
      } else {
        alert("削除に失敗しました");
      }
    } catch (e) {
      console.error("動画削除エラー", e);
      alert("削除に失敗しました");
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

  const requestDelete = (video: VideoItem, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setDeleteTarget(video);
  };

  return (
    <div className="space-y-5 fade-in">
      {/* ─ 削除確認ダイアログ ─ */}
      {deleteTarget && !deleting && (
        <DeleteConfirmDialog
          video={deleteTarget}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      {deleting && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60">
          <div className="text-white text-sm">削除中...</div>
        </div>
      )}

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

      {/* ─ 空状態 ─ */}
      {!loading && videos.length === 0 && (
        <div className="py-24 text-center text-[#4a6080]">
          <p className="text-5xl mb-4">🎬</p>
          <p className="text-sm">動画がまだありません</p>
          <p className="text-xs mt-1">スタジオタブから動画を生成してください</p>
        </div>
      )}

      {/* ─ グリッド ─ */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {videos.map(video => (
          <VideoCard
            key={video.id}
            video={video}
            onClick={() => setLightboxVideo(video)}
            onDelete={(e) => requestDelete(video, e)}
          />
        ))}
      </div>

      {/* ─ ライトボックス ─ */}
      {lightboxVideo && (
        <VideoLightbox
          video={lightboxVideo}
          onClose={() => setLightboxVideo(null)}
          onDelete={() => requestDelete(lightboxVideo)}
        />
      )}
    </div>
  );
}

export default VideoLibrary;
