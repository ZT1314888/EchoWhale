import { HistoryRail } from "./components/HistoryRail";
import { SceneSummaryCard } from "./components/SceneSummaryCard";
import { SessionStage } from "./components/SessionStage";
import { UploadDropzone } from "./components/UploadDropzone";
import { activeSession, historyEntries } from "./data/mockSession";

export function App() {
  return (
    <div className="min-h-screen bg-[var(--color-night)] text-[var(--color-mist)]">
      <div className="halo-grid min-h-screen px-4 py-6 sm:px-6 lg:px-10">
        <div className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-[1520px] flex-col gap-6">
          <header className="flex flex-col gap-4 rounded-[28px] border border-white/10 bg-black/10 px-5 py-4 backdrop-blur md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-full border border-[var(--color-aqua)]/35 bg-[var(--color-aqua)]/12 text-sm font-semibold text-[var(--color-aqua)]">
                EW
              </div>
              <div>
                <p className="font-display text-2xl text-[var(--color-foam)]">EchoWhale</p>
                <p className="text-sm tracking-[0.18em] text-white/35 uppercase">
                  Pencil-first prototype cockpit
                </p>
              </div>
            </div>

            <nav className="flex flex-wrap gap-2 text-sm">
              <span className="signal-chip">Home</span>
              <span className="signal-chip">Session</span>
              <span className="signal-chip">Feedback</span>
              <span className="signal-chip">History</span>
            </nav>
          </header>

          <div className="grid flex-1 gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,0.72fr)]">
            <main className="flex min-h-0 flex-col gap-6">
              <UploadDropzone />
              <SessionStage session={activeSession} />
            </main>

            <aside className="flex min-h-0 flex-col gap-6">
              <SceneSummaryCard session={activeSession} />
              <HistoryRail entries={historyEntries} />
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}
