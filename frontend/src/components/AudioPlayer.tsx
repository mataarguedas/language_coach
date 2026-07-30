interface Props {
  src: string;
}

export default function AudioPlayer({ src }: Props) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <p className="mb-2 text-xs font-medium text-slate-500">Playback</p>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio
        key={src}
        controls
        src={src}
        className="w-full"
      />
    </div>
  );
}
