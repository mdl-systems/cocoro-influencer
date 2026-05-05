"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Job, SceneItem } from "../types";
import ProgressBar from "./ProgressBar";
import StatusBadge from "./StatusBadge";


function PipelineRunner({
  customerName,
  scenes,
  onGoToLibrary,
  onNewVideo,
  onAddToQueue,
}: {
  customerName: string;
  scenes: SceneItem[];
  onGoToLibrary?: () => void;
  onNewVideo?: () => void;
  onAddToQueue?: (settings: import("../types").QueueItemSettings) => void;
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

  // ① 字幕
  const [enableSubtitles, setEnableSubtitles] = useState(false);
  // ② BGM
  const [bgmFiles, setBgmFiles] = useState<string[]>([]);
  const [bgmName, setBgmName] = useState<string | null>(null);
  const [bgmVolume, setBgmVolume] = useState(0.12);
  // ③ 音声モデル
  interface VoiceModel { id: number; model_id: number; spk_id: number; name: string }
  const [voiceModels, setVoiceModels] = useState<VoiceModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState(0);
  const [selectedSpeakerId, setSelectedSpeakerId] = useState(0);
  // B-1 フォーマット
  const [outputFormat, setOutputFormat] = useState<"shorts" | "youtube">("shorts");
  // B-2 トランジション
  const [transition, setTransition] = useState("none");
  // B-3 ウォーターマーク
  const [logoFiles, setLogoFiles] = useState<string[]>([]);
  const [selectedLogo, setSelectedLogo] = useState<string | null>(null);
  const [logoPosition, setLogoPosition] = useState("bottom-right");
  const [uploading, setUploading] = useState(false);
  // ④ 話速
  const [speechSpeed, setSpeechSpeed] = useState(0.50);
  // ⑤ アニメーションエンジン選択
  const [videoEngine, setVideoEngine] = useState<"sadtalker"|"liveportrait"|"wan22"|"musetalk">("sadtalker");


  // BGM一覧・音声一覧・ロゴ一覧を起動時に取得
  useEffect(() => {
    fetch("/api/v1/pipeline/bgm/list").then(r => r.json()).then(d => setBgmFiles(d.files ?? []))
      .catch(() => {});
    fetch("/api/v1/pipeline/voices").then(r => r.json()).then(d => {
      const models: VoiceModel[] = [];
      (d.models ?? []).forEach((m: Record<string, unknown>, mi: number) => {
        const spks = m.spk2id as Record<string, number> | undefined;
        if (spks) {
          Object.entries(spks).forEach(([name, spkId]) => {
            models.push({ id: models.length, model_id: mi, spk_id: spkId, name: `${m.model_name ?? `Model ${mi}`} - ${name}` });
          });
        } else {
          models.push({ id: mi, model_id: mi, spk_id: 0, name: String(m.model_name ?? `Model ${mi}`) });
        }
      });
      setVoiceModels(models);
    }).catch(() => {});
    fetch("/api/v1/pipeline/logos/list").then(r => r.json()).then(d => setLogoFiles(d.logos ?? []))
      .catch(() => {});
  }, []);

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/v1/pipeline/logos/upload", { method: "POST", body: fd });
      const d = await res.json();
      if (res.ok) {
        setLogoFiles(prev => [...prev.filter(f => f !== d.filename), d.filename]);
        setSelectedLogo(d.filename);
      }
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

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
          output_format: outputFormat,
          enable_subtitles: enableSubtitles,
          bgm_name: bgmName,
          bgm_volume: bgmVolume,
          model_id: selectedModelId,
          speaker_id: selectedSpeakerId,
          transition,
          transition_duration: 0.5,
          watermark_name: selectedLogo,
          watermark_position: logoPosition,
          watermark_scale: 0.15,
          script: scenes.map(s => ({
            text: s.text,
            scene_type: "talking_head",
            cinematic_prompt: s.cinematic_prompt || "modern office, bright lighting, cinematic",
            caption: "",
            pose: s.pose,
            camera_angle: s.camera_angle,
            appearance_prompt: "",
          })),
          speech_speed: speechSpeed,
          use_wan22: videoEngine === "wan22",
          use_liveportrait: videoEngine === "liveportrait",
          use_sadtalker: videoEngine === "sadtalker",
          use_musetalk: videoEngine === "musetalk",
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

      {/* ① 字幕 + ② BGM + ③ 音声 + B-1 フォーマット + B-2 トランジション + B-3 ロゴ — 設定パネル */}
      <div className="bg-[#080c14] rounded-xl p-4 space-y-4 border border-[#1f2d42]">
        <p className="text-[10px] font-bold text-[#4a6080] uppercase tracking-widest">⚙️ 生成オプション</p>

        {/* B-1 フォーマット */}
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-[#f0f6ff]">📱 出力フォーマット</p>
          <div className="grid grid-cols-2 gap-1.5">
            <button onClick={() => setOutputFormat("shorts")}
              className={`py-1.5 rounded-lg text-xs font-semibold transition-all ${
                outputFormat === "shorts" ? "bg-blue-600 text-white" : "bg-[#0d1521] text-[#4a6080] border border-[#1f2d42] hover:border-blue-500/50"
              }`}>
              📱 縦型 (Shorts 9:16)
            </button>
            <button onClick={() => setOutputFormat("youtube")}
              className={`py-1.5 rounded-lg text-xs font-semibold transition-all ${
                outputFormat === "youtube" ? "bg-blue-600 text-white" : "bg-[#0d1521] text-[#4a6080] border border-[#1f2d42] hover:border-blue-500/50"
              }`}>
              🖥 横型 (YouTube 16:9)
            </button>
          </div>
        </div>

        {/* B-2 トランジション */}
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-[#f0f6ff]">✨ シーン間トランジション</p>
          <div className="flex flex-wrap gap-1.5">
            {[
              { id: "none", label: "カット" },
              { id: "fade", label: "フェード" },
              { id: "wipeleft", label: "ワイプ左" },
              { id: "wiperight", label: "ワイプ右" },
              { id: "dissolve", label: "ディゾルブ" },
              { id: "slideleft", label: "スライド" },
              { id: "fadeblack", label: "黒フェード" },
            ].map(t => (
              <button key={t.id} onClick={() => setTransition(t.id)}
                className={`cam-chip ${
                  transition === t.id ? "border-violet-400 text-violet-300 bg-violet-500/10" : ""
                }`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* ① 字幕 */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-[#f0f6ff]">📝 字幕自動生成</p>
            <p className="text-[10px] text-[#4a6080]">台本テキストを動画に字幕として熷き込む</p>
          </div>
          <button
            onClick={() => setEnableSubtitles(v => !v)}
            className={`w-10 h-5 rounded-full transition-colors relative ${enableSubtitles ? "bg-blue-600" : "bg-[#1f2d42]"}`}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${enableSubtitles ? "left-5" : "left-0.5"}`} />
          </button>
        </div>

        {/* ② BGM */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-[#f0f6ff]">🎵 BGM</p>
            {bgmName && (
              <span className="text-[10px] text-[#3d7eff]">vol: {Math.round(bgmVolume * 100)}%</span>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => setBgmName(null)}
              className={`cam-chip ${bgmName === null ? "border-[#3d7eff] text-[#3d7eff] bg-[rgba(61,126,255,0.1)]" : ""}`}
            >
              なし
            </button>
            {bgmFiles.length === 0 && <span className="text-[10px] text-[#4a6080] py-1">/data/bgm/ にファイルを置いてください</span>}
            {bgmFiles.map(f => (
              <button key={f} onClick={() => setBgmName(f)}
                className={`cam-chip ${bgmName === f ? "border-[#3d7eff] text-[#3d7eff] bg-[rgba(61,126,255,0.1)]" : ""}`}>
                🎵 {f}
              </button>
            ))}
          </div>
          {bgmName && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-[#4a6080]">0%</span>
              <input type="range" min={0} max={0.5} step={0.01} value={bgmVolume}
                onChange={e => setBgmVolume(Number(e.target.value))}
                className="flex-1 accent-blue-500 h-1"
              />
              <span className="text-[10px] text-[#4a6080]">50%</span>
            </div>
          )}
        </div>

        {/* B-3 ロゴ/ウォーターマーク */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-[#f0f6ff]">📛 ロゴ/ウォーターマーク</p>
            <label className={`text-[10px] px-2 py-0.5 rounded-lg cursor-pointer transition-colors ${
              uploading ? "opacity-50 cursor-wait" : "bg-[#1f2d42] hover:bg-[#253547] text-[#8ba0bc]"
            }`}>
              {uploading ? "アップロード中..." : "➕ アップロード"}
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={handleLogoUpload} className="hidden" />
            </label>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button onClick={() => setSelectedLogo(null)}
              className={`cam-chip ${selectedLogo === null ? "border-emerald-400 text-emerald-300 bg-emerald-500/10" : ""}`}>
              なし
            </button>
            {logoFiles.map(f => (
              <button key={f} onClick={() => setSelectedLogo(f)}
                className={`cam-chip ${selectedLogo === f ? "border-emerald-400 text-emerald-300 bg-emerald-500/10" : ""}`}>
                📛 {f}
              </button>
            ))}
          </div>
          {selectedLogo && (
            <div className="flex flex-wrap gap-1">
              {["bottom-right", "bottom-left", "top-right", "top-left"].map(pos => (
                <button key={pos} onClick={() => setLogoPosition(pos)}
                  className={`cam-chip text-[10px] ${
                    logoPosition === pos ? "border-emerald-400 text-emerald-300" : ""
                  }`}>
                  {pos === "bottom-right" ? "↘" : pos === "bottom-left" ? "↙" : pos === "top-right" ? "↗" : "↖"} {pos.replace("-", " ")}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ③ 音声モデル */}
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-[#f0f6ff]">🎤 音声</p>
          {voiceModels.length === 0 ? (
            <p className="text-[10px] text-[#4a6080]">Style-Bert-VITS2のモデルを読み込み中...</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {voiceModels.map(m => (
                <button key={m.id}
                  onClick={() => { setSelectedModelId(m.model_id); setSelectedSpeakerId(m.spk_id); }}
                  className={`cam-chip text-[10px] ${
                    selectedModelId === m.model_id && selectedSpeakerId === m.spk_id
                      ? "border-violet-400 text-violet-300 bg-violet-500/10" : ""
                  }`}>
                  {m.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ④ 話速スライダー */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-[#f0f6ff]">🗣️ 話速</p>
            <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${
              speechSpeed <= 0.55 ? "text-blue-300 bg-blue-500/10" :
              speechSpeed <= 0.85 ? "text-emerald-300 bg-emerald-500/10" :
              "text-orange-300 bg-orange-500/10"
            }`}>
              {speechSpeed <= 0.45 ? "🐢 超ゆっくり" :
               speechSpeed <= 0.65 ? "🐢 ゆっくり" :
               speechSpeed <= 0.85 ? "🚶 やや遅め" :
               speechSpeed <= 1.05 ? "🏃 標準" : "⚡ 速め"} ({speechSpeed.toFixed(2)}x)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-[#4a6080] w-8">遅い</span>
            <input
              type="range" min={0.3} max={1.5} step={0.05}
              value={speechSpeed}
              onChange={e => setSpeechSpeed(Number(e.target.value))}
              className="flex-1 accent-blue-500 h-1"
            />
            <span className="text-[10px] text-[#4a6080] w-8">速い</span>
          </div>
          <div className="flex justify-between px-8">
            {[0.30, 0.50, 0.70, 1.00, 1.50].map(v => (
              <button key={v} onClick={() => setSpeechSpeed(v)}
                className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
                  Math.abs(speechSpeed - v) < 0.03
                    ? "bg-blue-600 text-white"
                    : "text-[#4a6080] hover:text-[#8ba0bc]"
                }`}>
                {v.toFixed(2)}x
              </button>
            ))}
          </div>
        </div>

        {/* ⑤ アニメーションエンジン選択 */}
        <div className="pt-2 border-t border-[#1f2d42]">
          <p className="text-xs font-semibold text-[#f0f6ff] mb-2">⚡ アニメーションエンジン</p>
          <div className="grid grid-cols-2 gap-1.5">
            {([
              { id: "sadtalker",    icon: "💬", label: "SadTalker",    desc: "リップシンク高精度",        time: "2分",  color: "blue",    available: true  },
              { id: "liveportrait", icon: "🎭", label: "LivePortrait", desc: "頭・目が自然に動く",        time: "3分",  color: "violet", available: true  },
              { id: "wan22",        icon: "💪", label: "Wan2.2 I2V",   desc: "全身・腕・体の動き",        time: "10分", color: "emerald", available: true  },
              { id: "musetalk",     icon: "🌏", label: "MuseTalk",     desc: "日本語対応リップシンク",    time: "準備中", color: "orange", available: false },
            ] as const).map(eng => (
              <button
                key={eng.id}
                onClick={() => eng.available && setVideoEngine(eng.id as typeof videoEngine)}
                disabled={!eng.available}
                className={`relative p-2.5 rounded-xl border text-left transition-all ${
                  !eng.available
                    ? "opacity-40 cursor-not-allowed border-[#1f2d42] bg-[#0a1628]"
                    : videoEngine === eng.id
                    ? eng.color === "blue"    ? "border-blue-500    bg-blue-500/10"
                    : eng.color === "violet"  ? "border-violet-500  bg-violet-500/10"
                    : eng.color === "emerald" ? "border-emerald-500 bg-emerald-500/10"
                    :                          "border-orange-500  bg-orange-500/10"
                    : "border-[#1f2d42] bg-[#0a1628] hover:border-[#2a3d52]"
                }`}
              >
                {videoEngine === eng.id && eng.available && (
                  <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full" style={{
                    backgroundColor: eng.color === "blue" ? "#3b82f6" : eng.color === "violet" ? "#8b5cf6" : eng.color === "emerald" ? "#10b981" : "#f97316"
                  }} />
                )}
                <div className="text-base mb-0.5">{eng.icon}</div>
                <div className="text-[11px] font-bold text-[#f0f6ff]">{eng.label}</div>
                <div className="text-[9px] text-[#4a6080] mt-0.5 leading-tight">{eng.desc}</div>
                <div className={`text-[9px] font-semibold mt-1 ${
                  eng.color === "blue" ? "text-blue-400" : eng.color === "violet" ? "text-violet-400" : eng.color === "emerald" ? "text-emerald-400" : "text-orange-400"
                }`}>⏱ {eng.time}</div>
              </button>
            ))}
          </div>
        </div>

      </div>

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

      {/* ─ キューに追加ボタン ─ */}
      {onAddToQueue && (
        <button
          onClick={() => onAddToQueue({
            outputFormat,
            transition,
            bgmName,
            bgmVolume,
            enableSubtitles,
            modelId: selectedModelId,
            speakerId: selectedSpeakerId,
            watermarkName: selectedLogo,
            watermarkPosition: logoPosition,
          })}
          disabled={running}
          className="w-full py-2.5 rounded-xl font-semibold text-sm border border-violet-500/40 bg-violet-500/10 hover:bg-violet-500/20 text-violet-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          ➕ バッチキューに追加
        </button>
      )}

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

export default PipelineRunner;
