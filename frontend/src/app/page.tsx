"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Types 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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
  pose: "neutral" | "talking" | "greeting" | "presenting" | "thinking" | "walk" | "pointing";
  camera_angle: "close_up" | "upper_body" | "full_body";
  cinematic_prompt: string;
}

// D-1 繝励Μ繧ｻ繝・ヨ
interface ScenePreset {
  id: string;
  name: string;
  createdAt: string;
  customerName: string;
  scenes: SceneItem[];
}

// D-2 繝舌ャ繝√く繝･繝ｼ
interface QueueItemSettings {
  outputFormat: "shorts" | "youtube";
  transition: string;
  bgmName: string | null;
  bgmVolume: number;
  enableSubtitles: boolean;
  modelId: number;
  speakerId: number;
  watermarkName: string | null;
  watermarkPosition: string;
}

interface QueueItem {
  id: string;
  customerName: string;
  scenes: SceneItem[];
  settings: QueueItemSettings;
  addedAt: string;
  status: "pending" | "running" | "done" | "error";
  jobId: number | null;
  progress: number;
  statusMsg: string;
  videoUrl: string | null;
  errorMsg: string | null;
}

interface SceneJobState {
  jobId: number | null;
  status: "idle" | "running" | "done" | "error";
  progress: number;
  statusMsg: string;
  previewUrl: string | null;
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Constants 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

const JOB_TYPE_LABELS: Record<string, string> = {
  avatar:       "耳 繧｢繝舌ち繝ｼ逕滓・",
  voice:        "痔 髻ｳ螢ｰ蜷域・",
  talking_head: "離・・繝医・繧ｭ繝ｳ繧ｰ繝倥ャ繝・,
  cinematic:    "汐 繧ｷ繝阪・繝・ぅ繝・け",
  compose:      "笨ゑｸ・蜍慕判蜷域・",
  pipeline:     "噫 繝輔Ν繝代う繝励Λ繧､繝ｳ",
  instantid:    "ｧｬ InstantID",
};

const STATUS_STYLE: Record<string, string> = {
  pending:              "bg-amber-500/10 text-amber-300 border-amber-500/30",
  running:              "bg-blue-500/10 text-blue-300 border-blue-500/30",
  done:                 "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  error:                "bg-red-500/10 text-red-300 border-red-500/30",
  waiting_for_approval: "bg-violet-500/10 text-violet-300 border-violet-500/30",
};

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Sub-components 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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
        <span className="truncate max-w-[70%]">{label || "蜃ｦ逅・ｸｭ..."}</span>
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

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 DropZone 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

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
        <div className="text-4xl mb-2">胴</div>
      )}
      <p className={`text-sm font-semibold ${accent}`}>{label}</p>
      <p className="text-xs text-[#4a6080] mt-0.5">{sublabel}</p>
    </div>
  );
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Avatar Upload Section 笏笏笏笏笏笏笏笏笏笏笏

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
      if (count > 480) { stopPoll(); setPollStatus("竢ｰ 繧ｿ繧､繝繧｢繧ｦ繝・(80蛻・"); return; }
      try {
        const res = await fetch(`/api/v1/jobs/${jid}`);
        const d: Job = await res.json();
        if (d.status === "done") {
          stopPoll();
          setPollProgress(100);
          setPollStatus("脂 InstantID繝昴・繧ｺ逕ｻ蜒上・逕滓・縺悟ｮ御ｺ・＠縺ｾ縺励◆・・);
          onUploaded();
        } else if (d.status === "error") {
          stopPoll();
          setPollStatus(`笶・繧ｨ繝ｩ繝ｼ: ${d.error_message || "隧ｳ邏ｰ縺ｯ繝ｭ繧ｰ繧堤｢ｺ隱・}`);
        } else {
          setPollProgress(d.progress ?? 0);
          setPollStatus(d.status_message ? `竢ｳ ${d.status_message}` : `竢ｳ InstantID繝昴・繧ｺ逕滓・荳ｭ (job#${jid})`);
        }
      } catch { /* network error, keep polling */ }
    }, 10000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onUploaded]);

  useEffect(() => () => stopPoll(), []);

  const handleUpload = async () => {
    if (!customerName) { alert("蜈医↓鬘ｧ螳｢蜷阪ｒ蜈･蜉帙＠縺ｦ縺上□縺輔＞"); return; }
    if (!faceFile)    { alert("鬘泌・逵溘ｒ驕ｸ謚槭＠縺ｦ縺上□縺輔＞"); return; }
    setUploading(true);
    setPollStatus("繧｢繝・・繝ｭ繝ｼ繝我ｸｭ...");
    const fd = new FormData();
    fd.append("file", faceFile);
    if (fbFile) fd.append("fullbody_file", fbFile);
    try {
      const res = await fetch(`/api/v1/avatars/upload?customer_name=${encodeURIComponent(customerName)}`, {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) { setPollStatus(`笶・${JSON.stringify(data)}`); return; }
      if (data.job_id) {
        setJobId(data.job_id);
        setPollStatus(`笨・菫晏ｭ伜ｮ御ｺ・竊・InstantID逕滓・髢句ｧ・(job#${data.job_id})`);
        startPoll(data.job_id);
      } else {
        setPollStatus("笨・" + (data.message || "繧｢繝・・繝ｭ繝ｼ繝牙ｮ御ｺ・));
        onUploaded();
      }
    } catch (e) {
      setPollStatus(`笶・繝阪ャ繝医Ρ繝ｼ繧ｯ繧ｨ繝ｩ繝ｼ: ${e}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <DropZone
          label="鬘泌・逵滂ｼ亥ｿ・茨ｼ・
          sublabel="豁｣髱｢繝ｻ繧ｯ繝ｭ繝ｼ繧ｺ繧｢繝・・謗ｨ螂ｨ"
          accent="text-yellow-400"
          onChange={handleFace}
          preview={facePreview}
        />
        <DropZone
          label="蜈ｨ霄ｫ蜀咏悄・域耳螂ｨ・・
          sublabel="鬆ｭ縲懆ｶｳ縺ｾ縺ｧ蜈ｨ菴・
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
        {uploading ? "繧｢繝・・繝ｭ繝ｼ繝我ｸｭ..." : "豆 繧｢繝・・繝ｭ繝ｼ繝・& InstantID逕滓・"}
      </button>

      {pollStatus && (
        <div className="space-y-2 fade-in">
          <p className="text-xs text-[#8ba0bc]">{pollStatus}</p>
          {jobId && pollProgress > 0 && pollProgress < 100 && (
            <ProgressBar value={pollProgress} running label="InstantID繝昴・繧ｺ逕滓・" />
          )}
        </div>
      )}
    </div>
  );
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Scene Editor 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

const DEFAULT_SCENE: () => SceneItem = () => ({
  id: Math.random().toString(36).slice(2),
  text: "",
  pose: "neutral",
  camera_angle: "upper_body",
  cinematic_prompt: "modern office, professional lighting, subtle movement, cinematic",
});

// 竭 繧ｫ繝｡繝ｩ讒句峙繧ｪ繝励す繝ｧ繝ｳ
const CAMERA_OPTIONS: { value: SceneItem["camera_angle"]; icon: string; label: string; sub: string }[] = [
  { value: "close_up",   icon: "側", label: "鬘斐い繝・・",   sub: "Close-up"   },
  { value: "upper_body", icon: "ｧ・, label: "荳雁濠霄ｫ",      sub: "Upper body" },
  { value: "full_body",  icon: "垳", label: "蜈ｨ霄ｫ",        sub: "Full body"  },
];

// 竭｡ 繝昴・繧ｺ繧ｪ繝励す繝ｧ繝ｳ (7遞ｮ)
const POSE_OPTIONS: { value: SceneItem["pose"]; icon: string; label: string }[] = [
  { value: "neutral",    icon: "・", label: "騾壼ｸｸ"     },
  { value: "talking",    icon: "離",  label: "隧ｱ縺・     },
  { value: "greeting",   icon: "窓", label: "謖ｨ諡ｶ"     },
  { value: "presenting", icon: "搭", label: "繝励Ξ繧ｼ繝ｳ" },
  { value: "thinking",   icon: "､・, label: "諤晁・     },
  { value: "walk",       icon: "垳", label: "豁ｩ縺・     },
  { value: "pointing",   icon: "笘晢ｸ・, label: "謖・ｷｮ縺・   },
];

// 竭｢ 繧ｫ繝｡繝ｩ繝繝ｼ繝冶ｾ樊嶌 (繧ｯ繝ｪ繝・け縺ｧ cinematic_prompt 縺ｫ霑ｽ險・
const CAMERA_MOVES: { label: string; prompt: string }[] = [
  { label: "剥+ 繧ｺ繝ｼ繝繧､繝ｳ",    prompt: "slow zoom in"               },
  { label: "剥- 繧ｺ繝ｼ繝繧｢繧ｦ繝・,  prompt: "slow zoom out"              },
  { label: "竊・繝代Φ蟾ｦ",          prompt: "slow pan left"              },
  { label: "竊・繝代Φ蜿ｳ",          prompt: "slow pan right"             },
  { label: "竊・繝・ぅ繝ｫ繝井ｸ・,      prompt: "tilt up slowly"             },
  { label: "竊・繝・ぅ繝ｫ繝井ｸ・,      prompt: "tilt down slowly"           },
  { label: "売 繧ｪ繝ｼ繝薙ャ繝・,     prompt: "orbit around subject"       },
  { label: "東 蝗ｺ螳・,            prompt: "static camera"              },
  { label: "汐 謇区戟縺｡",         prompt: "handheld camera, slight shake" },
  { label: "笨ｨ 繧ｹ繝繝ｼ繧ｺ",       prompt: "cinematic smooth motion"    },
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

          {/* 笏笏 Header 笏笏 */}
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#4a6080] uppercase tracking-widest">Scene {i + 1}</span>
            {scenes.length > 1 && (
              <button onClick={() => remove(i)}
                className="text-xs text-red-400 hover:text-red-300 transition-colors px-2 py-0.5 rounded hover:bg-red-500/10">
                卵・・蜑企勁
              </button>
            )}
          </div>

          {/* 笏笏 蜿ｰ譛ｬ繝・く繧ｹ繝・笏笏 */}
          <textarea
            rows={3}
            value={scene.text}
            onChange={(e) => update(i, { text: e.target.value })}
            placeholder="蜿ｰ譛ｬ繝・く繧ｹ繝医ｒ蜈･蜉・.. (AI縺碁浹螢ｰ繧貞粋謌舌＠縺ｾ縺・"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-3 py-2 text-sm text-[#f0f6ff] placeholder-[#4a6080] resize-none transition-colors"
          />

          {/* 竭 繧ｫ繝｡繝ｩ讒句峙繧｢繧､繧ｳ繝ｳ驕ｸ謚・*/}
          <div>
            <label className="block text-[10px] font-bold text-[#4a6080] uppercase tracking-widest mb-2">胴 繧ｫ繝｡繝ｩ讒句峙</label>
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

          {/* 竭｡ 繝昴・繧ｺ繧｢繧､繧ｳ繝ｳ驕ｸ謚・(7遞ｮ) */}
          <div>
            <label className="block text-[10px] font-bold text-[#4a6080] uppercase tracking-widest mb-2">兵 繝昴・繧ｺ</label>
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

          {/* 竭｢ 閭梧勹繝励Ο繝ｳ繝励ヨ + 繧ｫ繝｡繝ｩ繝繝ｼ繝冶ｾ樊嶌 */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] font-bold text-[#4a6080] uppercase tracking-widest">汐 閭梧勹繝ｻ蜍輔″繝励Ο繝ｳ繝励ヨ</label>
              <button
                onClick={() => setShowMoves(prev => ({ ...prev, [i]: !prev[i] }))}
                className="text-[10px] text-[#3d7eff] hover:underline"
              >
                {showMoves[i] ? "笆ｲ 髢峨§繧・ : "笆ｼ 繧ｫ繝｡繝ｩ繝繝ｼ繝冶ｾ樊嶌"}
              </button>
            </div>
            <input
              type="text"
              value={scene.cinematic_prompt}
              onChange={(e) => update(i, { cinematic_prompt: e.target.value })}
              placeholder="modern office, professional lighting..."
              className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-lg px-3 py-1.5 text-xs text-[#f0f6ff] placeholder-[#4a6080] transition-colors mb-1.5"
            />
            {/* 繧ｫ繝｡繝ｩ繝繝ｼ繝冶ｾ樊嶌繝√ャ繝・*/}
            {showMoves[i] && (
              <div className="flex flex-wrap gap-1.5 fade-in p-2 bg-[#080c14] rounded-lg border border-[#1f2d42]">
                <p className="w-full text-[9px] text-[#4a6080] mb-0.5">繧ｯ繝ｪ繝・け縺ｧ繝励Ο繝ｳ繝励ヨ縺ｫ霑ｽ蜉 竊・/p>
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
        + 繧ｷ繝ｼ繝ｳ繧定ｿｽ蜉
      </button>
    </div>
  );
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 AI 蜿ｰ譛ｬ逕滓・ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

function ScriptGenerator({ onScriptReady }: { onScriptReady: (scenes: SceneItem[]) => void }) {
  const [open, setOpen] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [productName, setProductName] = useState("");
  const [target, setTarget] = useState("20莉｣縲・0莉｣縺ｮ繝薙ず繝阪せ繝代・繧ｽ繝ｳ");
  const [tone, setTone] = useState("繝励Ο繝輔ぉ繝・す繝ｧ繝翫Ν縺ｧ隕ｪ縺励∩繧・☆縺・);
  const [duration, setDuration] = useState("60遘・);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    if (!companyName || !productName) { alert("莨夂､ｾ蜷阪→蝠・刀繝ｻ繧ｵ繝ｼ繝薙せ蜷阪ｒ蜈･蜉帙＠縺ｦ縺上□縺輔＞"); return; }
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
      if (scenes.length === 0) throw new Error("蜿ｰ譛ｬ繧ｷ繝ｼ繝ｳ縺檎函謌舌＆繧後∪縺帙ｓ縺ｧ縺励◆");
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
        AI 縺ｧ蜿ｰ譛ｬ繧定・蜍慕函謌・(Ollama / Qwen2.5:32b)
      </button>
    );
  }

  return (
    <div className="scene-card p-4 space-y-3 fade-in" style={{ borderColor: "rgba(139,92,246,0.4)" }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-violet-400 uppercase tracking-widest">AI 蜿ｰ譛ｬ逕滓・</span>
        <button onClick={() => setOpen(false)} className="text-xs text-[#4a6080] hover:text-[#8ba0bc]">髢峨§繧・/button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">莨夂､ｾ蜷・*</label>
          <input value={companyName} onChange={e => setCompanyName(e.target.value)}
            placeholder="萓・ 譬ｪ蠑丈ｼ夂､ｾ繧ｵ繝ｳ繝励Ν"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
        </div>
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">蝠・刀繝ｻ繧ｵ繝ｼ繝薙せ蜷・*</label>
          <input value={productName} onChange={e => setProductName(e.target.value)}
            placeholder="萓・ AI蜍慕判逕滓・繧ｵ繝ｼ繝薙せ"
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">繝医・繝ｳ</label>
          <input value={tone} onChange={e => setTone(e.target.value)}
            placeholder="繝励Ο繝輔ぉ繝・す繝ｧ繝翫Ν縺ｧ隕ｪ縺励∩繧・☆縺・
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
        </div>
        <div>
          <label className="block text-xs text-[#4a6080] mb-1">蟆ｺ繝ｻ髟ｷ縺・/label>
          <select value={duration} onChange={e => setDuration(e.target.value)}
            className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-2 py-1.5 text-sm text-[#f0f6ff] transition-colors">
            <option value="30遘・>30遘・/option>
            <option value="60遘・>60遘・/option>
            <option value="90遘・>90遘・/option>
            <option value="120遘・>120遘・/option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs text-[#4a6080] mb-1">繧ｿ繝ｼ繧ｲ繝・ヨ螻､</label>
        <input value={target} onChange={e => setTarget(e.target.value)}
          placeholder="20莉｣縲・0莉｣縺ｮ繝薙ず繝阪せ繝代・繧ｽ繝ｳ"
          className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-violet-500 outline-none rounded-lg px-3 py-1.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
      </div>

      {error && <p className="text-xs text-red-400">繧ｨ繝ｩ繝ｼ: {error}</p>}

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="w-full py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all text-white"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            Ollama (Qwen2.5:32b) 縺ｧ逕滓・荳ｭ...
          </span>
        ) : "蜿ｰ譛ｬ繧堤函謌・}
      </button>
    </div>
  );
}


// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Scene Regenerator 笏笏笏笏笏笏笏笏笏笏笏

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
      if (count > 360) { // 30蛻・ち繧､繝繧｢繧ｦ繝・        stopPoll(idx);
        setSceneJobs(prev => ({ ...prev, [idx]: { ...prev[idx], status: "error", statusMsg: "竢ｰ 繧ｿ繧､繝繧｢繧ｦ繝・ } }));
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
          setSceneJobs(prev => ({ ...prev, [idx]: { jobId, status: "done", progress: 100, statusMsg: "笨・螳御ｺ・, previewUrl: url } }));
        } else if (d.status === "error") {
          stopPoll(idx);
          setSceneJobs(prev => ({ ...prev, [idx]: { jobId, status: "error", progress: 0, statusMsg: `笶・${d.error_message || "繧ｨ繝ｩ繝ｼ"}`, previewUrl: null } }));
        } else {
          setSceneJobs(prev => ({ ...prev, [idx]: { ...prev[idx], progress: d.progress ?? 0, statusMsg: d.status_message ?? "逕滓・荳ｭ..." } }));
        }
      } catch { /* keep polling */ }
    }, 5000);
  };

  const handleRegenerate = async (idx: number) => {
    if (!customerName) { alert("鬘ｧ螳｢蜷阪ｒ蜈･蜉帙＠縺ｦ縺上□縺輔＞"); return; }
    const scene = scenes[idx];
    if (!scene?.text.trim()) { alert(`Scene ${idx + 1} 縺ｮ蜿ｰ譛ｬ繧貞・蜉帙＠縺ｦ縺上□縺輔＞`); return; }

    setSceneJobs(prev => ({ ...prev, [idx]: { jobId: null, status: "running", progress: 0, statusMsg: "繧ｸ繝ｧ繝夜∽ｿ｡荳ｭ...", previewUrl: null } }));

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
      setSceneJobs(prev => ({ ...prev, [idx]: { ...prev[idx], jobId, statusMsg: `繧ｸ繝ｧ繝・#${jobId} 螳溯｡御ｸｭ...` } }));
      startPoll(idx, jobId);
    } catch (e: unknown) {
      setSceneJobs(prev => ({ ...prev, [idx]: { jobId: null, status: "error", progress: 0, statusMsg: `笶・${e instanceof Error ? e.message : String(e)}`, previewUrl: null } }));
    }
  };

  if (scenes.length === 0) {
    return <p className="text-sm text-[#4a6080] text-center py-8">縺ｾ縺壹せ繧ｿ繧ｸ繧ｪ繧ｿ繝悶〒繧ｷ繝ｼ繝ｳ繧定ｿｽ蜉縺励※縺上□縺輔＞</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-[#4a6080]">蜷・す繝ｼ繝ｳ繧貞句挨縺ｫ逕滓・縺ｧ縺阪∪縺吶ょ・菴薙ヱ繧､繝励Λ繧､繝ｳ縺ｨ縺ｯ迢ｬ遶九＠縺ｦ螳溯｡後＆繧後∪縺吶・/p>
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
                {job?.status === "running"  && <span className="text-xs text-blue-400 animate-pulse">竢ｳ 逕滓・荳ｭ</span>}
                {job?.status === "done"     && <span className="text-xs text-emerald-400">笨・螳御ｺ・/span>}
                {job?.status === "error"    && <span className="text-xs text-red-400">笶・繧ｨ繝ｩ繝ｼ</span>}
                {job?.jobId && <span className="text-xs text-[#4a6080]">job#{job.jobId}</span>}
              </div>
              <button
                onClick={() => handleRegenerate(idx)}
                disabled={isRunning}
                className="text-xs font-semibold px-3 py-1 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 hover:border-indigo-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                笙ｻ・・蜊倅ｽ鍋函謌・              </button>
            </div>

            {/* 蜿ｰ譛ｬ繝励Ξ繝薙Η繝ｼ */}
            <p className="text-xs text-[#8ba0bc] line-clamp-2">{scene.text || <span className="text-[#4a6080] italic">蜿ｰ譛ｬ譛ｪ蜈･蜉・/span>}</p>

            {/* 騾ｲ謐励ヰ繝ｼ */}
            {job && job.status !== "idle" && (
              <div className="space-y-2">
                <ProgressBar
                  value={job.progress}
                  label={job.statusMsg}
                  running={isRunning}
                />

                {/* 螳御ｺ・・繝ｬ繝薙Η繝ｼ */}
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
  onAddToQueue,
}: {
  customerName: string;
  scenes: SceneItem[];
  onGoToLibrary?: () => void;
  onNewVideo?: () => void;
  onAddToQueue?: (settings: QueueItemSettings, name: string, scenesCopy: SceneItem[]) => void;
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

  // 竭 蟄怜ｹ・  const [enableSubtitles, setEnableSubtitles] = useState(false);
  // 竭｡ BGM
  const [bgmFiles, setBgmFiles] = useState<string[]>([]);
  const [bgmName, setBgmName] = useState<string | null>(null);
  const [bgmVolume, setBgmVolume] = useState(0.12);
  // 竭｢ 髻ｳ螢ｰ繝｢繝・Ν
  interface VoiceModel { id: number; model_id: number; spk_id: number; name: string }
  const [voiceModels, setVoiceModels] = useState<VoiceModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState(0);
  const [selectedSpeakerId, setSelectedSpeakerId] = useState(0);
  // B-1 繝輔か繝ｼ繝槭ャ繝・  const [outputFormat, setOutputFormat] = useState<"shorts" | "youtube">("shorts");
  // B-2 繝医Λ繝ｳ繧ｸ繧ｷ繝ｧ繝ｳ
  const [transition, setTransition] = useState("none");
  // B-3 繧ｦ繧ｩ繝ｼ繧ｿ繝ｼ繝槭・繧ｯ
  const [logoFiles, setLogoFiles] = useState<string[]>([]);
  const [selectedLogo, setSelectedLogo] = useState<string | null>(null);
  const [logoPosition, setLogoPosition] = useState("bottom-right");
  const [uploading, setUploading] = useState(false);

  // BGM荳隕ｧ繝ｻ髻ｳ螢ｰ荳隕ｧ繝ｻ繝ｭ繧ｴ荳隕ｧ繧定ｵｷ蜍墓凾縺ｫ蜿門ｾ・  useEffect(() => {
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
          setErrorMsg(d.error_message || "荳肴・縺ｪ繧ｨ繝ｩ繝ｼ");
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
    } catch (e) { console.error("謇ｿ隱埼∽ｿ｡繧ｨ繝ｩ繝ｼ", e); }
  };



  const handleRun = async () => {
    if (!customerName) { alert("鬘ｧ螳｢蜷阪ｒ蜈･蜉帙＠縺ｦ縺上□縺輔＞"); return; }
    if (scenes.some(s => !s.text.trim())) { alert("蜈ｨ繧ｷ繝ｼ繝ｳ縺ｮ蜿ｰ譛ｬ繧貞・蜉帙＠縺ｦ縺上□縺輔＞"); return; }

    stopAll();
    setRunning(true);
    setStatus("pending");
    setProgress(0);
    setStatusMsg("繧ｸ繝ｧ繝悶ｒ繧ｭ繝･繝ｼ縺ｫ霑ｽ蜉荳ｭ...");
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

      {/* 竭 蟄怜ｹ・+ 竭｡ BGM + 竭｢ 髻ｳ螢ｰ + B-1 繝輔か繝ｼ繝槭ャ繝・+ B-2 繝医Λ繝ｳ繧ｸ繧ｷ繝ｧ繝ｳ + B-3 繝ｭ繧ｴ 窶・險ｭ螳壹ヱ繝阪Ν */}
      <div className="bg-[#080c14] rounded-xl p-4 space-y-4 border border-[#1f2d42]">
        <p className="text-[10px] font-bold text-[#4a6080] uppercase tracking-widest">笞呻ｸ・逕滓・繧ｪ繝励す繝ｧ繝ｳ</p>

        {/* B-1 繝輔か繝ｼ繝槭ャ繝・*/}
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-[#f0f6ff]">導 蜃ｺ蜉帙ヵ繧ｩ繝ｼ繝槭ャ繝・/p>
          <div className="grid grid-cols-2 gap-1.5">
            <button onClick={() => setOutputFormat("shorts")}
              className={`py-1.5 rounded-lg text-xs font-semibold transition-all ${
                outputFormat === "shorts" ? "bg-blue-600 text-white" : "bg-[#0d1521] text-[#4a6080] border border-[#1f2d42] hover:border-blue-500/50"
              }`}>
              導 邵ｦ蝙・(Shorts 9:16)
            </button>
            <button onClick={() => setOutputFormat("youtube")}
              className={`py-1.5 rounded-lg text-xs font-semibold transition-all ${
                outputFormat === "youtube" ? "bg-blue-600 text-white" : "bg-[#0d1521] text-[#4a6080] border border-[#1f2d42] hover:border-blue-500/50"
              }`}>
              箕 讓ｪ蝙・(YouTube 16:9)
            </button>
          </div>
        </div>

        {/* B-2 繝医Λ繝ｳ繧ｸ繧ｷ繝ｧ繝ｳ */}
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-[#f0f6ff]">笨ｨ 繧ｷ繝ｼ繝ｳ髢薙ヨ繝ｩ繝ｳ繧ｸ繧ｷ繝ｧ繝ｳ</p>
          <div className="flex flex-wrap gap-1.5">
            {[
              { id: "none", label: "繧ｫ繝・ヨ" },
              { id: "fade", label: "繝輔ぉ繝ｼ繝・ },
              { id: "wipeleft", label: "繝ｯ繧､繝怜ｷｦ" },
              { id: "wiperight", label: "繝ｯ繧､繝怜承" },
              { id: "dissolve", label: "繝・ぅ繧ｾ繝ｫ繝・ },
              { id: "slideleft", label: "繧ｹ繝ｩ繧､繝・ },
              { id: "fadeblack", label: "鮟偵ヵ繧ｧ繝ｼ繝・ },
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

        {/* 竭 蟄怜ｹ・*/}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-[#f0f6ff]">統 蟄怜ｹ戊・蜍慕函謌・/p>
            <p className="text-[10px] text-[#4a6080]">蜿ｰ譛ｬ繝・く繧ｹ繝医ｒ蜍慕判縺ｫ蟄怜ｹ輔→縺励※辭ｷ縺崎ｾｼ繧</p>
          </div>
          <button
            onClick={() => setEnableSubtitles(v => !v)}
            className={`w-10 h-5 rounded-full transition-colors relative ${enableSubtitles ? "bg-blue-600" : "bg-[#1f2d42]"}`}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${enableSubtitles ? "left-5" : "left-0.5"}`} />
          </button>
        </div>

        {/* 竭｡ BGM */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-[#f0f6ff]">七 BGM</p>
            {bgmName && (
              <span className="text-[10px] text-[#3d7eff]">vol: {Math.round(bgmVolume * 100)}%</span>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => setBgmName(null)}
              className={`cam-chip ${bgmName === null ? "border-[#3d7eff] text-[#3d7eff] bg-[rgba(61,126,255,0.1)]" : ""}`}
            >
              縺ｪ縺・            </button>
            {bgmFiles.length === 0 && <span className="text-[10px] text-[#4a6080] py-1">/data/bgm/ 縺ｫ繝輔ぃ繧､繝ｫ繧堤ｽｮ縺・※縺上□縺輔＞</span>}
            {bgmFiles.map(f => (
              <button key={f} onClick={() => setBgmName(f)}
                className={`cam-chip ${bgmName === f ? "border-[#3d7eff] text-[#3d7eff] bg-[rgba(61,126,255,0.1)]" : ""}`}>
                七 {f}
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

        {/* B-3 繝ｭ繧ｴ/繧ｦ繧ｩ繝ｼ繧ｿ繝ｼ繝槭・繧ｯ */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-[#f0f6ff]">筒 繝ｭ繧ｴ/繧ｦ繧ｩ繝ｼ繧ｿ繝ｼ繝槭・繧ｯ</p>
            <label className={`text-[10px] px-2 py-0.5 rounded-lg cursor-pointer transition-colors ${
              uploading ? "opacity-50 cursor-wait" : "bg-[#1f2d42] hover:bg-[#253547] text-[#8ba0bc]"
            }`}>
              {uploading ? "繧｢繝・・繝ｭ繝ｼ繝我ｸｭ..." : "筐・繧｢繝・・繝ｭ繝ｼ繝・}
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={handleLogoUpload} className="hidden" />
            </label>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button onClick={() => setSelectedLogo(null)}
              className={`cam-chip ${selectedLogo === null ? "border-emerald-400 text-emerald-300 bg-emerald-500/10" : ""}`}>
              縺ｪ縺・            </button>
            {logoFiles.map(f => (
              <button key={f} onClick={() => setSelectedLogo(f)}
                className={`cam-chip ${selectedLogo === f ? "border-emerald-400 text-emerald-300 bg-emerald-500/10" : ""}`}>
                筒 {f}
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
                  {pos === "bottom-right" ? "竊・ : pos === "bottom-left" ? "竊・ : pos === "top-right" ? "竊・ : "竊・} {pos.replace("-", " ")}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 竭｢ 髻ｳ螢ｰ繝｢繝・Ν */}
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-[#f0f6ff]">痔 髻ｳ螢ｰ</p>
          {voiceModels.length === 0 ? (
            <p className="text-[10px] text-[#4a6080]">Style-Bert-VITS2縺ｮ繝｢繝・Ν繧定ｪｭ縺ｿ霎ｼ縺ｿ荳ｭ...</p>
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
      </div>

      {/* 繝ｭ繧ｴ/繧ｦ繧ｩ繝ｼ繧ｿ繝ｼ繝槭・繧ｯ莉･髯阪・逵∫払 窶・縺薙％縺ｫ險ｭ螳壹ヱ繝阪Ν縺檎ｶ壹￥ */}

      {/* 筐・繧ｭ繝･繝ｼ縺ｫ霑ｽ蜉 */}
      <button
        onClick={() => {
          if (!customerName) { alert("鬘ｧ螳｢蜷阪ｒ蜈･蜉帙＠縺ｦ縺上□縺輔＞"); return; }
          if (scenes.some(s => !s.text.trim())) { alert("蜈ｨ繧ｷ繝ｼ繝ｳ縺ｮ蜿ｰ譛ｬ繧貞・蜉帙＠縺ｦ縺上□縺輔＞"); return; }
          onAddToQueue?.({
            outputFormat,
            transition,
            bgmName,
            bgmVolume,
            enableSubtitles,
            modelId: selectedModelId,
            speakerId: selectedSpeakerId,
            watermarkName: selectedLogo,
            watermarkPosition: logoPosition,
          }, customerName, JSON.parse(JSON.stringify(scenes)));
        }}
        className="w-full py-2.5 rounded-xl text-sm font-semibold bg-[#0d1521] border border-[#1f2d42] hover:border-violet-500/50 hover:bg-violet-500/10 text-[#8ba0bc] hover:text-violet-300 transition-all"
      >
        筐・繧ｭ繝･繝ｼ縺ｫ霑ｽ蜉
      </button>

      <button
        onClick={handleRun}
        disabled={running}
        className="w-full py-3.5 rounded-xl font-bold text-base bg-gradient-to-r from-blue-600 via-violet-600 to-purple-600 hover:from-blue-500 hover:via-violet-500 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.98] text-white shadow-lg shadow-violet-500/20"
      >
        {running ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            逕滓・荳ｭ... ({fmtTime(elapsed)})
          </span>
        ) : "噫 蜍慕判繧堤函謌舌☆繧・}
      </button>

      {(running || status) && (
        <div className="glass p-5 space-y-3 fade-in">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">逕滓・繧ｹ繝・・繧ｿ繧ｹ</h3>
            <div className="flex items-center gap-2">
              {jobId && <span className="text-xs text-[#4a6080]">job#{jobId}</span>}
              {status && <StatusBadge status={status} />}
              {running && <span className="text-xs text-[#3d7eff] font-mono">{fmtTime(elapsed)}</span>}
            </div>
          </div>

          <ProgressBar value={progress} label={statusMsg || "蜃ｦ逅・ｸｭ..."} running={running} />

          {/* 謇ｿ隱榊ｾ・■UI */}
          {approvalStage && (
            <div className="bg-violet-500/10 border border-violet-500/30 rounded-xl p-4 space-y-3 fade-in">
              <p className="text-sm font-semibold text-violet-300">謇ｿ隱榊ｾ・■: {approvalStage}</p>
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
                  謇ｿ隱・                </button>
                <button onClick={() => handleApproval("retry")}
                  className="py-2 rounded-lg text-sm font-semibold bg-amber-600 hover:bg-amber-500 text-white transition-colors">
                  蜀咲函謌・                </button>
                <button onClick={() => handleApproval("reject")}
                  className="py-2 rounded-lg text-sm font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors">
                  荳ｭ譁ｭ
                </button>
              </div>
            </div>
          )}

          {errorMsg && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              <p className="text-xs text-red-300">繧ｨ繝ｩ繝ｼ: {errorMsg}</p>
            </div>
          )}
        </div>
      )}

      {videoUrl && (
        <div className="glass overflow-hidden fade-in">
          <div className="px-5 py-3 border-b border-[#1f2d42] flex items-center justify-between">
            <h3 className="text-sm font-semibold text-emerald-400">笨・逕滓・螳御ｺ・ｼ・/h3>
            <a
              href={videoUrl}
              download="cocoro_video.mp4"
              className="text-xs text-[#3d7eff] hover:underline"
            >
              筮・ｸ・繝繧ｦ繝ｳ繝ｭ繝ｼ繝・            </a>
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
          {/* 笨・螳御ｺ・ｾ後い繧ｯ繧ｷ繝ｧ繝ｳ繝懊ち繝ｳ */}
          <div className="px-5 py-4 border-t border-[#1f2d42] space-y-3">
            <p className="text-xs text-[#4a6080]">
              逃 縺薙・蜍慕判縺ｯ <span className="text-[#8ba0bc] font-mono">/data/outputs/videos/</span> 縺ｫ閾ｪ蜍輔い繝ｼ繧ｫ繧､繝悶＆繧後∪縺励◆
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={onGoToLibrary}
                className="py-2.5 rounded-xl text-sm font-semibold bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-300 border border-emerald-500/30 hover:border-emerald-400 transition-all"
              >
                刀 繝ｩ繧､繝悶Λ繝ｪ縺ｧ遒ｺ隱・              </button>
              <button
                onClick={onNewVideo}
                className="py-2.5 rounded-xl text-sm font-semibold bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 hover:border-blue-400 transition-all"
              >
                筐・譁ｰ縺励＞蜍慕判繧剃ｽ懈・
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Job History 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏

function JobHistory({ jobs, loading }: { jobs: Job[]; loading: boolean }) {
  if (loading) return <div className="py-12 text-center text-[#4a6080] text-sm">隱ｭ縺ｿ霎ｼ縺ｿ荳ｭ...</div>;
  if (jobs.length === 0) return (
    <div className="py-16 text-center text-[#4a6080]">
      <p className="text-5xl mb-3">働</p>
      <p className="text-sm">繧ｸ繝ｧ繝悶′縺ゅｊ縺ｾ縺帙ｓ</p>
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
                  竊・{job.output_path.split("/").slice(-2).join("/")}
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
                  磁 蜀咲函
                </a>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 Video Library (Veo3-style) 笏笏笏笏笏笏

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
          <div className="play-btn">笆ｶ</div>
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
  // Esc繧ｭ繝ｼ縺ｧ髢峨§繧・  useEffect(() => {
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
              筮・DL ({fmtSize(video.size_bytes)})
            </a>
            <button
              onClick={onClose}
              className="text-[#4a6080] hover:text-[#f0f6ff] transition-colors text-lg leading-none"
            >
              笨・            </button>
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
      console.error("蜍慕判荳隕ｧ蜿門ｾ励お繝ｩ繝ｼ", e);
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, [selectedCustomer, finalOnly]);

  useEffect(() => { fetchVideos(); }, [fetchVideos]);

  return (
    <div className="space-y-5 fade-in">
      {/* 笏 繝・・繝ｫ繝舌・ 笏 */}
      <div className="flex flex-wrap items-center gap-3">
        {/* 鬘ｧ螳｢繝輔ぅ繝ｫ繧ｿ繝ｼ */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setSelectedCustomer(null)}
            className={`filter-chip ${selectedCustomer === null ? "active" : ""}`}
          >
            縺吶∋縺ｦ
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

        {/* 譛邨ょ虚逕ｻ繝輔ぅ繝ｫ繧ｿ繝ｼ */}
        <button
          onClick={() => setFinalOnly(f => !f)}
          className={`filter-chip flex items-center gap-1 ${finalOnly ? "active" : ""}`}
        >
          箝・譛邨ょ虚逕ｻ縺ｮ縺ｿ
        </button>

        {/* 繧ｹ繝壹・繧ｵ繝ｼ */}
        <div className="flex-1" />

        {/* 譖ｴ譁ｰ */}
        <span className="text-[10px] text-[#4a6080]">
          {lastRefresh.toLocaleTimeString("ja-JP")} 譖ｴ譁ｰ
        </span>
        <button
          onClick={fetchVideos}
          disabled={loading}
          className="filter-chip flex items-center gap-1 disabled:opacity-50"
        >
          {loading ? "竢ｳ" : "売"} 譖ｴ譁ｰ
        </button>
      </div>

      {/* 笏 繧ｫ繧ｦ繝ｳ繝・笏 */}
      <p className="text-xs text-[#4a6080]">
        {loading ? "隱ｭ縺ｿ霎ｼ縺ｿ荳ｭ..." : `${videos.length} 莉ｶ縺ｮ蜍慕判`}
      </p>

      {/* 笏 繧ｰ繝ｪ繝・ラ 笏 */}
      {!loading && videos.length === 0 && (
        <div className="py-24 text-center text-[#4a6080]">
          <p className="text-5xl mb-4">汐</p>
          <p className="text-sm">蜍慕判縺後∪縺縺ゅｊ縺ｾ縺帙ｓ</p>
          <p className="text-xs mt-1">繧ｹ繧ｿ繧ｸ繧ｪ繧ｿ繝悶°繧牙虚逕ｻ繧堤函謌舌＠縺ｦ縺上□縺輔＞</p>
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

      {/* 笏 繝ｩ繧､繝医・繝・け繧ｹ 笏 */}
      {lightboxVideo && (
        <VideoLightbox
          video={lightboxVideo}
          onClose={() => setLightboxVideo(null)}
        />
      )}
    </div>
  );
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 D-1 Preset Panel 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
const PRESET_KEY = "cocoro_presets";

function PresetPanel({
  customerName,
  scenes,
  onLoad,
}: {
  customerName: string;
  scenes: SceneItem[];
  onLoad: (preset: ScenePreset) => void;
}) {
  const [presets, setPresets] = useState<ScenePreset[]>(() => {
    try { return JSON.parse(localStorage.getItem(PRESET_KEY) || "[]"); }
    catch { return []; }
  });
  const [open, setOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);

  const save = () => {
    if (!saveName.trim()) { alert("繝励Μ繧ｻ繝・ヨ蜷阪ｒ蜈･蜉帙＠縺ｦ縺上□縺輔＞"); return; }
    const preset: ScenePreset = {
      id: crypto.randomUUID(),
      name: saveName.trim(),
      createdAt: new Date().toISOString(),
      customerName,
      scenes: JSON.parse(JSON.stringify(scenes)),
    };
    const updated = [preset, ...presets].slice(0, 20);
    setPresets(updated);
    localStorage.setItem(PRESET_KEY, JSON.stringify(updated));
    setSaveName("");
    setSaving(false);
  };

  const del = (id: string) => {
    const updated = presets.filter(p => p.id !== id);
    setPresets(updated);
    localStorage.setItem(PRESET_KEY, JSON.stringify(updated));
  };

  return (
    <div className="glass p-4 space-y-3 fade-in">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-[#8ba0bc] uppercase tracking-widest">沈 繝励Μ繧ｻ繝・ヨ</span>
        <button onClick={() => setOpen(v => !v)} className="text-xs text-[#4a6080] hover:text-[#8ba0bc] transition-colors">
          {open ? "笆ｲ 髢峨§繧・ : `笆ｼ ${presets.length > 0 ? `${presets.length}莉ｶ菫晏ｭ倅ｸｭ` : "菫晏ｭ倥↑縺・}`}
        </button>
      </div>

      {saving ? (
        <div className="flex gap-2">
          <input
            autoFocus value={saveName} onChange={e => setSaveName(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") save(); if (e.key === "Escape") setSaving(false); }}
            placeholder="繝励Μ繧ｻ繝・ヨ蜷阪ｒ蜈･蜉・.."
            className="flex-1 bg-[#080c14] border border-[#1f2d42] focus:border-emerald-500 outline-none rounded-lg px-3 py-1.5 text-xs text-[#f0f6ff] placeholder-[#4a6080]"
          />
          <button onClick={save} className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold">菫晏ｭ・/button>
          <button onClick={() => setSaving(false)} className="px-3 py-1.5 rounded-lg bg-[#1f2d42] text-[#8ba0bc] text-xs">笨・/button>
        </div>
      ) : (
        <button
          onClick={() => setSaving(true)}
          className="w-full py-2 rounded-lg text-xs font-semibold border border-dashed border-[#1f2d42] hover:border-emerald-500/50 text-[#4a6080] hover:text-emerald-400 transition-all"
        >
          + 迴ｾ蝨ｨ縺ｮ險ｭ螳壹ｒ繝励Μ繧ｻ繝・ヨ菫晏ｭ・        </button>
      )}

      {open && (
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {presets.length === 0 && <p className="text-xs text-[#4a6080] text-center py-4">菫晏ｭ俶ｸ医∩繝励Μ繧ｻ繝・ヨ縺ｯ縺ゅｊ縺ｾ縺帙ｓ</p>}
          {presets.map(p => (
            <div key={p.id} className="flex items-center gap-2 bg-[#080c14] rounded-lg px-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-[#f0f6ff] truncate">{p.name}</p>
                <p className="text-[10px] text-[#4a6080]">
                  {p.customerName} ﾂｷ {p.scenes.length}繧ｷ繝ｼ繝ｳ ﾂｷ {new Date(p.createdAt).toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
              <button onClick={() => { onLoad(p); setOpen(false); }}
                className="text-xs px-2 py-1 rounded bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 transition-all shrink-0">
                隱ｭ霎ｼ
              </button>
              <button onClick={() => del(p.id)}
                className="text-xs px-2 py-1 rounded bg-red-600/10 hover:bg-red-600/30 text-red-400 border border-red-500/20 transition-all shrink-0">
                蜑企勁
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 D-2 BatchRunner (invisible engine) 笏笏
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
    onUpdate(item.id, { status: "running", statusMsg: "繧ｸ繝ｧ繝夜∽ｿ｡荳ｭ..." });
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
      onUpdate(item.id, { jobId, statusMsg: `繧ｸ繝ｧ繝・#${jobId} 螳溯｡御ｸｭ...` });

      const timer = setInterval(async () => {
        try {
          const r = await fetch(`/api/v1/jobs/${jobId}`);
          const d = await r.json();
          onUpdate(item.id, { progress: d.progress ?? 0, statusMsg: d.status_message ?? "逕滓・荳ｭ..." });
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
            onUpdate(item.id, { status: "error", errorMsg: d.error_message || "荳肴・縺ｪ繧ｨ繝ｩ繝ｼ" });
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

// 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏 D-2 QueueTab 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
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
        <p className="text-5xl mb-4">搭</p>
        <p className="text-sm">繧ｭ繝･繝ｼ縺ｯ遨ｺ縺ｧ縺・/p>
        <p className="text-xs mt-2 text-[#4a6080]">繧ｹ繧ｿ繧ｸ繧ｪ縺ｧ蜿ｰ譛ｬ繧定ｨｭ螳壹＠縲娯桾 繧ｭ繝･繝ｼ縺ｫ霑ｽ蜉縲阪ｒ謚ｼ縺励※縺上□縺輔＞</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 fade-in">
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "蠕・ｩ滉ｸｭ", value: pending, color: "text-amber-400",   icon: "竢ｳ" },
          { label: "螳溯｡御ｸｭ", value: running, color: "text-blue-400",    icon: "笞｡" },
          { label: "螳御ｺ・,   value: done,    color: "text-emerald-400", icon: "笨・ },
          { label: "繧ｨ繝ｩ繝ｼ", value: errored, color: "text-red-400",     icon: "笶・ },
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
            className="text-xs text-[#4a6080] hover:text-[#8ba0bc] border border-[#1f2d42] hover:border-[#253547] px-3 py-1.5 rounded-lg transition-colors">
            笨・螳御ｺ・ｸ医∩繧偵け繝ｪ繧｢ ({done}莉ｶ)
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
                  <span className="text-[10px] text-[#4a6080]">{item.scenes.length}繧ｷ繝ｼ繝ｳ</span>
                  {item.status === "pending" && <span className="text-xs text-amber-400">竢ｳ 蠕・ｩ滉ｸｭ</span>}
                  {item.status === "running" && <span className="text-xs text-blue-400 animate-pulse">笞｡ 螳溯｡御ｸｭ</span>}
                  {item.status === "done"    && <span className="text-xs text-emerald-400">笨・螳御ｺ・/span>}
                  {item.status === "error"   && <span className="text-xs text-red-400">笶・繧ｨ繝ｩ繝ｼ</span>}
                  {item.jobId && <span className="text-[10px] text-[#4a6080]">job#{item.jobId}</span>}
                </div>

                <div className="flex gap-1.5 flex-wrap mb-2">
                  <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">
                    {item.settings.outputFormat === "youtube" ? "箕 YouTube" : "導 Shorts"}
                  </span>
                  {item.settings.transition !== "none" && (
                    <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">笨ｨ {item.settings.transition}</span>
                  )}
                  {item.settings.bgmName && (
                    <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">七 {item.settings.bgmName}</span>
                  )}
                  {item.settings.enableSubtitles && (
                    <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">統 蟄怜ｹ・/span>
                  )}
                  {item.settings.watermarkName && (
                    <span className="text-[10px] bg-[#0d1521] border border-[#1f2d42] rounded px-1.5 py-0.5 text-[#4a6080]">筒 {item.settings.watermarkName}</span>
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
                  className="text-xs text-[#4a6080] hover:text-red-400 transition-colors shrink-0 mt-1">
                  笨・                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────── Main Page ───────────────────────

type Tab = "studio" | "scene" | "jobs" | "library" | "batch";

export default function StudioPage() {
  const [tab, setTab] = useState<Tab>("studio");
  const [customerName, setCustomerName] = useState("cocoro_customer");
  const [scenes, setScenes] = useState<SceneItem[]>([DEFAULT_SCENE()]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");

  // D-2 バッチキュー
  const [batchQueue, setBatchQueue] = useState<QueueItem[]>([]);

  const addToQueue = (settings: QueueItemSettings, name: string, scenesCopy: SceneItem[]) => {
    setBatchQueue(prev => [...prev, {
      id: crypto.randomUUID(),
      customerName: name,
      scenes: scenesCopy,
      settings,
      addedAt: new Date().toISOString(),
      status: "pending",
      jobId: null,
      progress: 0,
      statusMsg: "待機中",
      videoUrl: null,
      errorMsg: null,
    }]);
    const ts = new Date().toISOString().slice(0,16).replace(/[-T:]/g, "").slice(0,12);
    const base = name.replace(/_\d{8,}$/, "");
    setCustomerName(`${base}_${ts}`);
    setScenes([DEFAULT_SCENE()]);
  };

  const updateQueueItem = (id: string, updates: Partial<QueueItem>) =>
    setBatchQueue(prev => prev.map(i => i.id === id ? { ...i, ...updates } : i));

  const clearDoneQueue = () =>
    setBatchQueue(prev => prev.filter(i => i.status !== "done"));

  const removeQueueItem = (id: string) =>
    setBatchQueue(prev => prev.filter(i => i.id !== id));

  const loadPreset = (preset: ScenePreset) => {
    setCustomerName(preset.customerName);
    setScenes(preset.scenes.map(s => ({ ...s, id: crypto.randomUUID() })));
  };

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
  const queuePending = batchQueue.filter(i => i.status === "pending").length;

  const handleNewVideo = () => {
    const ts = new Date().toISOString().slice(0,16).replace(/[-T:]/g, "").slice(0,12);
    const base = customerName.replace(/_\d{8,}$/, "");
    setCustomerName(`${base}_${ts}`);
    setScenes([DEFAULT_SCENE()]);
    setTab("studio");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="min-h-screen">
      <BatchRunner queue={batchQueue} onUpdate={updateQueueItem} />
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
            <div className="hidden sm:flex items-center gap-3 text-xs text-[#8ba0bc]">
              <span>📋 {jobs.length} jobs</span>
              {runningCount > 0 && (
                <span className="flex items-center gap-1 text-blue-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 pulse-dot" />
                  {runningCount} 実行中
                </span>
              )}
              <span className="text-emerald-400">✅ {doneCount} 完了</span>
              {queuePending > 0 && (
                <span className="flex items-center gap-1 text-amber-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot" />
                  キュー {queuePending}件
                </span>
              )}
            </div>
            <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
              apiStatus === "online"
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                : apiStatus === "offline"
                ? "bg-red-500/10 text-red-400 border-red-500/30"
                : "bg-[#1f2d42] text-[#4a6080] border-[#1f2d42]"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${
                apiStatus === "online" ? "bg-emerald-400 pulse-dot" : "bg-red-400"
              }`} />
              API {apiStatus === "online" ? "オンライン" : apiStatus === "offline" ? "オフライン" : "確認中"}
            </span>
          </div>
        </div>
        <div className="max-w-6xl mx-auto px-6 flex gap-0 border-t border-[#1f2d42]">
          {([
            { key: "studio",  label: "🎬 スタジオ" },
            { key: "scene",   label: "♻️ シーン生成" },
            { key: "library", label: "📁 ライブラリ" },
            { key: "jobs",    label: `📋 ジョブ${jobs.length > 0 ? ` (${jobs.length})` : ""}` },
            { key: "batch",   label: `⚡ キュー${batchQueue.length > 0 ? ` (${batchQueue.length})` : ""}` },
          ] as { key: Tab; label: string }[]).map(({ key, label }) => (
            <button key={key} onClick={() => setTab(key)}
              className={`relative px-5 py-2.5 text-sm font-medium border-b-2 transition-all ${
                tab === key ? "border-[#3d7eff] text-[#f0f6ff]" : "border-transparent text-[#4a6080] hover:text-[#8ba0bc]"
              }`}
            >
              {label}
              {key === "batch" && queuePending > 0 && (
                <span className="absolute -top-0.5 -right-1 w-2 h-2 rounded-full bg-amber-400 pulse-dot" />
              )}
            </button>
          ))}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {tab === "studio" && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-6 items-start">
            <div className="space-y-6">
              <PresetPanel customerName={customerName} scenes={scenes} onLoad={loadPreset} />
              <section className="glass p-6 space-y-4 fade-in">
                <h2 className="text-sm font-bold text-[#8ba0bc] uppercase tracking-widest">顧客設定</h2>
                <div>
                  <label className="block text-xs font-medium text-[#4a6080] mb-1.5">顧客名 / プロジェクト名</label>
                  <input type="text" value={customerName} onChange={e => setCustomerName(e.target.value)}
                    placeholder="例: sample_company"
                    className="w-full bg-[#080c14] border border-[#1f2d42] focus:border-[#3d7eff] outline-none rounded-xl px-4 py-2.5 text-sm text-[#f0f6ff] placeholder-[#4a6080] transition-colors" />
                </div>
                <div>
                  <h3 className="text-xs font-medium text-[#4a6080] mb-3">📷 キャラクター画像アップロード</h3>
                  <AvatarUploadSection customerName={customerName} onUploaded={fetchJobs} />
                </div>
              </section>
              <section className="glass p-6 space-y-4 fade-in">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-[#8ba0bc] uppercase tracking-widest">台本エディタ</h2>
                  <span className="text-xs text-[#4a6080]">{scenes.length} シーン</span>
                </div>
                <ScriptGenerator onScriptReady={setScenes} />
                <SceneEditor scenes={scenes} onChange={setScenes} />
              </section>
            </div>
            <div className="space-y-4 lg:sticky lg:top-[115px] fade-in">
              <section className="glass p-6 space-y-5">
                <h2 className="text-sm font-bold text-[#8ba0bc] uppercase tracking-widest">🚀 動画生成</h2>
                <div className="bg-[#080c14] rounded-xl p-4 space-y-2 text-xs text-[#8ba0bc]">
                  <div className="flex justify-between"><span>顧客名</span><span className="text-[#f0f6ff] font-medium">{customerName || "未設定"}</span></div>
                  <div className="flex justify-between"><span>シーン数</span><span className="text-[#f0f6ff] font-medium">{scenes.length} シーン</span></div>
                  <div className="flex justify-between"><span>推定時間</span><span className="text-amber-400 font-medium">約 {scenes.length * 15}〜{scenes.length * 25} 分</span></div>
                  {queuePending > 0 && (
                    <div className="flex justify-between">
                      <span>キュー残</span>
                      <button onClick={() => setTab("batch")} className="text-violet-400 font-medium hover:underline">{queuePending}件待機中 →</button>
                    </div>
                  )}
                </div>
                <PipelineRunner customerName={customerName} scenes={scenes}
                  onGoToLibrary={() => setTab("library")} onNewVideo={handleNewVideo} onAddToQueue={addToQueue} />
              </section>
            </div>
          </div>
        )}
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
        {tab === "jobs" && (
          <div className="space-y-4 fade-in">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "総ジョブ", value: jobs.length, icon: "📋", color: "from-violet-500 to-indigo-500" },
                { label: "実行中",   value: runningCount, icon: "⚡", color: "from-blue-500 to-cyan-500" },
                { label: "完了",     value: doneCount, icon: "✅", color: "from-emerald-500 to-teal-500" },
                { label: "エラー",   value: jobs.filter(j => j.status === "error").length, icon: "❌", color: "from-red-500 to-rose-500" },
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
                <button onClick={fetchJobs} className="text-xs text-[#4a6080] hover:text-[#8ba0bc] transition-colors">🔄 更新</button>
              </div>
              <JobHistory jobs={jobs} loading={loadingJobs} />
            </div>
          </div>
        )}
        {tab === "library" && <div className="fade-in"><VideoLibrary /></div>}
        {tab === "batch" && (
          <div className="fade-in">
            <QueueTab queue={batchQueue} onClearDone={clearDoneQueue} onRemove={removeQueueItem} />
          </div>
        )}
      </main>
    </div>
  );
}
