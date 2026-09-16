import { Link } from "react-router-dom";
import { Button, EmptyState } from "../components/ui";

export function Settings() {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted">Mock screen — backend arrives in a later phase.</p>
      </div>
      <EmptyState
        title="Nothing to configure yet"
        body="Pipeline defaults, API keys, and theme preferences land here in a later phase. The theme toggle in the header already works."
        action={
          <Link to="/">
            <Button variant="primary">Back to Home</Button>
          </Link>
        }
      />
    </div>
  );
}
