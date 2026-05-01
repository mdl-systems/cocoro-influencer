"use client";

import { Job, JOB_TYPE_LABELS } from "../types";
import StatusBadge from "./StatusBadge";

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


export default JobHistory;
