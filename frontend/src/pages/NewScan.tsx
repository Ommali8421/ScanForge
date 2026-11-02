import React, { useState, useEffect } from "react";
import { UploadDropzone } from "../components/UploadDropzone";
import { ScanTypeCards } from "../components/ScanTypeCards";
import { QualitySelect } from "../components/QualitySelect";
import { FormatPicker } from "../components/FormatPicker";
import { ScanType, QualityPreset, Capabilities } from "../api/types";
import { createJob } from "../api/client";
import { useGuide } from "../context/GuideContext";
import { SmartHint } from "../components/SmartHint";
import {
  ChevronDown,
  ChevronUp,
  ArrowRight,
  CheckCircle2,
  Sliders,
  ShieldCheck,
  AlertCircle,
  FileCheck2,
} from "lucide-react";

interface Props {
  capabilities: Capabilities | null;
  onJobCreated: (jobId: string) => void;
}

export const NewScan: React.FC<Props> = ({ capabilities, onJobCreated }) => {
  const { guideEnabled } = useGuide();

  const [file, setFile] = useState<File | null>(null);
  const [scanType, setScanType] = useState<ScanType>("photo");
  const [quality, setQuality] = useState<QualityPreset>("standard");
  const [formats, setFormats] = useState<string[]>(["glb", "obj"]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    const allowed = capabilities?.format_matrix?.[scanType] || (
      scanType === "gaussian_splat"
        ? ["ply", "splat", "spz"]
        : scanType === "lidar"
        ? ["glb", "ply", "stl", "xyz"]
        : ["glb", "gltf", "obj", "fbx", "usdz", "ply", "stl", "xyz"]
    );
    const valid = formats.filter((f) => allowed.includes(f));
    const nextFormats = valid.length > 0
      ? valid
      : scanType === "gaussian_splat"
      ? ["ply", "splat"]
      : scanType === "lidar"
      ? ["glb", "ply"]
      : ["glb", "obj"];
    setFormats(nextFormats);
  }, [scanType, capabilities]);

  // Advanced options
  const [meshRoute, setMeshRoute] = useState<"auto" | "photogrammetry" | "depth_fusion">("auto");
  const [includeMesh, setIncludeMesh] = useState(false);
  const [polyTarget, setPolyTarget] = useState<number>(200000);
  const [textureSize, setTextureSize] = useState<number>(4096);
  const [upAxis, setUpAxis] = useState<"y" | "z">("y");
  const [units, setUnits] = useState<"m" | "cm" | "mm">("m");
  const [cameraModel, setCameraModel] = useState<string>("SIMPLE_RADIAL");
  const [minRegistrationRatio, setMinRegistrationRatio] = useState<number>(0.60);

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
        units: units,
        camera_model: cameraModel,
        min_registration_ratio: minRegistrationRatio,
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
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      {/* Studio Header Banner */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[11px] font-mono font-bold uppercase tracking-widest text-cyan-400 bg-cyan-500/10 px-2.5 py-0.5 rounded-full border border-cyan-500/20">
            Guided Studio Launchpad
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
          Create Spatial 3D Scan
        </h1>
        <p className="text-zinc-400 text-sm mt-1 max-w-2xl leading-relaxed">
          Upload interior video walkthroughs or photo archives to generate floor-aligned textured meshes, room dimensions, and Gaussian Splats.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* LEFT COLUMN: Main Configuration (8 cols) */}
          <div className="lg:col-span-8 space-y-6">
            {/* Step 1: Input File */}
            <section className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[11px] font-mono flex items-center justify-center">
                    1
                  </span>
                  <span>Select Room Walkthrough / Capture</span>
                </label>
                <span className="text-xs text-zinc-500 font-mono">Step 1 of 4</span>
              </div>
              <UploadDropzone
                file={file}
                onFileSelect={setFile}
                maxUploadMb={capabilities?.limits.max_upload_mb || 2048}
                maxVideoSeconds={capabilities?.limits.max_video_seconds || 600}
              />
            </section>

            {/* Step 2: Reconstruction Type */}
            <section className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[11px] font-mono flex items-center justify-center">
                    2
                  </span>
                  <span>Reconstruction Mode</span>
                </label>
                <span className="text-xs text-zinc-500 font-mono">Step 2 of 4</span>
              </div>
              <ScanTypeCards
                selected={scanType}
                onSelect={setScanType}
                lidarEnabled={capabilities?.lidar_enabled || false}
              />
            </section>

            {/* Step 3: Quality Preset */}
            <section className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[11px] font-mono flex items-center justify-center">
                    3
                  </span>
                  <span>Quality Preset</span>
                </label>
                <span className="text-xs text-zinc-500 font-mono">Step 3 of 4</span>
              </div>
              <QualitySelect selected={quality} onSelect={setQuality} />
            </section>

            {/* Step 4: Deliverables Format Picker */}
            <section className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[11px] font-mono flex items-center justify-center">
                    4
                  </span>
                  <span>Deliverable Export Formats</span>
                </label>
                <span className="text-xs text-zinc-500 font-mono">Step 4 of 4</span>
              </div>
              <FormatPicker
                scanType={scanType}
                selectedFormats={formats}
                onChange={setFormats}
                capabilities={capabilities}
              />
            </section>

            {/* Collapsible Advanced Reconstruction Settings */}
            <section className="bg-zinc-950/80 border border-zinc-800 rounded-3xl overflow-hidden shadow-xl">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-zinc-900/60 transition-colors"
              >
                <div className="flex items-center gap-2.5">
                  <Sliders className="w-4 h-4 text-cyan-400" />
                  <span className="text-sm font-bold text-white">
                    Advanced Reconstruction Settings
                  </span>
                  <span className="text-xs text-zinc-500 font-normal hidden sm:inline">
                    (Mesh routes, polycount target, UV atlas, up-axis)
                  </span>
                </div>
                {showAdvanced ? (
                  <ChevronUp className="w-4 h-4 text-zinc-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-zinc-400" />
                )}
              </button>

              {showAdvanced && (
                <div className="p-6 pt-2 border-t border-zinc-800/80 space-y-5 text-xs text-zinc-300">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* Mesh Route (Photo Scan) */}
                    {scanType === "photo" && (
                      <div>
                        <label className="block text-zinc-400 mb-1.5 font-semibold">
                          Mesh Reconstruction Route:
                        </label>
                        <select
                          value={meshRoute}
                          onChange={(e) => setMeshRoute(e.target.value as any)}
                          className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 text-xs"
                        >
                          <option value="auto">Auto (Evaluates texture variance)</option>
                          <option value="photogrammetry">Route A: Photogrammetry (COLMAP + OpenMVS)</option>
                          <option value="depth_fusion">Route B: Depth Fusion (Neural Depth + TSDF)</option>
                        </select>
                      </div>
                    )}

                    {/* 3DGS Extract Mesh Toggle */}
                    {scanType === "gaussian_splat" && (
                      <div>
                        <label className="block text-zinc-400 mb-1.5 font-semibold">
                          Extract Mesh from Splat:
                        </label>
                        <label className="flex items-center space-x-2.5 mt-2 cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={includeMesh}
                            onChange={(e) => setIncludeMesh(e.target.checked)}
                            className="rounded border-zinc-700 text-indigo-600 focus:ring-0 bg-zinc-900 w-4 h-4"
                          />
                          <span className="text-white font-medium">
                            Generate textured mesh (TSDF Splat Mesher)
                          </span>
                        </label>
                      </div>
                    )}

                    {/* Target Face Count */}
                    <div>
                      <label className="block text-zinc-400 mb-1.5 font-semibold">
                        Target Face Count:
                      </label>
                      <select
                        value={polyTarget}
                        onChange={(e) => setPolyTarget(Number(e.target.value))}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 text-xs font-mono"
                      >
                        <option value={50000}>Draft Decimation (~50,000 faces)</option>
                        <option value={200000}>Standard Decimation (~200,000 faces) — Default</option>
                        <option value={1000000}>High Fidelity (~1,000,000 faces)</option>
                      </select>
                    </div>

                    {/* Texture Atlas Size */}
                    <div>
                      <label className="block text-zinc-400 mb-1.5 font-semibold">
                        Texture Atlas Resolution:
                      </label>
                      <select
                        value={textureSize}
                        onChange={(e) => setTextureSize(Number(e.target.value))}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 text-xs font-mono"
                      >
                        <option value={1024}>1K (1024 × 1024)</option>
                        <option value={2048}>2K (2048 × 2048)</option>
                        <option value={4096}>4K (4096 × 4096) — Recommended Sharpness</option>
                        <option value={8192}>8K (8192 × 8192)</option>
                      </select>
                    </div>

                    {/* Up-Axis Alignment */}
                    <div>
                      <label className="block text-zinc-400 mb-1.5 font-semibold">
                        Up-Axis Alignment:
                      </label>
                      <select
                        value={upAxis}
                        onChange={(e) => setUpAxis(e.target.value as any)}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 text-xs font-mono"
                      >
                        <option value="y">Y-Up (OpenGL / Three.js / Web standard)</option>
                        <option value="z">Z-Up (Blender / Unreal Engine standard)</option>
                      </select>
                    </div>

                    {/* Units */}
                    <div>
                      <label className="block text-zinc-400 mb-1.5 font-semibold">
                        System Units:
                      </label>
                      <select
                        value={units}
                        onChange={(e) => setUnits(e.target.value as any)}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 text-xs font-mono"
                      >
                        <option value="m">Meters (m) — Architectural Standard</option>
                        <option value="cm">Centimeters (cm)</option>
                        <option value="mm">Millimeters (mm)</option>
                      </select>
                    </div>

                    {/* Camera Model */}
                    <div>
                      <label className="block text-zinc-400 mb-1.5 font-semibold">
                        Camera Lens Model:
                      </label>
                      <select
                        value={cameraModel}
                        onChange={(e) => setCameraModel(e.target.value)}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500 font-mono text-[11px]"
                      >
                        <option value="SIMPLE_RADIAL">SIMPLE_RADIAL (Default — 1 focal, 1 radial)</option>
                        <option value="OPENCV">OPENCV (8 params — recommended for wide-angle)</option>
                        <option value="RADIAL">RADIAL (1 focal, 2 radial)</option>
                        <option value="PINHOLE">PINHOLE (fx, fy, cx, cy — no distortion)</option>
                      </select>
                    </div>

                    {/* Min Registration Ratio */}
                    <div className="sm:col-span-2 border-t border-zinc-800/80 pt-3 mt-1">
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-zinc-400 font-semibold">
                          Minimum Frame Registration Ratio:
                        </label>
                        <span className="font-mono text-cyan-400 font-bold text-xs">
                          {(minRegistrationRatio * 100).toFixed(0)}%
                        </span>
                      </div>
                      <input
                        type="range"
                        min="0.10"
                        max="1.00"
                        step="0.05"
                        value={minRegistrationRatio}
                        onChange={(e) => setMinRegistrationRatio(parseFloat(e.target.value))}
                        className="w-full accent-indigo-500 cursor-pointer"
                      />
                      <div className="flex justify-between text-[10px] text-zinc-500 font-mono mt-1">
                        <span>10% (Permissive / Partial)</span>
                        <span className="text-zinc-300 font-medium">60% (Default Target)</span>
                        <span>90% (Strict)</span>
                      </div>
                      <p className="text-[11px] text-zinc-500 mt-1.5">
                        Reconstruction checks registration completeness against this threshold. Set to 30% to accept partial models on low-texture or quickly-panned captures.
                      </p>
                    </div>
                  </div>

                  <SmartHint
                    topic="Mesh Route Guidance"
                    hint="Auto analyzes frame texture variance: high-texture rooms use Photogrammetry (Route A) for sharp corners, while featureless drywall rooms use Depth Fusion (Route B) to prevent holes."
                    guideTab={2}
                  />
                </div>
              )}
            </section>
          </div>

          {/* RIGHT COLUMN: Sticky Summary & Launch Rail (4 cols) */}
          <div className="lg:col-span-4 sticky top-20 space-y-4">
            {/* Reconstruction Summary Card */}
            <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2">
                  <FileCheck2 className="w-4 h-4 text-cyan-400" />
                  Configuration Summary
                </h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-bold uppercase">
                  {scanType.replace("_", " ")}
                </span>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between items-center py-1 border-b border-zinc-900">
                  <span className="text-zinc-400">File Selected:</span>
                  <span className="font-mono text-zinc-200 font-medium truncate max-w-[150px]">
                    {file ? file.name : "None chosen"}
                  </span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-zinc-900">
                  <span className="text-zinc-400">Quality Preset:</span>
                  <span className="font-semibold text-white capitalize">{quality}</span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-zinc-900">
                  <span className="text-zinc-400">Target Polycount:</span>
                  <span className="font-mono text-zinc-300">{(polyTarget / 1000).toFixed(0)}k faces</span>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-zinc-900">
                  <span className="text-zinc-400">Atlas Resolution:</span>
                  <span className="font-mono text-zinc-300">{textureSize} × {textureSize}</span>
                </div>
                <div>
                  <span className="text-zinc-400 block mb-1.5">Selected Deliverables:</span>
                  <div className="flex flex-wrap gap-1">
                    {formats
                      .filter((fmt) => {
                        const allowed = capabilities?.format_matrix?.[scanType] || (
                          scanType === "gaussian_splat"
                            ? ["ply", "splat", "spz"]
                            : scanType === "lidar"
                            ? ["glb", "ply", "stl", "xyz"]
                            : ["glb", "gltf", "obj", "fbx", "usdz", "ply", "stl", "xyz"]
                        );
                        return allowed.includes(fmt);
                      })
                      .map((fmt) => (
                      <span
                        key={fmt}
                        className="px-2 py-0.5 rounded-md text-[10px] font-mono uppercase bg-zinc-900 text-cyan-300 border border-zinc-800 font-bold"
                      >
                        {fmt}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Capture Quality Checklist (Active when Guide is ON) */}
            {guideEnabled && (
              <div className="bg-indigo-950/20 border border-indigo-500/20 rounded-3xl p-5 shadow-lg space-y-2.5">
                <div className="flex items-center gap-1.5 text-xs font-bold text-white">
                  <ShieldCheck className="w-4 h-4 text-cyan-400" />
                  <span>Pre-Flight Capture Checklist</span>
                </div>
                <ul className="text-xs space-y-1.5 text-zinc-300">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>All interior lights turned ON</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>Slow sideways walking (no tripod spinning)</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>Locked camera exposure & focus</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>Corners/moldings framed across blank walls</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                    <span>Looped trajectory back to start</span>
                  </li>
                </ul>
              </div>
            )}

            {/* Error Message */}
            {errorMsg && (
              <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-rose-300 text-xs font-medium flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                <span>{errorMsg}</span>
              </div>
            )}

            {/* Upload Progress & CTA Launch Button */}
            <div className="space-y-3 pt-1">
              {uploading ? (
                <div className="bg-zinc-950 border border-zinc-800 p-5 rounded-3xl space-y-3 shadow-xl">
                  <div className="flex justify-between text-xs font-mono">
                    <span className="text-zinc-400">Streaming capture to disk...</span>
                    <span className="text-cyan-400 font-bold tabular-nums">{uploadPercent}%</span>
                  </div>
                  <div className="w-full bg-zinc-900 h-2.5 rounded-full overflow-hidden border border-zinc-800">
                    <div
                      className="bg-gradient-to-r from-indigo-600 via-cyan-500 to-emerald-400 h-full transition-all duration-150 rounded-full shadow-md shadow-cyan-500/20"
                      style={{ width: `${uploadPercent}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-zinc-500">
                    Safe multipart stream • Bypassing RAM bottlenecks
                  </p>
                </div>
              ) : (
                <button
                  type="submit"
                  disabled={!file}
                  className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-500 hover:from-indigo-500 hover:to-cyan-400 text-white font-bold text-sm shadow-xl shadow-indigo-600/25 disabled:opacity-40 disabled:cursor-not-allowed transition-all transform active:scale-[0.99] flex items-center justify-center gap-2 select-none"
                >
                  <span>Launch 3D Reconstruction</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      </form>
    </div>
  );
};
