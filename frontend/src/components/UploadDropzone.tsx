import React, { useRef, useState, useEffect } from "react";
import { UploadCloud, FileVideo, Archive, X, AlertTriangle, Film, CheckCircle2 } from "lucide-react";

interface Props {
  file: File | null;
  onFileSelect: (file: File | null) => void;
  maxUploadMb: number;
  maxVideoSeconds?: number;
}

export const UploadDropzone: React.FC<Props> = ({
  file,
  onFileSelect,
  maxUploadMb,
  maxVideoSeconds = 600,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [videoMeta, setVideoMeta] = useState<{ duration?: number; width?: number; height?: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Pre-flight video metadata extraction
  useEffect(() => {
    if (!file) {
      setVideoMeta(null);
      return;
    }

    const isVideo = file.type.startsWith("video/") || /\.(mp4|mov|m4v|avi)$/i.test(file.name);
    if (!isVideo) {
      setVideoMeta(null);
      return;
    }

    try {
      const url = URL.createObjectURL(file);
      const video = document.createElement("video");
      video.preload = "metadata";
      video.onloadedmetadata = () => {
        setVideoMeta({
          duration: Math.round(video.duration),
          width: video.videoWidth,
          height: video.videoHeight,
        });
        URL.revokeObjectURL(url);
      };
      video.onerror = () => {
        URL.revokeObjectURL(url);
      };
      video.src = url;
    } catch {
      setVideoMeta(null);
    }
  }, [file]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      onFileSelect(e.dataTransfer.files[0]);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const fileSizeMb = file ? file.size / (1024 * 1024) : 0;
  const isNearLimit = fileSizeMb > maxUploadMb * 0.9;
  const isOverLimit = fileSizeMb > maxUploadMb;
  const isDurationOver = videoMeta?.duration && videoMeta.duration > maxVideoSeconds;

  return (
    <div className="w-full">
      <input
        ref={inputRef}
        type="file"
        accept=".mp4,.mov,.m4v,.avi,.zip,.r3d"
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            onFileSelect(e.target.files[0]);
          }
        }}
      />

      {!file ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`border-2 border-dashed rounded-3xl p-8 sm:p-10 text-center cursor-pointer transition-all duration-200 relative group overflow-hidden ${
            isDragging
              ? "border-indigo-500 bg-indigo-500/10 shadow-xl shadow-indigo-500/10 scale-[1.01]"
              : "border-zinc-800 bg-zinc-950/60 hover:border-indigo-500/60 hover:bg-zinc-900/60"
          }`}
        >
          {/* Subtle ambient hover radial glow */}
          <div className="absolute inset-0 bg-radial-gradient from-indigo-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

          <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 group-hover:scale-110 group-hover:text-cyan-400 transition-all shadow-md shadow-indigo-500/10">
            <UploadCloud className="w-7 h-7" />
          </div>

          <h3 className="text-sm sm:text-base font-bold text-white mb-1.5 tracking-tight">
            Click to upload or drag & drop room capture
          </h3>
          <p className="text-xs text-zinc-400 mb-4 max-w-md mx-auto leading-relaxed">
            Accepts <span className="text-zinc-200 font-medium">MP4, MOV</span> walkthrough video or{" "}
            <span className="text-zinc-200 font-medium">ZIP</span> photo archive / iOS Record3D{" "}
            <span className="text-zinc-200 font-medium">.r3d</span>
          </p>

          <div className="inline-flex flex-wrap items-center justify-center gap-2 text-[11px] font-mono text-zinc-400 bg-zinc-900/90 px-3.5 py-1.5 rounded-full border border-zinc-800 shadow-inner">
            <span>Limit: <strong className="text-zinc-200">{maxUploadMb} MB</strong></span>
            <span>•</span>
            <span>Duration: <strong className="text-zinc-200">≤ {maxVideoSeconds}s</strong> ({Math.round(maxVideoSeconds / 60)} min)</span>
          </div>
        </div>
      ) : (
        <div className="border border-zinc-800 bg-zinc-950/80 rounded-3xl p-5 shadow-xl space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center space-x-3.5 overflow-hidden min-w-0">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600/30 to-cyan-500/20 border border-indigo-500/40 flex items-center justify-center text-cyan-300 flex-shrink-0 shadow-md shadow-indigo-500/10">
                {file.name.endsWith(".zip") || file.name.endsWith(".r3d") ? (
                  <Archive className="w-6 h-6" />
                ) : (
                  <FileVideo className="w-6 h-6" />
                )}
              </div>

              <div className="truncate">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-bold text-white truncate tracking-tight">
                    {file.name}
                  </p>
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold uppercase tracking-wider bg-zinc-800 text-zinc-300 border border-zinc-700">
                    {file.name.split(".").pop() || "FILE"}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-zinc-400 mt-1 font-mono">
                  <span className="text-indigo-300 font-semibold tabular-nums">
                    {formatFileSize(file.size)}
                  </span>
                  {videoMeta && (
                    <>
                      <span>•</span>
                      <span className="flex items-center gap-1 text-zinc-300">
                        <Film className="w-3 h-3 text-cyan-400" />
                        {videoMeta.duration}s
                      </span>
                      {videoMeta.width && videoMeta.height && (
                        <>
                          <span>•</span>
                          <span>{videoMeta.width}×{videoMeta.height}</span>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={() => onFileSelect(null)}
              className="p-2 rounded-xl text-zinc-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors flex-shrink-0"
              title="Remove file"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Pre-flight Warnings */}
          {(isOverLimit || isNearLimit || isDurationOver) && (
            <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-2xl flex items-start gap-2.5 text-xs text-amber-200">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                {isOverLimit && (
                  <p className="font-semibold text-rose-300">
                    File exceeds maximum upload limit ({maxUploadMb} MB). Upload may be rejected.
                  </p>
                )}
                {!isOverLimit && isNearLimit && (
                  <p>
                    File is near the upload limit ({fileSizeMb.toFixed(1)} / {maxUploadMb} MB). Ensure connection is stable.
                  </p>
                )}
                {isDurationOver && (
                  <p className="mt-0.5">
                    Video duration ({videoMeta?.duration}s) exceeds recommendation ({maxVideoSeconds}s). Frames will be capped adaptively.
                  </p>
                )}
              </div>
            </div>
          )}

          {!isOverLimit && !isDurationOver && (
            <div className="flex items-center gap-1.5 text-[11px] text-emerald-400 px-1 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Pre-flight checks passed • Ready for GPU ingest</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
