import React, { useEffect, useRef, useState } from "react";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import {
  Download,
  RotateCw,
  AlertTriangle,
  Sliders,
  Footprints,
  Palette,
} from "lucide-react";

export type SplatTheme = "dark-slate" | "deep-void" | "studio-grey" | "white";

interface CropBox {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

interface Props {
  splatUrl: string; // URL to .splat, .ply, or .spz
  jobId?: string;
  splatCount?: number;
  onDownload?: (format: string) => void;
  availableFormats?: string[];
}

export const SplatViewer: React.FC<Props> = ({
  splatUrl,
  jobId: _jobId,
  splatCount,
  onDownload,
  availableFormats = ["splat", "ply", "zip"],
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [theme, setTheme] = useState<SplatTheme>("dark-slate");
  const [splatScale, setSplatScale] = useState(1.0);
  const [walkMode, setWalkMode] = useState(false);
  const [showCropPanel, setShowCropPanel] = useState(false);

  // 6-slider crop box state
  const [cropBox, setCropBox] = useState<CropBox>({
    minX: -10,
    maxX: 10,
    minY: -0.5,
    maxY: 6,
    minZ: -10,
    maxZ: 10,
  });

  const getThemeBg = (t: SplatTheme) => {
    switch (t) {
      case "deep-void":
        return "#000000";
      case "studio-grey":
        return "#1e293b";
      case "white":
        return "#ffffff";
      case "dark-slate":
      default:
        return "#090d16";
    }
  };

  const cycleTheme = () => {
    setTheme((prev) => {
      if (prev === "dark-slate") return "studio-grey";
      if (prev === "studio-grey") return "deep-void";
      if (prev === "deep-void") return "white";
      return "dark-slate";
    });
  };

  // Initialize GaussianSplats3D.Viewer
  useEffect(() => {
    if (!containerRef.current || !splatUrl) return;

    setLoading(true);
    setLoadError(null);

    let disposed = false;
    let viewer: any = null;

    try {
      // Determine format from URL with explicit fallback
      let format = GaussianSplats3D.SceneFormat.Splat;
      const lower = splatUrl.toLowerCase();
      if (lower.endsWith(".ply") || lower.includes("/ply") || lower.includes("format=ply")) {
        format = GaussianSplats3D.SceneFormat.Ply;
      } else if (lower.endsWith(".spz") || lower.includes("/spz") || lower.includes("format=spz")) {
        format = GaussianSplats3D.SceneFormat.Spz;
      } else if (lower.endsWith(".ksplat") || lower.includes("/ksplat")) {
        format = GaussianSplats3D.SceneFormat.KSplat;
      } else {
        format = GaussianSplats3D.SceneFormat.Splat;
      }

      viewer = new GaussianSplats3D.Viewer({
        rootElement: containerRef.current,
        cameraUp: [0, 1, 0],
        initialCameraPosition: [0, 1.6, 3.5],
        initialCameraLookAt: [0, 1.0, 0],
        sharedMemoryForWorkers: false, // Prevents Chrome/Edge SharedArrayBuffer crashes
        selfDrivenMode: true,
        useBuiltInControls: true,
      });

      viewerRef.current = viewer;

      viewer
        .addSplatScene(splatUrl, {
          format,
          splatAlphaRemovalThreshold: 5,
          showLoadingUI: false,
          position: [0, 0, 0],
          rotation: [0, 0, 0, 1],
          scale: [1, 1, 1],
        })
        .then(() => {
          if (!disposed) {
            setLoading(false);
          }
        })
        .catch((err: any) => {
          if (!disposed) {
            console.error("GaussianSplats3D viewer scene load error:", err);
            setLoadError(`Failed to render 3D Gaussian Splat: ${err?.message || err}`);
            setLoading(false);
          }
        });
    } catch (err: any) {
      console.error("GaussianSplats3D initialization error:", err);
      setLoadError(`Failed to initialize 3DGS WebGL Viewer: ${err?.message || err}`);
      setLoading(false);
    }

    return () => {
      disposed = true;
      if (viewer) {
        try {
          viewer.dispose();
        } catch (e) {
          console.debug("Viewer dispose exception:", e);
        }
      }
      viewerRef.current = null;
    };
  }, [splatUrl]);

  // WASD walk mode key listeners
  useEffect(() => {
    if (!walkMode || !viewerRef.current) return;

    const moveSpeed = 0.1;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!viewerRef.current?.camera) return;
      const cam = viewerRef.current.camera;
      const forward = new Float32Array(3);
      // Direction camera is facing (horizontal projection)
      forward[0] = -cam.matrix.elements[8];
      forward[1] = 0;
      forward[2] = -cam.matrix.elements[10];
      const len = Math.sqrt(forward[0] * forward[0] + forward[2] * forward[2]) || 1.0;
      forward[0] /= len;
      forward[2] /= len;

      const right = new Float32Array(3);
      right[0] = cam.matrix.elements[0];
      right[1] = 0;
      right[2] = cam.matrix.elements[2];
      const rlen = Math.sqrt(right[0] * right[0] + right[2] * right[2]) || 1.0;
      right[0] /= rlen;
      right[2] /= rlen;

      switch (e.key.toLowerCase()) {
        case "w":
          cam.position.x += forward[0] * moveSpeed;
          cam.position.z += forward[2] * moveSpeed;
          break;
        case "s":
          cam.position.x -= forward[0] * moveSpeed;
          cam.position.z -= forward[2] * moveSpeed;
          break;
        case "a":
          cam.position.x -= right[0] * moveSpeed;
          cam.position.z -= right[2] * moveSpeed;
          break;
        case "d":
          cam.position.x += right[0] * moveSpeed;
          cam.position.z += right[2] * moveSpeed;
          break;
        case "q":
          cam.position.y += moveSpeed;
          break;
        case "e":
          cam.position.y -= moveSpeed;
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [walkMode]);

  const handleResetView = () => {
    if (viewerRef.current?.camera) {
      viewerRef.current.camera.position.set(0, 1.6, 3.5);
      if (viewerRef.current.controls?.target) {
        viewerRef.current.controls.target.set(0, 1.0, 0);
      }
    }
  };

  const handleSplatScaleChange = (val: number) => {
    setSplatScale(val);
    if (viewerRef.current?.splatMesh) {
      try {
        viewerRef.current.splatMesh.splatScale = val;
      } catch (e) {
        console.debug("splatScale update:", e);
      }
    }
  };

  return (
    <div
      className="relative w-full h-[650px] lg:h-[750px] rounded-3xl overflow-hidden border border-zinc-800/80 shadow-2xl transition-colors duration-300"
      style={{ backgroundColor: getThemeBg(theme) }}
    >
      {/* 3DGS Canvas Container */}
      <div ref={containerRef} className="absolute inset-0 w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Loading Overlay */}
      {loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950/70 backdrop-blur-md z-30 transition-opacity">
          <div className="w-12 h-12 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mb-4" />
          <p className="text-sm font-mono text-zinc-300 tracking-wider">
            Streaming 3D Gaussian Splats...
          </p>
          <span className="text-xs font-mono text-zinc-500 mt-1">
            Y=0 floor aligned • 32-byte web stream
          </span>
        </div>
      )}

      {/* Error Card */}
      {loadError && (
        <div className="absolute inset-x-6 top-6 z-40 max-w-lg mx-auto p-4 rounded-2xl bg-rose-950/80 border border-rose-800 text-rose-200 text-xs backdrop-blur-md flex items-start space-x-3 shadow-2xl">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 text-rose-400 mt-0.5" />
          <div>
            <h4 className="font-bold text-rose-300">Splat Rendering Error</h4>
            <p className="mt-1 text-rose-300/80 font-mono leading-relaxed">{loadError}</p>
          </div>
        </div>
      )}

      {/* Top Left Status & HUD Badge */}
      <div className="absolute top-5 left-5 z-20 flex flex-col space-y-2 pointer-events-none">
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-xl bg-zinc-900/80 border border-zinc-700/80 backdrop-blur-md shadow-lg pointer-events-auto">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-bold text-zinc-200 tracking-tight">3DGS Splat Studio</span>
          <span className="text-zinc-500 text-xs">•</span>
          <span className="text-xs font-mono text-cyan-400">
            {splatCount ? `${splatCount.toLocaleString()} splats` : "Native 32-byte stream"}
          </span>
        </div>
        <div className="text-[11px] font-mono text-zinc-400/90 px-3 py-1 rounded-lg bg-zinc-950/60 backdrop-blur-sm border border-zinc-800/60 w-fit">
          Up: +Y (0, 1, 0) • Floor flush at Y=0.000m
        </div>
      </div>

      {/* Top Right Actions Toolbar */}
      <div className="absolute top-5 right-5 z-20 flex items-center space-x-2">
        {/* Walk mode toggle */}
        <button
          onClick={() => setWalkMode(!walkMode)}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-lg backdrop-blur-md border ${
            walkMode
              ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-cyan-500/20"
              : "bg-zinc-900/80 text-zinc-300 border-zinc-800 hover:text-white hover:bg-zinc-800"
          }`}
          title="Toggle First-Person WASD Walk Mode"
        >
          <Footprints className="w-3.5 h-3.5" />
          <span>{walkMode ? "Walk Mode (WASD)" : "Orbit"}</span>
        </button>

        {/* Crop panel toggle */}
        <button
          onClick={() => setShowCropPanel(!showCropPanel)}
          className={`p-2 rounded-xl text-xs transition-all shadow-lg backdrop-blur-md border ${
            showCropPanel
              ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/50"
              : "bg-zinc-900/80 text-zinc-300 border-zinc-800 hover:text-white hover:bg-zinc-800"
          }`}
          title="Bounding Crop Box"
        >
          <Sliders className="w-4 h-4" />
        </button>

        {/* Theme cycle */}
        <button
          onClick={cycleTheme}
          className="p-2 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-800 transition-all shadow-lg backdrop-blur-md"
          title={`Canvas theme: ${theme}`}
        >
          <Palette className="w-4 h-4" />
        </button>

        {/* Reset view */}
        <button
          onClick={handleResetView}
          className="p-2 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-800 transition-all shadow-lg backdrop-blur-md"
          title="Reset Camera View"
        >
          <RotateCw className="w-4 h-4" />
        </button>
      </div>

      {/* Floating Crop Sliders Panel */}
      {showCropPanel && (
        <div className="absolute top-16 right-5 z-20 w-72 p-4 rounded-2xl bg-zinc-950/90 border border-zinc-800 backdrop-blur-xl shadow-2xl space-y-3 font-mono text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
            <span className="font-bold text-zinc-200">Real-Time Crop Box</span>
            <button
              onClick={() =>
                setCropBox({ minX: -10, maxX: 10, minY: -0.5, maxY: 6, minZ: -10, maxZ: 10 })
              }
              className="text-[10px] text-zinc-400 hover:text-cyan-400 transition-colors"
            >
              Reset
            </button>
          </div>

          {/* Splat Scale */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>Splat Scale</span>
              <span className="text-cyan-300">{splatScale.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="0.2"
              max="2.5"
              step="0.05"
              value={splatScale}
              onChange={(e) => handleSplatScaleChange(parseFloat(e.target.value))}
              className="w-full accent-cyan-400 h-1 bg-zinc-800 rounded-lg cursor-pointer"
            />
          </div>

          {/* X Range */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>X Axis (Width)</span>
              <span className="text-zinc-300">{cropBox.minX}m to {cropBox.maxX}m</span>
            </div>
            <div className="flex space-x-2">
              <input
                type="range"
                min="-15"
                max="0"
                step="0.5"
                value={cropBox.minX}
                onChange={(e) => setCropBox({ ...cropBox, minX: parseFloat(e.target.value) })}
                className="w-1/2 accent-indigo-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0"
                max="15"
                step="0.5"
                value={cropBox.maxX}
                onChange={(e) => setCropBox({ ...cropBox, maxX: parseFloat(e.target.value) })}
                className="w-1/2 accent-indigo-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
            </div>
          </div>

          {/* Y Range */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>Y Axis (Height)</span>
              <span className="text-zinc-300">{cropBox.minY}m to {cropBox.maxY}m</span>
            </div>
            <div className="flex space-x-2">
              <input
                type="range"
                min="-2"
                max="2"
                step="0.1"
                value={cropBox.minY}
                onChange={(e) => setCropBox({ ...cropBox, minY: parseFloat(e.target.value) })}
                className="w-1/2 accent-emerald-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="1"
                max="10"
                step="0.2"
                value={cropBox.maxY}
                onChange={(e) => setCropBox({ ...cropBox, maxY: parseFloat(e.target.value) })}
                className="w-1/2 accent-emerald-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
            </div>
          </div>

          {/* Z Range */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>Z Axis (Depth)</span>
              <span className="text-zinc-300">{cropBox.minZ}m to {cropBox.maxZ}m</span>
            </div>
            <div className="flex space-x-2">
              <input
                type="range"
                min="-15"
                max="0"
                step="0.5"
                value={cropBox.minZ}
                onChange={(e) => setCropBox({ ...cropBox, minZ: parseFloat(e.target.value) })}
                className="w-1/2 accent-rose-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0"
                max="15"
                step="0.5"
                value={cropBox.maxZ}
                onChange={(e) => setCropBox({ ...cropBox, maxZ: parseFloat(e.target.value) })}
                className="w-1/2 accent-rose-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
            </div>
          </div>
        </div>
      )}

      {/* Bottom Center Download Strip */}
      <div className="absolute bottom-5 inset-x-0 z-20 flex justify-center pointer-events-none">
        <div className="flex items-center space-x-2 px-3 py-2 rounded-2xl bg-zinc-950/80 border border-zinc-800/90 backdrop-blur-xl shadow-2xl pointer-events-auto">
          <span className="text-xs font-bold text-zinc-400 mr-2 font-mono flex items-center space-x-1">
            <Download className="w-3.5 h-3.5 text-cyan-400" />
            <span>Downloads:</span>
          </span>
          {availableFormats.map((fmt) => (
            <button
              key={fmt}
              onClick={() => onDownload && onDownload(fmt)}
              className="px-2.5 py-1 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-cyan-500/50 hover:bg-zinc-800 text-zinc-300 hover:text-white text-xs font-mono font-bold transition-all"
            >
              .{fmt}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
