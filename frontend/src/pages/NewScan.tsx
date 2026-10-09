import React, { useState } from "react";
import { UploadDropzone } from "../components/UploadDropzone";
import { ScanTypeCards } from "../components/ScanTypeCards";
import { QualitySelect } from "../components/QualitySelect";
import { FormatPicker } from "../components/FormatPicker";
import { ScanType, QualityPreset, Capabilities } from "../api/types";
import { createJob } from "../api/client";
import { ChevronDown, ChevronUp, HelpCircle, ArrowRight } from "lucide-react";


interface Props {
  capabilities: Capabilities | null;
  onJobCreated: (jobId: string) => void;
}

export const NewScan: React.FC<Props> = ({ capabilities, onJobCreated }) => {
  const [file, setFile] = useState<File | null>(null);
  const [scanType, setScanType] = useState<ScanType>("photo");
  const [quality, setQuality] = useState<QualityPreset>("standard");
  const [formats, setFormats] = useState<string[]>(["glb", "obj"]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Advanced options
  const [meshRoute, setMeshRoute] = useState<"auto" | "photogrammetry" | "depth_fusion">("auto");
  const [includeMesh, setIncludeMesh] = useState(false);
  const [polyTarget, setPolyTarget] = useState<number>(200000);
  const [textureSize, setTextureSize] = useState<number>(4096);
  const [upAxis, setUpAxis] = useState<"y" | "z">("y");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setErrorMsg("Please select a video file or photo zip archive.");
      return;
    }

    setUploading(true);
    setErrorMsg(null);
    setUploadPercent(0);

    try {
      const options = {
        mesh_route: meshRoute,
        include_mesh: includeMesh,
        poly_target: polyTarget,
        texture_size: textureSize,
        up_axis: upAxis,
        units: "m",
      };

      const res = await createJob(
        file,
        scanType,
        quality,
        formats,
        options,
        (pct) => setUploadPercent(pct)
      );

      onJobCreated(res.job_id);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed creating scan job");
      setUploading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6">
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
          Create New 3D Scan
        </h1>
        <p className="text-dark-muted text-sm mt-1">
          Upload interior video walkthroughs or photo archives to generate textured meshes and Gaussian Splats.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Upload Dropzone */}
        <div className="bg-dark-card border border-dark-border rounded-2xl p-6 shadow-lg">
          <label className="block text-sm font-semibold text-white mb-3">1. Select Input File</label>
          <UploadDropzone
            file={file}
            onFileSelect={setFile}
            maxUploadMb={capabilities?.limits.max_upload_mb || 2048}
          />
        </div>

        {/* Scan Type Selection */}
        <div className="bg-dark-card border border-dark-border rounded-2xl p-6 shadow-lg">
          <label className="block text-sm font-semibold text-white mb-3">2. Reconstruction Type</label>
          <ScanTypeCards
            selected={scanType}
            onSelect={setScanType}
            lidarEnabled={capabilities?.lidar_enabled || false}
          />
        </div>

        {/* Quality Preset */}
        <div className="bg-dark-card border border-dark-border rounded-2xl p-6 shadow-lg">
          <label className="block text-sm font-semibold text-white mb-3">3. Quality Preset</label>
          <QualitySelect selected={quality} onSelect={setQuality} />
        </div>

        {/* Export Formats */}
        <div className="bg-dark-card border border-dark-border rounded-2xl p-6 shadow-lg">
          <label className="block text-sm font-semibold text-white mb-3">4. Desired Export Formats</label>
          <FormatPicker
            scanType={scanType}
            selectedFormats={formats}
            onChange={setFormats}
            capabilities={capabilities}
          />
        </div>

        {/* Collapsible Advanced Options */}
        <div className="bg-dark-card border border-dark-border rounded-2xl overflow-hidden shadow-lg">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-dark-hover transition-colors"
          >
            <span className="text-sm font-semibold text-white flex items-center gap-2">
              Advanced Reconstruction Settings
              <span className="text-xs text-dark-muted font-normal">(Mesh routes, polycount, texturing)</span>
            </span>
            {showAdvanced ? (
              <ChevronUp className="w-4 h-4 text-dark-muted" />
            ) : (
              <ChevronDown className="w-4 h-4 text-dark-muted" />
            )}
          </button>

          {showAdvanced && (
            <div className="p-6 pt-2 border-t border-dark-border space-y-4 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {scanType === "photo" && (
                  <div>
                    <label className="block text-dark-muted mb-1.5 font-medium">Reconstruction Route:</label>
                    <select
                      value={meshRoute}
                      onChange={(e) => setMeshRoute(e.target.value as any)}
                      className="w-full bg-dark-bg border border-dark-border rounded-xl px-3 py-2 text-white focus:outline-none focus:border-brand-500"
                    >
                      <option value="auto">Auto Heuristic (Evaluates texture variance)</option>
                      <option value="photogrammetry">Route A: Photogrammetry (COLMAP + OpenMVS)</option>
                      <option value="depth_fusion">Route B: Depth Fusion (Monocular Depth + TSDF)</option>
                    </select>
                  </div>
                )}

                {scanType === "gaussian_splat" && (
                  <div>
                    <label className="block text-dark-muted mb-1.5 font-medium">Extract Mesh from Splat:</label>
                    <label className="flex items-center space-x-2 mt-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={includeMesh}
                        onChange={(e) => setIncludeMesh(e.target.checked)}
                        className="rounded border-dark-border text-brand-500 focus:ring-0 bg-dark-bg w-4 h-4"
                      />
                      <span className="text-white">Generate textured mesh (TSDF Splat Mesher)</span>
                    </label>
                  </div>
                )}

                <div>
                  <label className="block text-dark-muted mb-1.5 font-medium">Target Face Count:</label>
                  <select
                    value={polyTarget}
                    onChange={(e) => setPolyTarget(Number(e.target.value))}
                    className="w-full bg-dark-bg border border-dark-border rounded-xl px-3 py-2 text-white focus:outline-none focus:border-brand-500"
                  >
                    <option value={50000}>Draft Decimation (~50,000 faces)</option>
                    <option value={200000}>Standard Decimation (~200,000 faces)</option>
                    <option value={1000000}>High Fidelity (~1,000,000 faces)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-dark-muted mb-1.5 font-medium">Texture Atlas Resolution:</label>
                  <select
                    value={textureSize}
                    onChange={(e) => setTextureSize(Number(e.target.value))}
                    className="w-full bg-dark-bg border border-dark-border rounded-xl px-3 py-2 text-white focus:outline-none focus:border-brand-500"
                  >
                    <option value={1024}>1K (1024 × 1024)</option>
                    <option value={2048}>2K (2048 × 2048)</option>
                    <option value={4096}>4K (4096 × 4096) — Recommended</option>
                    <option value={8192}>8K (8192 × 8192)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-dark-muted mb-1.5 font-medium">Up-Axis Alignment:</label>
                  <select
                    value={upAxis}
                    onChange={(e) => setUpAxis(e.target.value as any)}
                    className="w-full bg-dark-bg border border-dark-border rounded-xl px-3 py-2 text-white focus:outline-none focus:border-brand-500"
                  >
                    <option value="y">Y-Up (OpenGL / Three.js standard)</option>
                    <option value="z">Z-Up (Blender / Unreal standard)</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Interior Capture Tips Banner */}
        <div className="bg-brand-500/10 border border-brand-500/20 rounded-2xl p-4 flex items-start gap-3 text-xs text-brand-200">
          <HelpCircle className="w-5 h-5 flex-shrink-0 text-brand-400 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-white">Interior Scanning Tips:</p>
            <p>
              Walk slowly along the perimeter of the room facing inwards. Keep lighting uniform and avoid rapid rotational movements.
            </p>
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-xs font-medium">
            {errorMsg}
          </div>
        )}

        {/* Upload Progress Bar & Submit Button */}
        <div>
          {uploading ? (
            <div className="bg-dark-card border border-dark-border p-4 rounded-2xl space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-dark-muted">Streaming upload to disk...</span>
                <span className="text-brand-400 font-bold">{uploadPercent}%</span>
              </div>
              <div className="w-full bg-dark-bg h-2 rounded-full overflow-hidden border border-dark-border">
                <div
                  className="bg-brand-500 h-full transition-all duration-150 rounded-full"
                  style={{ width: `${uploadPercent}%` }}
                />
              </div>
            </div>
          ) : (
            <button
              type="submit"
              disabled={!file}
              className="w-full py-3.5 px-6 rounded-2xl bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-lg shadow-brand-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
            >
              <span>Start Reconstruction</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
};
