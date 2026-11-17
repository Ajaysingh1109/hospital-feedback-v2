import React from "react";
import { AlertTriangle, RefreshCw, ArrowRight } from "lucide-react";

interface LowAudioModalProps {
  isOpen: boolean;
  message?: string;
  onRecordAgain: () => void;
  onContinue: () => void;
}

export const LowAudioModal: React.FC<LowAudioModalProps> = ({
  isOpen,
  message,
  onRecordAgain,
  onContinue,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-white w-full max-w-sm rounded-3xl shadow-2xl border border-amber-200 overflow-hidden">
        <div className="bg-amber-500 p-6 text-white text-center">
          <div className="w-14 h-14 bg-white/20 rounded-2xl mx-auto flex items-center justify-center mb-2">
            <AlertTriangle className="w-8 h-8 text-white" />
          </div>
          <h2 className="text-lg font-bold">Audio Quality Warning</h2>
        </div>

        <div className="p-6 space-y-4">
          <p className="text-sm text-slate-700 leading-relaxed text-center font-medium">
            {message || "Audio quality appears low. Please review or consider re-recording if necessary."}
          </p>

          <div className="pt-2 flex flex-col gap-2.5">
            <button
              onClick={onRecordAgain}
              className="w-full py-3 px-4 bg-amber-500 hover:bg-amber-600 text-white font-semibold rounded-2xl shadow-md transition flex items-center justify-center gap-2 text-sm"
            >
              <RefreshCw className="w-4 h-4" />
              RECORD AGAIN
            </button>
            <button
              onClick={onContinue}
              className="w-full py-3 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-2xl transition flex items-center justify-center gap-2 text-sm"
            >
              <ArrowRight className="w-4 h-4" />
              CONTINUE ANYWAY
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
