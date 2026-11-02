import React, { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import {
  Download,
  RotateCw,
  AlertTriangle,
  Sliders,
  Footprints,
  Palette,
  Home,
  Layers,
  Compass,
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

interface AlignedCamera {
  index: number;
  name: string;
  position: [number, number, number];
  up: [number, number, number];
  forward: [number, number, number];
}

interface Props {
  splatUrl: string; // URL to .splat, .ply, or .spz
  jobId?: string;
  splatCount?: number;
  bounds?: {
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    min_z: number;
    max_z: number;
  };
  dimensions?: {
    length: number;
    width: number;
    height: number;
  };
  onDownload?: (format: string) => void;
  availableFormats?: string[];
}

export const SplatViewer: React.FC<Props> = ({
  splatUrl,
  jobId,
  splatCount,
  bounds,
  dimensions: _dimensions,
  onDownload,
  availableFormats = ["splat", "ply", "zip"],
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);

  const [loading, setLoading] = useState(true);
  const [loadProgress, setLoadProgress] = useState(0);
  const [loadingStage, setLoadingStage] = useState("Connecting to 3DGS WebGL Stream...");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [theme, setTheme] = useState<SplatTheme>("dark-slate");
  const [splatScale, setSplatScale] = useState(1.0);
  const [walkMode, setWalkMode] = useState(false);
  const [showCropPanel, setShowCropPanel] = useState(false);
  const [activePreset, setActivePreset] = useState<"inside" | "dollhouse" | "topdown" | "custom">("inside");
  const [alignedCameras, setAlignedCameras] = useState<AlignedCamera[]>([]);

  // 6-slider crop box state
  const [cropBox, setCropBox] = useState<CropBox>({
    minX: -15,
    maxX: 15,
    minY: -0.5,
    maxY: 8,
    minZ: -15,
    maxZ: 15,
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

  // Fetch aligned camera poses if available
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    fetch(`/api/jobs/${jobId}/artifacts/cameras_aligned.json`)
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => {
        if (active && data?.cameras && Array.isArray(data.cameras)) {
          setAlignedCameras(data.cameras);
        }
      })
      .catch((e) => {
        console.debug("cameras_aligned.json not available:", e);
      });
    return () => {
      active = false;
    };
  }, [jobId]);

  // Hook GPU shader clipping onto splat mesh material
  const applyGpuClipping = useCallback((box: CropBox) => {
    if (!viewerRef.current?.splatMesh) return;
    const mesh = viewerRef.current.splatMesh;
    const mat = mesh.material;
    if (!mat) return;

    if (!mat.uniforms.sfCropMin) {
      mat.uniforms.sfCropMin = { value: new THREE.Vector3(box.minX, box.minY, box.minZ) };
      mat.uniforms.sfCropMax = { value: new THREE.Vector3(box.maxX, box.maxY, box.maxZ) };
      mat.uniforms.sfCropEnabled = { value: 1 };

      if (!mat.vertexShader.includes("sfCropMin")) {
        mat.vertexShader = `
          uniform vec3 sfCropMin;
          uniform vec3 sfCropMax;
          uniform int sfCropEnabled;
        ` + mat.vertexShader;

        mat.vertexShader = mat.vertexShader.replace(
          "vec3 splatCenter = uintBitsToFloat(uvec3(sampledCenterColor.gba));",
          `vec3 splatCenter = uintBitsToFloat(uvec3(sampledCenterColor.gba));
          if (sfCropEnabled == 1) {
            if (splatCenter.x < sfCropMin.x || splatCenter.x > sfCropMax.x ||
                splatCenter.y < sfCropMin.y || splatCenter.y > sfCropMax.y ||
                splatCenter.z < sfCropMin.z || splatCenter.z > sfCropMax.z) {
              gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
              return;
            }
          }`
        );
        mat.needsUpdate = true;
      }
    } else {
      mat.uniforms.sfCropMin.value.set(box.minX, box.minY, box.minZ);
      mat.uniforms.sfCropMax.value.set(box.maxX, box.maxY, box.maxZ);
      mat.uniforms.sfCropEnabled.value = 1;
    }
  }, []);

  // Update clipping when cropBox changes
  useEffect(() => {
    applyGpuClipping(cropBox);
  }, [cropBox, applyGpuClipping]);

  // View Preset: Inside Room
  const handlePresetInside = useCallback(() => {
    setActivePreset("inside");
    if (!viewerRef.current?.camera) return;

    // Reset crop box to full room
    if (bounds) {
      setCropBox({
        minX: Math.floor(bounds.min_x - 1.0),
        maxX: Math.ceil(bounds.max_x + 1.0),
        minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
        maxY: Math.ceil(bounds.max_y + 1.0),
        minZ: Math.floor(bounds.min_z - 1.0),
        maxZ: Math.ceil(bounds.max_z + 1.0),
      });
    }

    if (alignedCameras.length > 0) {
      const cam0 = alignedCameras[0];
      const pos = cam0.position;
      const fwd = cam0.forward;
      viewerRef.current.camera.position.set(pos[0], pos[1], pos[2]);
      if (viewerRef.current.controls?.target) {
        viewerRef.current.controls.target.set(
          pos[0] + fwd[0] * 3.0,
          pos[1] + fwd[1] * 3.0,
          pos[2] + fwd[2] * 3.0
        );
        viewerRef.current.controls.update?.();
      }
    } else {
      viewerRef.current.camera.position.set(0, 1.4, 0);
      if (viewerRef.current.controls?.target) {
        viewerRef.current.controls.target.set(0, 1.3, 3.0);
        viewerRef.current.controls.update?.();
      }
    }
  }, [alignedCameras, bounds]);

  // View Preset: Dollhouse Cutaway (Orbits elevated 3/4 with top 18% ceiling cutaway)
  const handlePresetDollhouse = useCallback(() => {
    setActivePreset("dollhouse");
    if (!viewerRef.current?.camera) return;

    let cx = 0, cy = 1.0, cz = 0;
    let spanX = 5.0, spanY = 2.8, spanZ = 5.0;

    if (bounds) {
      cx = (bounds.min_x + bounds.max_x) / 2;
      cy = (bounds.min_y + bounds.max_y) / 2;
      cz = (bounds.min_z + bounds.max_z) / 2;
      spanX = Math.max(bounds.max_x - bounds.min_x, 4.0);
      spanY = Math.max(bounds.max_y - bounds.min_y, 2.0);
      spanZ = Math.max(bounds.max_z - bounds.min_z, 4.0);

      // Cut away top 18% of ceiling
      const ceilingCutY = bounds.max_y - 0.18 * spanY;
      setCropBox({
        minX: Math.floor(bounds.min_x - 1.0),
        maxX: Math.ceil(bounds.max_x + 1.0),
        minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
        maxY: ceilingCutY,
        minZ: Math.floor(bounds.min_z - 1.0),
        maxZ: Math.ceil(bounds.max_z + 1.0),
      });
    }

    // Elevated 3/4 viewpoint looking down at room centroid
    const eyeX = cx - 1.1 * spanX;
    const eyeY = cy + 1.2 * spanY + 1.0;
    const eyeZ = cz - 1.1 * spanZ;
    viewerRef.current.camera.position.set(eyeX, eyeY, eyeZ);
    if (viewerRef.current.controls?.target) {
      viewerRef.current.controls.target.set(cx, cy * 0.5, cz);
      viewerRef.current.controls.update?.();
    }
  }, [bounds]);

  // View Preset: Floor Plan Top-Down
  const handlePresetTopDown = useCallback(() => {
    setActivePreset("topdown");
    if (!viewerRef.current?.camera) return;

    let cx = 0, cz = 0;
    let span = 6.0;

    if (bounds) {
      cx = (bounds.min_x + bounds.max_x) / 2;
      cz = (bounds.min_z + bounds.max_z) / 2;
      span = Math.max(bounds.max_x - bounds.min_x, bounds.max_z - bounds.min_z, 5.0);

      setCropBox({
        minX: Math.floor(bounds.min_x - 1.0),
        maxX: Math.ceil(bounds.max_x + 1.0),
        minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
        maxY: Math.ceil(bounds.max_y + 1.0),
        minZ: Math.floor(bounds.min_z - 1.0),
        maxZ: Math.ceil(bounds.max_z + 1.0),
      });
    }

    viewerRef.current.camera.position.set(cx, span * 1.5, cz);
    if (viewerRef.current.controls?.target) {
      viewerRef.current.controls.target.set(cx, 0.0, cz);
      viewerRef.current.controls.update?.();
    }
  }, [bounds]);

  // Initialize GaussianSplats3D.Viewer
  useEffect(() => {
    if (!containerRef.current || !splatUrl) return;

    setLoading(true);
    setLoadProgress(0);
    setLoadingStage("Connecting to 3DGS WebGL Stream...");
    setLoadError(null);

    let disposed = false;
    let viewer: any = null;

    try {
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
        initialCameraPosition: [0, 1.4, 0],
        initialCameraLookAt: [0, 1.3, 3.0],
        sharedMemoryForWorkers: false,
        gpuAcceleratedSort: false,
        antialiased: true,
        sphericalHarmonicsDegree: 0,
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
          onProgress: (percent: number) => {
            if (!disposed) {
              const p = Math.min(Math.round(percent), 100);
              setLoadProgress(p);
              if (p >= 100) {
                setLoadingStage("Rasterizing 3D Gaussian Splats...");
              } else {
                setLoadingStage(`Downloading Splat Payload... ${p}%`);
              }
            }
          },
        })
        .then(() => {
          if (disposed) return;

          try {
            viewer.start();
          } catch (e) {
            console.debug("viewer.start exception:", e);
          }

          // Auto-frame initial room view
          try {
            let cx = 0, cy = 1.0, cz = 0;
            let span = 5.0;

            if (bounds) {
              cx = (bounds.min_x + bounds.max_x) / 2;
              cy = (bounds.min_y + bounds.max_y) / 2;
              cz = (bounds.min_z + bounds.max_z) / 2;
              span = Math.max(bounds.max_x - bounds.min_x, bounds.max_z - bounds.min_z, 4.0);

              const pad = Math.max(span * 0.2, 1.5);
              const initialBox: CropBox = {
                minX: Math.floor(bounds.min_x - pad),
                maxX: Math.ceil(bounds.max_x + pad),
                minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
                maxY: Math.ceil(bounds.max_y + pad),
                minZ: Math.floor(bounds.min_z - pad),
                maxZ: Math.ceil(bounds.max_z + pad),
              };
              setCropBox(initialBox);
              applyGpuClipping(initialBox);
            }

            if (viewer.camera) {
              viewer.camera.near = 0.05;
              viewer.camera.far = 2000.0;
              viewer.camera.updateProjectionMatrix();

              // Spawn at interior eye-level looking forward
              viewer.camera.position.set(cx, Math.max(cy * 0.6, 1.3), cz - span * 0.1);
              if (viewer.controls?.target) {
                viewer.controls.target.set(cx, Math.max(cy * 0.6, 1.3), cz + span * 0.6);
                viewer.controls.update?.();
              }
            }
          } catch (e) {
            console.debug("Camera auto-framing exception:", e);
          }

          setLoading(false);
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
  }, [splatUrl, bounds, applyGpuClipping]);

  // WASD walk mode key listeners
  useEffect(() => {
    if (!walkMode || !viewerRef.current) return;

    const moveSpeed = 0.12;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!viewerRef.current?.camera) return;
      const cam = viewerRef.current.camera;
      const forward = new Float32Array(3);
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
      className="relative w-full h-[560px] lg:h-[650px] rounded-3xl overflow-hidden border border-zinc-800/80 shadow-2xl transition-colors duration-300"
      style={{ backgroundColor: getThemeBg(theme) }}
    >
      {/* 3DGS Canvas Container */}
      <div ref={containerRef} className="absolute inset-0 w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Loading Overlay */}
      {loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950/80 backdrop-blur-md z-30 transition-opacity">
          <div className="w-12 h-12 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mb-4" />
          <p className="text-sm font-mono text-zinc-200 tracking-wider font-semibold">
            {loadingStage}
          </p>
          <div className="w-48 h-1.5 bg-zinc-800 rounded-full overflow-hidden mt-3">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all duration-300"
              style={{ width: `${Math.max(loadProgress, 5)}%` }}
            />
          </div>
          <span className="text-xs font-mono text-zinc-500 mt-2">
            World-centered (0, 0, 0) • Floor flush at Y=0.000m • +Y Up
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
          Up: +Y (0, 1, 0) • Floor flush at Y=0.000m • Center (0, 0)
        </div>
      </div>

      {/* Top Center 1-Click View Presets */}
      <div className="absolute top-5 inset-x-0 z-20 flex justify-center pointer-events-none">
        <div className="flex items-center space-x-1 p-1 rounded-2xl bg-zinc-950/80 border border-zinc-800/90 backdrop-blur-xl shadow-2xl pointer-events-auto">
          <button
            onClick={handlePresetInside}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all ${
              activePreset === "inside"
                ? "bg-cyan-500 text-zinc-950 shadow-md shadow-cyan-500/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
            title="Inside Room Walkthrough Camera"
          >
            <Home className="w-3.5 h-3.5" />
            <span>Inside Room</span>
          </button>

          <button
            onClick={handlePresetDollhouse}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all ${
              activePreset === "dollhouse"
                ? "bg-cyan-500 text-zinc-950 shadow-md shadow-cyan-500/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
            title="Dollhouse 3/4 Overview with Ceiling Cutaway"
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Dollhouse Cutaway</span>
          </button>

          <button
            onClick={handlePresetTopDown}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all ${
              activePreset === "topdown"
                ? "bg-cyan-500 text-zinc-950 shadow-md shadow-cyan-500/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
            title="Floor Plan Top-Down View"
          >
            <Compass className="w-3.5 h-3.5" />
            <span>Floor Plan</span>
          </button>
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
          title="Bounding Crop Box & Clipping"
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
          onClick={handlePresetInside}
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
              onClick={() => {
                setActivePreset("custom");
                if (bounds) {
                  setCropBox({
                    minX: Math.floor(bounds.min_x - 1.0),
                    maxX: Math.ceil(bounds.max_x + 1.0),
                    minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
                    maxY: Math.ceil(bounds.max_y + 1.0),
                    minZ: Math.floor(bounds.min_z - 1.0),
                    maxZ: Math.ceil(bounds.max_z + 1.0),
                  });
                }
              }}
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
                min="-20"
                max="0"
                step="0.5"
                value={cropBox.minX}
                onChange={(e) => {
                  setActivePreset("custom");
                  setCropBox({ ...cropBox, minX: parseFloat(e.target.value) });
                }}
                className="w-1/2 accent-indigo-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0"
                max="20"
                step="0.5"
                value={cropBox.maxX}
                onChange={(e) => {
                  setActivePreset("custom");
                  setCropBox({ ...cropBox, maxX: parseFloat(e.target.value) });
                }}
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
                onChange={(e) => {
                  setActivePreset("custom");
                  setCropBox({ ...cropBox, minY: parseFloat(e.target.value) });
                }}
                className="w-1/2 accent-emerald-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0.5"
                max="12"
                step="0.2"
                value={cropBox.maxY}
                onChange={(e) => {
                  setActivePreset("custom");
                  setCropBox({ ...cropBox, maxY: parseFloat(e.target.value) });
                }}
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
                min="-20"
                max="0"
                step="0.5"
                value={cropBox.minZ}
                onChange={(e) => {
                  setActivePreset("custom");
                  setCropBox({ ...cropBox, minZ: parseFloat(e.target.value) });
                }}
                className="w-1/2 accent-rose-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0"
                max="20"
                step="0.5"
                value={cropBox.maxZ}
                onChange={(e) => {
                  setActivePreset("custom");
                  setCropBox({ ...cropBox, maxZ: parseFloat(e.target.value) });
                }}
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
