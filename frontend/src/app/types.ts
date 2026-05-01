// Shared types and constants (auto-extracted from page.tsx)

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
  pose: "neutral" | "talking" | "greeting" | "presenting" | "thinking" | "walk" | "pointing";
  camera_angle: "close_up" | "upper_body" | "full_body";
  cinematic_prompt: string;
}

// D-1 プリセット
interface ScenePreset {
  id: string;
  name: string;
  createdAt: string;
  customerName: string;
  scenes: SceneItem[];
}

// D-2 バッチキュー
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

export type { VideoItem, Job, SceneItem, ScenePreset, QueueItemSettings, QueueItem, SceneJobState };
export { JOB_TYPE_LABELS, STATUS_STYLE };
