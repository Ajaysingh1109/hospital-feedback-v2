import React from "react";
import { AlertCircle, Check } from "lucide-react";

interface DepartmentMismatchBannerProps {
  aiDepartment: string;
  selectedDepartment: string;
  onUseSelected: () => void;
  onUseAI: () => void;
}

export const DepartmentMismatchBanner: React.FC<DepartmentMismatchBannerProps> = ({
  aiDepartment,
  selectedDepartment,
  onUseSelected,
  onUseAI,
}) => {
  if (
    !aiDepartment ||
    !selectedDepartment ||
    aiDepartment.toLowerCase().trim() === selectedDepartment.toLowerCase().trim()
  ) {
    return null;
  }

  return (
    <div className="bg-amber-50 border-2 border-amber-300 rounded-2xl p-4 shadow-sm animate-fade-in my-3">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="flex-1 space-y-1">
          <h4 className="text-sm font-bold text-amber-900">
            Possible department mismatch detected.
          </h4>
          <div className="grid grid-cols-2 gap-2 text-xs py-1">
            <div className="bg-white/80 p-2 rounded-xl border border-amber-200">
              <span className="text-slate-500 block">AI suggestion:</span>
              <span className="font-bold text-sky-800 text-sm">{aiDepartment}</span>
            </div>
            <div className="bg-white/80 p-2 rounded-xl border border-amber-200">
              <span className="text-slate-500 block">Selected department:</span>
              <span className="font-bold text-emerald-800 text-sm">{selectedDepartment}</span>
            </div>
          </div>
          <p className="text-xs text-amber-800">
            Please choose which department should handle this feedback:
          </p>
          <div className="flex gap-2 pt-1.5">
            <button
              type="button"
              onClick={onUseSelected}
              className="py-1.5 px-3 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs rounded-xl shadow-sm flex items-center gap-1.5 transition"
            >
              <Check className="w-3.5 h-3.5" />
              USE SELECTED ({selectedDepartment})
            </button>
            <button
              type="button"
              onClick={onUseAI}
              className="py-1.5 px-3 bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs rounded-xl shadow-sm flex items-center gap-1.5 transition"
            >
              <Check className="w-3.5 h-3.5" />
              USE AI SUGGESTION ({aiDepartment})
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
