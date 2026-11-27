import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button, ClampText, Icon, Menu, staggerStyle, type MenuItem } from "./ui";
import { StatusChip } from "./StatusChip";
import type { LibrarySermon } from "../mock/data";
import { LIFECYCLE_META, type LifecycleState } from "../utils/lifecycle";
import { formatDate, formatDurationValue } from "../utils/format";

export interface TeachingRowAction {
  label: string;
  onClick: () => void;
  primary?: boolean;
  testId?: string;
}

export interface TeachingRowProps {
  sermon: LibrarySermon;
  state: LifecycleState;
  action: TeachingRowAction;
  evidence?: ReactNode;
  menu?: MenuItem[];
  index?: number;
}

function useIsDesktop(): boolean {
  const query = "(min-width: 768px)";
  const [desktop, setDesktop] = useState(() => window.matchMedia?.(query)?.matches ?? true);
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    setDesktop(media.matches);
    const onChange = (event: MediaQueryListEvent) => setDesktop(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return desktop;
}

export function TeachingRow({ sermon, state, action, evidence, menu, index = 0 }: TeachingRowProps) {
  const desktop = useIsDesktop();
  const label = LIFECYCLE_META[state].label;
  const speaker = sermon.speaker || "Unknown speaker";

  return (
    <li
      data-testid={`teaching-row-${sermon.id}`}
      className="stagger-item min-h-[112px] md:min-h-[64px]"
      style={staggerStyle(index)}
    >
      <div className="grid min-h-[112px] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 px-4 py-2 md:min-h-[64px] md:grid-cols-[104px_minmax(0,1fr)_72px_112px_44px] md:gap-y-0 md:py-0">
        <div className="col-start-1 row-start-1 md:w-[104px]">
          <StatusChip state={state} />
        </div>

        <div className="col-span-2 row-start-2 min-w-0 md:col-span-1 md:col-start-2 md:row-start-1">
          <Link
            to={`/teaching/${sermon.id}`}
            aria-label={`Open ${sermon.title} by ${speaker}, ${label}`}
            className="flex min-h-[44px] flex-col justify-center rounded-md"
          >
            <ClampText text={sermon.title} className="text-sm font-semibold" />
            <p className="mt-0.5 flex min-w-0 text-xs text-muted">
              <span className="truncate">
                {speaker} · {formatDate(sermon.date)}
              </span>
              <span className="shrink-0 md:hidden"> · {formatDurationValue(sermon.duration)}</span>
            </p>
          </Link>
        </div>

        <div className="hidden md:col-start-3 md:row-start-1 md:block md:text-right md:font-mono md:text-xs md:text-muted">
          {evidence ?? formatDurationValue(sermon.duration)}
        </div>

        <div className="col-span-2 row-start-3 md:col-span-1 md:col-start-4 md:row-start-1">
          <Button
            variant={action.primary && desktop ? "primary" : "secondary"}
            onClick={action.onClick}
            data-testid={action.testId}
            className="w-full"
          >
            {action.label}
          </Button>
        </div>

        <div className="col-start-2 row-start-1 justify-self-end md:col-start-5 md:justify-self-center">
          {menu && menu.length > 0 ? (
            <Menu
              label={`Actions for ${sermon.title}`}
              triggerTestId={`teaching-actions-${sermon.id}`}
              triggerClassName="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-muted transition-colors hover:bg-raised hover:text-mist"
              trigger={<Icon name="more" />}
              items={menu}
            />
          ) : null}
        </div>
      </div>
    </li>
  );
}
