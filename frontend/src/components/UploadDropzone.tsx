export function UploadDropzone() {
  return (
    <section className="panel-shell panel-shell--hero overflow-hidden" aria-label="Upload today's scene">
      <div className="absolute inset-x-6 top-6 flex items-center justify-between gap-4">
        <span className="signal-chip signal-chip--warm">Pencil source active</span>
        <span className="text-xs uppercase tracking-[0.28em] text-white/35">API bridge pending</span>
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(260px,0.8fr)]">
        <div className="space-y-6 pt-8">
          <div>
            <p className="eyebrow">EchoWhale</p>
            <h1 className="font-display text-5xl leading-[1.02] text-[var(--color-foam)] sm:text-6xl">
              Upload today's scene and turn it into a speaking rehearsal.
            </h1>
          </div>
          <p className="max-w-2xl text-base leading-8 text-[var(--color-mist)] sm:text-lg">
            Build the session from one real-world image, pull out the likely role-play context,
            and keep the learner moving with short feedback instead of long lectures.
          </p>
          <div className="flex flex-wrap gap-3">
            <button className="primary-action" type="button">
              Upload today's scene
            </button>
            <button className="ghost-action" type="button">
              Preview design mapping
            </button>
          </div>
        </div>

        <div className="dropzone-shell">
          <div className="space-y-3">
            <p className="eyebrow">Dropzone</p>
            <p className="text-lg font-semibold text-[var(--color-foam)]">counter-order.jpg</p>
            <p className="text-sm leading-7 text-[var(--color-mist)]">
              Image accepted. The frontend currently replays a mock session contract until the real
              upload and session routes are exposed.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-[22px] border border-white/10 bg-black/10 p-4">
              <p className="eyebrow">Detected mood</p>
              <p className="mt-2 text-sm text-[var(--color-foam)]">Quick service, casual tone</p>
            </div>
            <div className="rounded-[22px] border border-white/10 bg-black/10 p-4">
              <p className="eyebrow">Learner goal</p>
              <p className="mt-2 text-sm text-[var(--color-foam)]">Place an order and keep it natural</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
