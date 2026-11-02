import React from "react";
import { Capabilities, ScanType } from "../api/types";
import { Check } from "lucide-react";
import { SmartHint } from "./SmartHint";

interface Props {
  scanType: ScanType;
  selectedFormats: string[];
  onChange: (formats: string[]) => void;
  capabilities: Capabilities | null;
}

interface FormatMeta {
  id: string;
  label: string;
  tag: string;
  desc: string;
}

export const FormatPicker: React.FC<Props> = ({
  scanType,
  selectedFormats,
  onChange,
  capabilities,
}) => {
  const allFormats: FormatMeta[] = [
    { id: "glb", label: "GLB", tag: "Web / Three.js", desc: "Self-contained binary glTF standard" },
    { id: "gltf", label: "GLTF", tag: "glTF JSON", desc: "glTF JSON + external bin & textures" },
    { id: "obj", label: "OBJ + MTL", tag: "Universal 3D", desc: "Wavefront mesh with 4K texture ZIP" },
    { id: "fbx", label: "FBX", tag: "Unreal / Unity", desc: "Embedded PBR textures for DCC tools" },
    { id: "usdz", label: "USDZ", tag: "Apple AR", desc: "Native iOS AR Quick Look for iPhone" },
    { id: "ply", label: "PLY", tag: "Points / Mesh", desc: "Stanford polygon with RGB vertex colors" },
    { id: "stl", label: "STL", tag: "3D Printing", desc: "Geometry only (manifold, no texture)" },
    { id: "xyz", label: "XYZ", tag: "Point Cloud", desc: "ASCII spatial coordinate table" },
    { id: "splat", label: "SPLAT", tag: "Web 3DGS", desc: "Compact 32-byte binary web splat" },
    { id: "spz", label: "SPZ", tag: "Compressed Splat", desc: "10x compressed Gaussian splat archive" },
  ];

  const allowedFormatsForScan = capabilities?.format_matrix?.[scanType] || [
    "glb",
    "obj",
    "ply",
    "stl",
    "xyz",
    "fbx",
    "usdz",
  ];

  const toggleFormat = (id: string) => {
    if (selectedFormats.includes(id)) {
      if (selectedFormats.length > 1) {
        onChange(selectedFormats.filter((f) => f !== id));
      }
    } else {
      onChange([...selectedFormats, id]);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
        {allFormats.map((f) => {
          const isSupported = allowedFormatsForScan.includes(f.id);
          const isSelected = selectedFormats.includes(f.id) && isSupported;

          return (
            <div
              key={f.id}
              onClick={() => isSupported && toggleFormat(f.id)}
              className={`p-3 rounded-2xl border transition-all duration-150 select-none flex flex-col justify-between ${
                !isSupported
                  ? "opacity-35 cursor-not-allowed border-zinc-800/60 bg-zinc-950/40 text-zinc-600"
                  : isSelected
                  ? "border-indigo-500/80 bg-indigo-950/30 text-white cursor-pointer shadow-md shadow-indigo-500/10 ring-1 ring-indigo-500/40"
                  : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/60 text-zinc-300 cursor-pointer"
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold uppercase tracking-wider text-white font-mono">
                    {f.label}
                  </span>
                  <div
                    className={`w-4 h-4 rounded-md flex items-center justify-center border transition-colors ${
                      isSelected
                        ? "bg-indigo-500 border-indigo-500 text-white shadow-sm"
                        : "border-zinc-800 bg-zinc-900"
                    }`}
                  >
                    {isSelected && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                  </div>
                </div>

                <div className="text-[10px] font-semibold text-cyan-400 dark:text-cyan-300 truncate">
                  {f.tag}
                </div>
              </div>

              <div className="text-[9.5px] text-zinc-400 mt-2 line-clamp-1 leading-tight">
                {f.desc}
              </div>
            </div>
          );
        })}
      </div>

      <SmartHint
        topic="Export Formats Cheat-Sheet"
        hint="GLB is universal for web/Three.js and Blender. FBX is best for game engines (Unreal/Unity). OBJ ZIP is ideal for legacy 3D tools. STL is geometry-only for 3D printing."
        guideTab={3}
      />
    </div>
  );
};
