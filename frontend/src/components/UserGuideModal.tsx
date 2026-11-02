import React, { useEffect } from "react";
import { useGuide } from "../context/GuideContext";
import {
  X,
  Compass,
  Layers,
  FileCheck,
  Video,
  Ruler,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Camera,
  Radar,
  Box,
  EyeOff,
  Lightbulb,
} from "lucide-react";

export const UserGuideModal: React.FC = () => {
  const {
    guideModalOpen,
    closeGuideModal,
    activeGuideTab,
    setActiveGuideTab,
    setGuideEnabled,
  } = useGuide();

  useEffect(() => {
    if (!guideModalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        closeGuideModal();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [guideModalOpen, closeGuideModal]);

  if (!guideModalOpen) return null;

  const tabs = [
    { id: 1, label: "Scan Modes", icon: Compass, title: "Which Scan Mode Should I Choose?" },
    { id: 2, label: "Mesh Routes", icon: Layers, title: "Photogrammetry (Route A) vs Depth Fusion (Route B)" },
    { id: 3, label: "Quality & Formats", icon: FileCheck, title: "Quality Presets & Output Formats Cheat-Sheet" },
    { id: 4, label: "Capture Rules", icon: Video, title: "How to Record a Great Room Video" },
    { id: 5, label: "Scale Calibration", icon: Ruler, title: "How to Calibrate Real-World Metric Scale" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto bg-black/75 backdrop-blur-md animate-in fade-in duration-200" onClick={closeGuideModal}>
      <div
        className="relative w-full max-w-4xl bg-zinc-950 border border-zinc-800 rounded-3xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-zinc-800/80 bg-zinc-900/60">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold tracking-tight text-white">
                  ScanForge Studio Guide
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-semibold uppercase">
                  Interactive Coach
                </span>
              </div>
              <p className="text-xs text-zinc-400">
                Essential concepts, capture rules, and pro tips for interior 3D reconstruction.
              </p>
            </div>
          </div>
          <button
            onClick={closeGuideModal}
            className="p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800/80 transition-colors"
            title="Close guide"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1.5 px-6 py-2.5 border-b border-zinc-800/60 bg-zinc-900/40 overflow-x-auto no-scrollbar">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeGuideTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveGuideTab(tab.id)}
                className={`flex items-center space-x-2 px-3 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                  isActive
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/25"
                    : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Modal Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6 text-sm text-zinc-300">
          {/* TAB 1: Which Scan Mode Should I Choose? */}
          {activeGuideTab === 1 && (
            <div className="space-y-5">
              <div>
                <h3 className="text-base font-bold text-white mb-1">
                  Which Scan Mode Should I Choose?
                </h3>
                <p className="text-xs text-zinc-400">
                  Select the reconstruction technique that best fits your deliverable needs.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Photo Scan */}
                <div className="p-4 rounded-2xl border border-indigo-500/30 bg-zinc-900/50 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="w-9 h-9 rounded-xl bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
                      <Camera className="w-5 h-5" />
                    </div>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 uppercase">
                      Primary
                    </span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-white text-sm">Photo Scan</h4>
                    <p className="text-xs text-zinc-400 mt-1">
                      Textured Triangle Mesh (GLB, OBJ, FBX, USDZ)
                    </p>
                  </div>
                  <ul className="text-xs space-y-1.5 text-zinc-300">
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                      <span>Clean, flat-walled triangle geometry aligned to Y=0 floor.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                      <span>Best for Blender, Unreal, CAD, floor plans, and 3D printing.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                      <span>Supports 2-point scale calibration for true metric meters.</span>
                    </li>
                  </ul>
                  <div className="pt-2 border-t border-zinc-800 text-[11px] text-zinc-400">
                    <strong>Input:</strong> Normal smartphone video walkthrough (.mp4, .mov) or zip of photos.
                  </div>
                </div>

                {/* 3DGS Scan */}
                <div className="p-4 rounded-2xl border border-cyan-500/30 bg-zinc-900/50 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="w-9 h-9 rounded-xl bg-cyan-500/20 text-cyan-400 flex items-center justify-center">
                      <Sparkles className="w-5 h-5" />
                    </div>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 uppercase">
                      Core 3DGS
                    </span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-white text-sm">3DGS Scan</h4>
                    <p className="text-xs text-zinc-400 mt-1">
                      Photorealistic Gaussian Splat (.splat, .spz, .ply)
                    </p>
                  </div>
                  <ul className="text-xs space-y-1.5 text-zinc-300">
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0 mt-0.5" />
                      <span>Captures complex lighting, mirror reflections, and glass.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0 mt-0.5" />
                      <span>Ultra-fast real-time web walkthroughs at 60 fps.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0 mt-0.5" />
                      <span>Enable "Extract Mesh" in Advanced options for both splat + mesh.</span>
                    </li>
                  </ul>
                  <div className="pt-2 border-t border-zinc-800 text-[11px] text-zinc-400">
                    <strong>Input:</strong> Thorough video walkthrough with good view overlap.
                  </div>
                </div>

                {/* LiDAR Scan */}
                <div className="p-4 rounded-2xl border border-purple-500/30 bg-zinc-900/50 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="w-9 h-9 rounded-xl bg-purple-500/20 text-purple-400 flex items-center justify-center">
                      <Radar className="w-5 h-5" />
                    </div>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 uppercase">
                      Beta
                    </span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-white text-sm">LiDAR Scan</h4>
                    <p className="text-xs text-zinc-400 mt-1">
                      Direct Hardware Depth + Color Fusion
                    </p>
                  </div>
                  <ul className="text-xs space-y-1.5 text-zinc-300">
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-purple-400 flex-shrink-0 mt-0.5" />
                      <span>Already scaled in true real-world meters at capture time.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-purple-400 flex-shrink-0 mt-0.5" />
                      <span>TSDF depth fusion with zero SfM bundle adjustment drift.</span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
                      <span>Requires an iOS device with LiDAR (iPhone Pro / iPad Pro).</span>
                    </li>
                  </ul>
                  <div className="pt-2 border-t border-zinc-800 text-[11px] text-zinc-400">
                    <strong>Input:</strong> Record3D .r3d archive or calibrated RGB-D ZIP.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Route A vs Route B vs Auto */}
          {activeGuideTab === 2 && (
            <div className="space-y-5">
              <div>
                <h3 className="text-base font-bold text-white mb-1">
                  Photogrammetry (Route A) vs Depth Fusion (Route B) vs Auto
                </h3>
                <p className="text-xs text-zinc-400">
                  ScanForge provides two distinct mesh reconstruction engines, selectable under Advanced Settings.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="font-bold text-white text-sm flex items-center gap-2">
                      <Box className="w-4 h-4 text-indigo-400" />
                      Route A: Photogrammetry (COLMAP + OpenMVS)
                    </h4>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300">
                      High-Texture
                    </span>
                  </div>
                  <p className="text-xs text-zinc-300 leading-relaxed">
                    Uses dense patch-match stereo to triangulate 3D coordinates from photo parallax, followed by Delaunay tetrahedral carving and UV texture atlas baking.
                  </p>
                  <div className="space-y-1.5 text-xs">
                    <div className="text-emerald-400 font-semibold flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Best For:
                    </div>
                    <p className="text-zinc-400 text-xs pl-5">
                      Rooms with rich visual textures: brick walls, patterned rugs, bookshelves, wooden flooring, art frames, and intricate decor. Produces razor-sharp architectural edges.
                    </p>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="text-amber-400 font-semibold flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5" /> Weakness:
                    </div>
                    <p className="text-zinc-400 text-xs pl-5">
                      Struggles on completely textureless, smooth white drywall where feature matchers find zero corners.
                    </p>
                  </div>
                </div>

                <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="font-bold text-white text-sm flex items-center gap-2">
                      <Layers className="w-4 h-4 text-cyan-400" />
                      Route B: Depth Fusion (Neural Depth + TSDF)
                    </h4>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300">
                      Featureless Walls
                    </span>
                  </div>
                  <p className="text-xs text-zinc-300 leading-relaxed">
                    Predicts metric monocular depth per frame using neural depth estimation, aligns depths to sparse SfM anchor points, and integrates them into an Open3D TSDF voxel volume.
                  </p>
                  <div className="space-y-1.5 text-xs">
                    <div className="text-emerald-400 font-semibold flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Best For:
                    </div>
                    <p className="text-zinc-400 text-xs pl-5">
                      Modern minimalist rooms, smooth drywall apartments, uniform white ceilings, and open corridors where traditional stereo leaves Swiss-cheese holes.
                    </p>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="text-amber-400 font-semibold flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5" /> Weakness:
                    </div>
                    <p className="text-zinc-400 text-xs pl-5">
                      Slightly softer geometric corners compared to multi-view stereo on fine objects.
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-2xl bg-indigo-950/30 border border-indigo-500/20 text-xs text-indigo-200 space-y-1.5">
                <div className="font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  Auto Mode (Recommended)
                </div>
                <p>
                  When set to <strong>Auto</strong>, ScanForge analyzes the texture variance and feature density across extracted keyframes. If mean texture variance is high ($\ge 0.40$), it automatically selects <strong>Route A</strong>; if texture is sparse on large white surfaces, it seamlessly activates <strong>Route B</strong> and logs the reasoning.
                </p>
              </div>
            </div>
          )}

          {/* TAB 3: Quality Presets & Output Formats */}
          {activeGuideTab === 3 && (
            <div className="space-y-5">
              <div>
                <h3 className="text-base font-bold text-white mb-1">
                  Quality Presets & Output Formats Cheat-Sheet
                </h3>
                <p className="text-xs text-zinc-400">
                  Understand computational trade-offs and select the right file format for your 3D workflow.
                </p>
              </div>

              {/* Quality Presets Table */}
              <div className="border border-zinc-800 rounded-2xl overflow-hidden bg-zinc-900/50">
                <table className="w-full text-left text-xs">
                  <thead className="bg-zinc-900 text-zinc-400 border-b border-zinc-800">
                    <tr>
                      <th className="p-3">Preset</th>
                      <th className="p-3">Image Cap</th>
                      <th className="p-3">Target Faces</th>
                      <th className="p-3">VRAM Target</th>
                      <th className="p-3">Ideal Use</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800 text-zinc-300">
                    <tr>
                      <td className="p-3 font-semibold text-white">Draft</td>
                      <td className="p-3 font-mono text-cyan-400">1200 px</td>
                      <td className="p-3 font-mono">~50k</td>
                      <td className="p-3 font-mono">&lt; 4 GB</td>
                      <td className="p-3 text-zinc-400">Fast sanity check & spatial layout preview</td>
                    </tr>
                    <tr className="bg-indigo-500/5">
                      <td className="p-3 font-semibold text-white">Standard</td>
                      <td className="p-3 font-mono text-cyan-400">1600 px</td>
                      <td className="p-3 font-mono">~200k</td>
                      <td className="p-3 font-mono">6–8 GB</td>
                      <td className="p-3 text-emerald-300 font-medium">Recommended sweet spot for 8 GB VRAM</td>
                    </tr>
                    <tr>
                      <td className="p-3 font-semibold text-white">High</td>
                      <td className="p-3 font-mono text-cyan-400">2000 px</td>
                      <td className="p-3 font-mono">~500k–1M</td>
                      <td className="p-3 font-mono">7.8 GB (Auto OOM retry)</td>
                      <td className="p-3 text-zinc-400">Final production deliverable & close-up inspection</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Formats Matrix */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">
                  Which File Format Should I Download?
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 text-xs">
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">GLB / GLTF</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      Universal 3D standard. Self-contained binary with embedded textures. Perfect for Three.js, web viewers, and Blender.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">FBX</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      Autodesk Filmbox with embedded PBR textures. The preferred import format for Unreal Engine, Unity, and Maya.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">OBJ + MTL (ZIP)</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      Classic Wavefront format (.obj, .mtl, and 4K texture atlas). Supported by virtually every legacy 3D program.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">USDZ</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      Universal Scene Description for Apple devices. Opens directly in iOS AR Quick Look on iPhones and iPads.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">STL</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      Stereolithography mesh. Geometry only (no color/texture). Ready for slicers like Cura and PrusaSlicer for 3D printing.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">PLY / XYZ</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      Stanford polygon & point cloud formats with per-vertex RGB colors. Ideal for CloudCompare and research tools.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">.splat</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      Compact 32-byte binary format for web Gaussian splats. Streamable and renderable at 60 fps in WebGL.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
                    <span className="font-bold text-white block">SPZ</span>
                    <span className="text-[11px] text-zinc-400 mt-1 block">
                      High-efficiency compressed Gaussian splat format (up to 10x smaller file size with near-zero quality loss).
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: Capture Rules */}
          {activeGuideTab === 4 && (
            <div className="space-y-5">
              <div>
                <h3 className="text-base font-bold text-white mb-1">
                  How to Record a Great Room Video (Capture Rules)
                </h3>
                <p className="text-xs text-zinc-400">
                  Follow these 6 golden rules to achieve 95%+ registered frames and sharp, spike-free geometry.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                <div className="p-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-2">
                  <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Rule 1: Walk for Parallax (Never Pure Spin)</span>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Walk slowly forward and sideways around the room perimeter. Pure rotation from one spot (like a tripod) provides zero baseline parallax and fails 3D depth triangulation!
                  </p>
                </div>

                <div className="p-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-2">
                  <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Rule 2: Lock Exposure & Autofocus</span>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Long-press your phone screen to lock AE/AF before recording. Constantly shifting camera brightness and hunting focus confuses SIFT feature descriptors and breaks matching.
                  </p>
                </div>

                <div className="p-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-2">
                  <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Rule 3: Turn On ALL Room Lights</span>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Bright, uniform illumination reduces camera shutter speed, eliminating motion blur. Open curtains and turn on ceiling and accent lamps.
                  </p>
                </div>

                <div className="p-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-2">
                  <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Rule 4: Frame Corners on Blank Walls</span>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    When panning past a featureless white wall, keep baseboards, door frames, or ceiling moldings in the top/bottom third of the frame so the tracker never sees pure white.
                  </p>
                </div>

                <div className="p-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-2">
                  <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Rule 5: Loop Back to Your Start</span>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Complete a full 360° circuit around the space and end at the exact location you began. This provides loop-closure constraints that eliminate drift and keep walls perpendicular.
                  </p>
                </div>

                <div className="p-4 rounded-2xl border border-zinc-800 bg-zinc-900/60 space-y-2">
                  <div className="flex items-center space-x-2 text-amber-400 font-semibold text-xs">
                    <AlertCircle className="w-4 h-4" />
                    <span>Rule 6: Beware of Mirrors & TV Screens</span>
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Large mirrors create virtual "ghost rooms" behind the wall. Walk at an angle to mirrors or drape large reflective TV panels to prevent spurious geometry outside the room.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: How to Calibrate Real-World Metric Scale */}
          {activeGuideTab === 5 && (
            <div className="space-y-5">
              <div>
                <h3 className="text-base font-bold text-white mb-1">
                  How to Calibrate Real-World Metric Scale
                </h3>
                <p className="text-xs text-zinc-400">
                  Video photogrammetry is inherently scale-ambiguous. Learn how to calibrate real meters in seconds.
                </p>
              </div>

              <div className="p-4 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-3 text-xs leading-relaxed">
                <div className="flex items-center gap-2 text-indigo-400 font-bold">
                  <Lightbulb className="w-4 h-4 text-amber-400" />
                  Why is my scan in arbitrary units?
                </div>
                <p className="text-zinc-300">
                  Because video cameras capture light rays without an active depth sensor, the computer reconstruction is mathematically valid up to an unknown scale factor $S$. A 10-meter living room and a 10-centimeter dollhouse produce identical camera ray projections!
                </p>
              </div>

              <div className="space-y-3">
                <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                  3-Step Calibration Process (&lt; 0.15s Execution)
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                  <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-600 text-white font-bold flex items-center justify-center font-mono">
                      1
                    </div>
                    <span className="font-bold text-white block">Click Point A</span>
                    <p className="text-zinc-400">
                      In the 3D viewer, click on one end of a known architectural reference (e.g. the left corner of a door frame, window sill, or floor tile). A crimson marker appears.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-600 text-white font-bold flex items-center justify-center font-mono">
                      2
                    </div>
                    <span className="font-bold text-white block">Click Point B</span>
                    <p className="text-zinc-400">
                      Click on the opposite end of the same reference (e.g. the right corner of the door). A blue marker and purple measurement line appear, showing virtual uncalibrated distance.
                    </p>
                  </div>

                  <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-2">
                    <div className="w-7 h-7 rounded-lg bg-emerald-600 text-white font-bold flex items-center justify-center font-mono">
                      3
                    </div>
                    <span className="font-bold text-white block">Enter Real Distance & Apply</span>
                    <p className="text-zinc-400">
                      Type the real measurement (e.g. <span className="font-mono text-emerald-400 font-bold">0.90 m</span>) and click <strong>Apply Scale</strong>. ScanForge updates all exports, floor area, and dimensions in &lt; 0.15s!
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-800/80 bg-zinc-900/80 text-xs">
          <button
            type="button"
            onClick={() => {
              setGuideEnabled(false);
              closeGuideModal();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 transition-colors"
          >
            <EyeOff className="w-4 h-4" />
            <span>Turn Off Guide Mode</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={closeGuideModal}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all shadow-md shadow-indigo-600/20"
            >
              Got it, let's scan
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
