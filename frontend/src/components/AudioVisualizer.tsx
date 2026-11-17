import React, { useEffect, useRef } from "react";

interface AudioVisualizerProps {
  stream: MediaStream | null;
  isRecording: boolean;
  isPaused: boolean;
}

export const AudioVisualizer: React.FC<AudioVisualizerProps> = ({
  stream,
  isRecording,
  isPaused,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!canvasRef.current || !stream || !isRecording || isPaused) {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      return;
    }

    let audioContext: AudioContext | null = null;
    let analyser: AnalyserNode | null = null;
    let source: MediaStreamAudioSourceNode | null = null;

    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      audioContext = new AudioCtx();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 128;
      source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");

      const draw = () => {
        if (!ctx || !canvas) return;
        animFrameRef.current = requestAnimationFrame(draw);

        analyser!.getByteFrequencyData(dataArray);

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const barWidth = (canvas.width / bufferLength) * 2;
        let barHeight;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
          barHeight = (dataArray[i] / 255) * canvas.height * 0.9;

          // Gradient color: Hospital teal to vibrant medical cyan
          const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
          gradient.addColorStop(0, "#0284c7");
          gradient.addColorStop(1, "#0d9488");

          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.roundRect(x, canvas.height - barHeight, barWidth - 2, barHeight, [3, 3, 0, 0]);
          ctx.fill();

          x += barWidth;
        }
      };

      draw();
    } catch (e) {
      console.warn("Audio visualizer initialization warning:", e);
    }

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      if (source) source.disconnect();
      if (audioContext && audioContext.state !== "closed") {
        audioContext.close();
      }
    };
  }, [stream, isRecording, isPaused]);

  return (
    <div className="w-full bg-slate-900/5 rounded-2xl p-3 flex flex-col items-center border border-slate-200">
      <canvas
        ref={canvasRef}
        width={320}
        height={60}
        className="w-full h-16 rounded-xl"
      />
      <div className="flex items-center gap-2 mt-1">
        <span
          className={`h-2.5 w-2.5 rounded-full ${
            isRecording && !isPaused
              ? "bg-emerald-500 animate-ping"
              : isPaused
              ? "bg-amber-500"
              : "bg-slate-300"
          }`}
        />
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
          {isRecording && !isPaused
            ? "Capturing Audio Live"
            : isPaused
            ? "Recording Paused"
            : "Microphone Ready"}
        </span>
      </div>
    </div>
  );
};
