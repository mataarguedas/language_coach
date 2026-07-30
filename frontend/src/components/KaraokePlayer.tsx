import { useRef } from "react";
import { useScheduler } from "../lib/scheduler";
import type { TimingSchedule } from "../lib/types";

interface Props {
  src: string;
  timing: TimingSchedule;
}

export default function KaraokePlayer({ src, timing }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const activeIndex = useScheduler(timing, audioRef);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
      <p className="text-xs font-medium text-slate-500">Playback</p>

      {timing.entries.length > 0 && (
        <div
          className="flex flex-wrap gap-x-1 gap-y-2 rounded-md bg-slate-50 p-3 text-lg leading-relaxed"
          aria-live="polite"
          aria-label="Karaoke text"
        >
          {timing.entries.map((entry, i) => (
            <span
              key={i}
              data-index={i}
              className={[
                "rounded px-0.5 transition-colors duration-75",
                i === activeIndex
                  ? "bg-amber-200 text-amber-900 font-semibold"
                  : "text-slate-700",
              ].join(" ")}
            >
              {entry.token.text}
            </span>
          ))}
        </div>
      )}

      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} controls src={src} className="w-full" />
    </div>
  );
}
