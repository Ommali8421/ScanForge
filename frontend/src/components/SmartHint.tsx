import React from "react";
import { useGuide } from "../context/GuideContext";
import { Sparkles, ArrowRight } from "lucide-react";

interface SmartHintProps {
  topic?: string;
  title?: string;
  hint: React.ReactNode;
  guideTab?: number;
  className?: string;
}

export const SmartHint: React.FC<SmartHintProps> = ({
  topic,
  title,
  hint,
  guideTab,
  className = "",
}) => {
  const { guideEnabled, openGuideModal } = useGuide();

  // If Guide Mode is toggled OFF, unmount completely
  if (!guideEnabled) {
    return null;
  }

  return (
    <div
      className={`p-3 rounded-xl border border-indigo-500/25 bg-gradient-to-r from-indigo-500/10 via-cyan-500/5 to-transparent text-xs text-indigo-200/90 flex items-start gap-2.5 transition-all shadow-sm ${className}`}
    >
      <div className="w-5 h-5 rounded-md bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0 text-indigo-400 mt-0.5">
        <Sparkles className="w-3 h-3 text-cyan-400" />
      </div>
      <div className="flex-1 min-w-0">
        {(title || topic) && (
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="font-semibold text-white tracking-tight">
              {title || topic}
            </span>
          </div>
        )}
        <div className="text-dark-muted dark:text-zinc-300 leading-relaxed">{hint}</div>
      </div>
      {guideTab && (
        <button
          type="button"
          onClick={() => openGuideModal(guideTab)}
          className="flex-shrink-0 text-[11px] font-medium text-cyan-400 hover:text-cyan-300 flex items-center gap-1 hover:underline ml-1 self-center"
        >
          <span>Guide</span>
          <ArrowRight className="w-3 h-3" />
        </button>
      )}
    </div>
  );
};
