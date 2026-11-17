import React from "react";
import { ShieldCheck, Mic } from "lucide-react";

interface ConsentModalProps {
  isOpen: boolean;
  noticeText: string;
  onAgree: () => void;
  onCancel: () => void;
}

export const ConsentModal: React.FC<ConsentModalProps> = ({
  isOpen,
  noticeText,
  onAgree,
  onCancel,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-white w-full max-w-md rounded-3xl shadow-2xl border border-slate-100 overflow-hidden">
        <div className="bg-gradient-to-r from-sky-600 to-teal-600 p-6 text-white text-center relative">
          <div className="w-16 h-16 bg-white/20 rounded-2xl mx-auto flex items-center justify-center mb-3 backdrop-blur-md">
            <Mic className="w-8 h-8 text-white animate-pulse" />
          </div>
          <h2 className="text-xl font-bold tracking-tight">Patient Recording Consent</h2>
          <p className="text-sky-100 text-xs mt-1">Hospital Quality Assurance & Voice Analysis</p>
        </div>

        <div className="p-6 space-y-4">
          <div className="bg-sky-50 border border-sky-100 rounded-2xl p-4 text-sky-950 flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />
            <p className="text-sm font-medium leading-relaxed">
              "{noticeText || "This conversation will be recorded and processed for hospital feedback and quality improvement."}"
            </p>
          </div>

          <div className="text-xs text-slate-500 space-y-1.5 px-1">
            <p>• Audio is processed securely and encrypted at rest.</p>
            <p>• The patient has been informed and given clear verbal consent.</p>
            <p>• Multi-language speech (Hindi, Hinglish, English) is supported.</p>
          </div>

          <div className="pt-2 flex flex-col gap-2.5">
            <button
              onClick={onAgree}
              className="w-full py-3.5 px-4 bg-teal-600 hover:bg-teal-700 active:scale-[0.99] text-white font-semibold rounded-2xl shadow-lg shadow-teal-600/20 transition-all flex items-center justify-center gap-2 text-base"
            >
              <ShieldCheck className="w-5 h-5" />
              I AGREE / CONTINUE
            </button>
            <button
              onClick={onCancel}
              className="w-full py-2.5 px-4 text-slate-500 hover:text-slate-700 hover:bg-slate-100 text-sm font-medium rounded-xl transition"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
