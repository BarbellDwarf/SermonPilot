import { Link } from "react-router-dom";
import { Button, EmptyState } from "../components/ui";

export function NewSermon() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New Sermon</h1>
        <p className="text-sm text-muted">Mock screen — backend arrives in Phase 3.</p>
      </div>
      <EmptyState
        title="Start a run"
        body="Phase 3 wires this to the real pipeline. For now, pick a sample file and the mock run appears under Jobs."
        action={
          <Link to="/jobs">
            <Button variant="primary">View mock Jobs</Button>
          </Link>
        }
      />
    </div>
  );
}
