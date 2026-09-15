import type { Section } from "../components/Shell";
import { Button } from "../components/ui";
import { EmptyState } from "../components/ui";

const copy: Record<Exclude<Section, "home" | "jobs">, { title: string; heading: string; body: string }> = {
  new: {
    title: "New Sermon",
    heading: "Start a run",
    body: "Phase 2 wires this to the real pipeline. For now, pick a sample file and the mock run appears under Jobs.",
  },
  library: {
    title: "Library",
    heading: "No teachings yet",
    body: "Processed teachings will live here with search, status badges, and one-tap regenerate. Import or process a sermon to get started.",
  },
  settings: {
    title: "Settings",
    heading: "Nothing to configure yet",
    body: "Pipeline defaults, API keys, and theme preferences land here in a later phase. The theme toggle in the header already works.",
  },
};

export function Placeholder({ section, onNavigate }: { section: Exclude<Section, "home" | "jobs">; onNavigate: (s: Section) => void }) {
  const c = copy[section];
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{c.title}</h1>
        <p className="text-sm text-muted">Mock screen — backend arrives in Phase 2.</p>
      </div>
      <EmptyState
        title={c.heading}
        body={c.body}
        action={
          section === "new" ? (
            <Button variant="primary" onClick={() => onNavigate("jobs")}>View mock Jobs</Button>
          ) : (
            <Button variant="primary" onClick={() => onNavigate("home")}>Back to Home</Button>
          )
        }
      />
    </div>
  );
}
