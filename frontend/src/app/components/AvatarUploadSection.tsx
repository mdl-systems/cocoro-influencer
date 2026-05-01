"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Job } from "../types";
import DropZone from "./DropZone";
import ProgressBar from "./ProgressBar";

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

export default AvatarUploadSection;
