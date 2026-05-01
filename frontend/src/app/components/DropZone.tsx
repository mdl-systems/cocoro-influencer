"use client";

import { useCallback, useRef, useState } from "react";

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
        <div className="text-4xl mb-2">📷</div>
      )}
      <p className={`text-sm font-semibold ${accent}`}>{label}</p>
      <p className="text-xs text-[#4a6080] mt-0.5">{sublabel}</p>
    </div>
  );
}

export default DropZone;
