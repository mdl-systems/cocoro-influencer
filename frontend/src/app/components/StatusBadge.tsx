"use client";

import { STATUS_STYLE } from "../types";

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

export default StatusBadge;
