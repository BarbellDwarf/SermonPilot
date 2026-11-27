import { Link, useNavigate } from "react-router-dom";
import { EmptyState, PageHeader, SkeletonList, buttonClass } from "../components/ui";
import { TeachingRow } from "../components/TeachingRow";
import { QueryError, useInboxData } from "../api/hooks";
import { LIFECYCLE_META } from "../utils/lifecycle";

export function Inbox() {
  const { sections, services, publishedThisWeek, isLoading, error, retry } = useInboxData();
  const navigate = useNavigate();

  const visible = sections.filter((section) => section.items.length > 0);
  const primaryId = visible[0]?.items[0]?.id;
  const okServices = services.filter((service) => service.state === "ok").length;

  const open = (id: string) => navigate(`/teaching/${id}`);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Inbox" sub="Teachings that need a decision." />

      {error ? <QueryError message={error} onRetry={retry} /> : null}

      {isLoading ? (
        <div className="flex flex-col gap-6" data-testid="inbox-loading">
          <SkeletonList rows={3} variant="row" />
          <SkeletonList rows={2} variant="row" />
        </div>
      ) : visible.length === 0 ? (
        error ? null : (
          <EmptyState
            title="Nothing needs you."
            body="No teaching is waiting on a review, a render or a retry. New work appears here as it arrives."
            action={
              <Link to="/new" className={buttonClass("secondary")}>
                New teaching
              </Link>
            }
          />
        )
      ) : (
        visible.map((section) => (
          <section
            key={section.state}
            aria-labelledby={`inbox-${section.state}`}
            data-testid={`inbox-section-${section.state}`}
            className="overflow-hidden rounded-lg border border-line bg-surface"
          >
            <div className="flex items-center justify-between gap-2 px-4 py-3">
              <h2 id={`inbox-${section.state}`} className="text-lg font-semibold">
                {LIFECYCLE_META[section.state].label}
              </h2>
              <span className="font-mono text-xs text-muted">{section.items.length}</span>
            </div>
            <ol className="divide-y divide-line border-t border-line">
              {section.items.map((sermon, index) => (
                <TeachingRow
                  key={sermon.id}
                  sermon={sermon}
                  state={section.state}
                  index={index}
                  action={{
                    label: LIFECYCLE_META[section.state].primary ?? "Open",
                    onClick: () => open(sermon.id),
                    primary: sermon.id === primaryId,
                    testId: `inbox-action-${sermon.id}`,
                  }}
                  menu={[{ label: "Open teaching", onSelect: () => open(sermon.id) }]}
                />
              ))}
            </ol>
          </section>
        ))
      )}

      {!isLoading ? (
        <footer
          data-testid="inbox-footer"
          className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted"
        >
          <span>{services.length > 0 ? `Services ${okServices}/${services.length}` : "Services —"}</span>
          <span>Published this week {publishedThisWeek}</span>
          <Link
            to="/library"
            className="inline-flex min-h-[44px] items-center rounded-md text-sm font-medium text-accent hover:underline"
          >
            Open library
          </Link>
        </footer>
      ) : null}
    </div>
  );
}
