import React, { useRef, useState } from "react";
import { UploadCloud, FileVideo, Archive, X } from "lucide-react";

interface Props {
  file: File | null;
  onFileSelect: (file: File | null) => void;
  maxUploadMb: number;
}

export const UploadDropzone: React.FC<Props> = ({ file, onFileSelect, maxUploadMb }) => {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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
          className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
            isDragging
              ? "border-brand-500 bg-brand-500/10"
              : "border-dark-border bg-dark-card hover:border-slate-600 hover:bg-dark-hover"
          }`}
        >
          <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-brand-500/10 flex items-center justify-center text-brand-400">
            <UploadCloud className="w-6 h-6" />
          </div>
          <p className="text-sm font-semibold text-white mb-1">
            Click to upload or drag & drop room capture
          </p>
          <p className="text-xs text-dark-muted mb-2">
            MP4, MOV video walkthrough or ZIP archive of photos / RGB-D frames
          </p>
          <span className="inline-block text-[11px] text-dark-muted bg-dark-bg px-2.5 py-1 rounded-full border border-dark-border">
            Max upload limit: {maxUploadMb} MB
          </span>
        </div>
      ) : (
        <div className="border border-dark-border bg-dark-card rounded-2xl p-4 flex items-center justify-between">
          <div className="flex items-center space-x-3 overflow-hidden">
            <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center text-brand-400 flex-shrink-0">
              {file.name.endsWith(".zip") || file.name.endsWith(".r3d") ? (
                <Archive className="w-5 h-5" />
              ) : (
                <FileVideo className="w-5 h-5" />
              )}
            </div>
            <div className="truncate">
              <p className="text-sm font-medium text-white truncate">{file.name}</p>
              <p className="text-xs text-dark-muted">{formatFileSize(file.size)}</p>
            </div>
          </div>
          <button
            onClick={() => onFileSelect(null)}
            className="p-1.5 rounded-lg text-dark-muted hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};
