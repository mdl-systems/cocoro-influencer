"use client";

function ProgressBar({ value, label, running }: { value: number; label?: string; running?: boolean }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-center text-xs text-[#8ba0bc]">
        <span className="truncate max-w-[70%]">{label || "処理中..."}</span>
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

export default ProgressBar;
