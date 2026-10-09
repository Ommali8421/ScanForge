import React from "react";
import { Capabilities, ScanType } from "../api/types";
import { Check } from "lucide-react";

interface Props {
  scanType: ScanType;
  selectedFormats: string[];
  onChange: (formats: string[]) => void;
  capabilities: Capabilities | null;
}

export const FormatPicker: React.FC<Props> = ({
  scanType,
  selectedFormats,
  onChange,
  capabilities,
}) => {
  const allFormats = [
    { id: "glb", label: "GLB", category: "Mesh", desc: "Binary glTF standard" },
    { id: "obj", label: "OBJ + MTL", category: "Mesh", desc: "Universal Wavefront mesh" },
    { id: "ply", label: "PLY", category: "Polygon / Point", desc: "Stanford polygon / splats" },
    { id: "splat", label: "SPLAT", category: "Gaussian Splat", desc: "Compact binary splat" },
    { id: "stl", label: "STL", category: "CAD", desc: "Stereolithography geometry" },
    { id: "xyz", label: "XYZ", category: "Point Cloud", desc: "Ascii coordinates" },
    { id: "fbx", label: "FBX", category: "DCC", desc: "Autodesk filmbox (needs Blender)" },
    { id: "usdz", label: "USDZ", category: "AR", desc: "Apple AR format (needs Blender)" },
  ];

  const allowedFormatsForScan = capabilities?.format_matrix?.[scanType] || ["glb", "obj"];

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
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {allFormats.map((f) => {
        const isSupported = allowedFormatsForScan.includes(f.id);
        const isSelected = selectedFormats.includes(f.id) && isSupported;

        return (
          <div
            key={f.id}
            onClick={() => isSupported && toggleFormat(f.id)}
            className={`p-3 rounded-xl border transition-all select-none ${
              !isSupported
                ? "opacity-40 cursor-not-allowed border-dark-border bg-dark-bg/40 text-dark-muted"
                : isSelected
                ? "border-brand-500 bg-brand-500/10 cursor-pointer"
                : "border-dark-border bg-dark-card hover:border-slate-600 hover:bg-dark-hover cursor-pointer"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold uppercase tracking-wider text-white">{f.label}</span>
              <div
                className={`w-4 h-4 rounded flex items-center justify-center border transition-colors ${
                  isSelected
                    ? "bg-brand-500 border-brand-500 text-white"
                    : "border-dark-border bg-dark-bg"
                }`}
              >
                {isSelected && <Check className="w-3 h-3" />}
              </div>
            </div>
            <div className="text-[10px] text-dark-muted truncate">{f.desc}</div>
          </div>
        );
      })}
    </div>
  );
};
