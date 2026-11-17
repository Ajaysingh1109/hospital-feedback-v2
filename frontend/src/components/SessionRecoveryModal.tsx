import React from "react";
import { History, Play, Trash2 } from "lucide-react";
import { SessionDraft } from "../types";

interface SessionRecoveryModalProps {
  draft: SessionDraft | null;
  onResume: () => void;
  onDiscard: () => void;
}

export const SessionRecoveryModal: React.FC<SessionRecoveryModalProps> = ({
  draft,
  onResume,
  onDiscard,
}) => {
  if (!draft) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-white w-full max-w-sm rounded-3xl shadow-2xl border border-sky-100 overflow-hidden">
        <div className="bg-sky-700 p-6 text-white text-center">
          <div className="w-14 h-14 bg-white/20 rounded-2xl mx-auto flex items-center justify-center mb-2">
            <History className="w-8 h-8 text-white animate-spin-slow" />
          </div>
          <h2 className="text-lg font-bold">Unfinished Session Found</h2>
          <p className="text-sky-200 text-xs mt-1">Automatic Session Recovery</p>
        </div>

        <div className="p-6 space-y-4">
          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 text-xs space-y-1 text-slate-600">
            <p className="font-semibold text-slate-800">An unfinished feedback session was recovered:</p>
            <p>• Step: <span className="capitalize font-medium text-sky-700">{draft.step}</span></p>
            {draft.form_data?.patient_name && (
              <p>• Patient: <span className="font-medium text-slate-800">{draft.form_data.patient_name}</span></p>
            )}
            {draft.form_data?.uhid && (
              <p>• UHID: <span className="font-mono font-medium text-slate-800">{draft.form_data.uhid}</span></p>
            )}
            <p>• Started: <span className="text-slate-500">{new Date(draft.started_at).toLocaleTimeString()}</span></p>
          </div>

          <div className="pt-2 flex flex-col gap-2.5">
            <button
              onClick={onResume}
              className="w-full py-3.5 px-4 bg-sky-600 hover:bg-sky-700 active:scale-[0.99] text-white font-semibold rounded-2xl shadow-lg shadow-sky-600/20 transition flex items-center justify-center gap-2 text-sm"
            >
              <Play className="w-4 h-4 fill-current" />
              RESUME SESSION
            </button>
            <button
              onClick={onDiscard}
              className="w-full py-2.5 px-4 bg-slate-100 hover:bg-red-50 hover:text-red-600 text-slate-600 font-medium rounded-xl transition flex items-center justify-center gap-2 text-xs"
            >
              <Trash2 className="w-4 h-4" />
              DISCARD UNFINISHED SESSION
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
