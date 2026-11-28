import { Chip } from "./ui";
import { LIFECYCLE_META, type LifecycleState } from "../utils/lifecycle";

export function StatusChip({ state }: { state: LifecycleState }) {
  const meta = LIFECYCLE_META[state];
  return <Chip tone={meta.tone}>{meta.label}</Chip>;
}
