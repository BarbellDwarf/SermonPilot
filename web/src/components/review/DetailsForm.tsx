import { useState } from "react";
import { writeApi, type ApiMetadataField } from "../../api/client";
import type { LibrarySermon } from "../../mock/data";
import { formatDate } from "../../utils/format";
import { Button, Chip, Field, Icon, Menu, buttonClass, inputCls } from "../ui";
import type { DetailsPatch } from "./types";

interface DetailsFormProps {
  sermon: LibrarySermon;
  description: string | null;
  descriptionNeedsReview?: boolean;
  hashtags?: string | null;
  isLive: boolean;
  readOnly?: boolean;
  onSaveDetails?: (patch: DetailsPatch) => Promise<void> | void;
  onRegenerateDescription?: () => Promise<void> | void;
  onSendBack?: () => void;
  onToast: (message: string, variant?: "success" | "error" | "info") => void;
}

interface DetailsDraft {
  title: string;
  speaker: string;
  series: string;
  date: string;
  description: string;
  hashtags: string;
}

const FIELD_LABELS: Record<ApiMetadataField, string> = {
  title: "title",
  description: "description",
  hashtags: "hashtags",
};

function ReadOnlyDetails({ draft }: { draft: DetailsDraft }) {
  const rows = [
    ["Title", draft.title],
    ["Speaker", draft.speaker || "Unknown speaker"],
    ["Series", draft.series || "—"],
    ["Date", formatDate(draft.date)],
    ["Description", draft.description || "No description recorded."],
    ["Hashtags", draft.hashtags || "—"],
  ];
  return (
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} data-testid={`detail-${label.toLowerCase()}`} className="min-w-0">
          <dt className="text-xs font-medium text-muted">{label}</dt>
          <dd className="mt-0.5 whitespace-pre-wrap text-sm text-mist [overflow-wrap:anywhere]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DetailsForm({
  sermon,
  description,
  descriptionNeedsReview = false,
  hashtags = null,
  isLive,
  readOnly = false,
  onSaveDetails,
  onRegenerateDescription,
  onSendBack,
  onToast,
}: DetailsFormProps) {
  const [form, setForm] = useState<DetailsDraft>({
    title: sermon.title,
    speaker: sermon.speaker,
    series: sermon.series,
    date: sermon.date,
    description: description ?? "",
    hashtags: hashtags ?? "",
  });
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [savedForm, setSavedForm] = useState<DetailsDraft | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [generated, setGenerated] = useState<Set<ApiMetadataField>>(() => new Set());
  const [generating, setGenerating] = useState<Set<ApiMetadataField>>(() => new Set());
  const [generateErrors, setGenerateErrors] = useState<Partial<Record<ApiMetadataField, string>>>({});
  const [descriptionReviewCleared, setDescriptionReviewCleared] = useState(false);

  if (readOnly) {
    return (
      <div className="flex flex-col gap-3">
        <ReadOnlyDetails draft={form} />
        {descriptionNeedsReview ? (
          <p className="rounded-md border border-warn bg-ink p-3 text-sm text-warn">
            Description generation failed. Send this teaching back with a note.
          </p>
        ) : null}
        {onSendBack ? (
          <Button onClick={onSendBack} className="w-full sm:w-fit">Send back with note</Button>
        ) : null}
      </div>
    );
  }

  const detailsDirty = savedForm
    ? (Object.keys(form) as (keyof DetailsDraft)[]).some((key) => form[key] !== savedForm[key])
    : form.title !== sermon.title ||
      form.speaker !== sermon.speaker ||
      form.series !== sermon.series ||
      form.date !== sermon.date ||
      form.description !== (description ?? "") ||
      form.hashtags !== (hashtags ?? "");
  const updateField = (field: keyof DetailsDraft, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setSaveState("idle");
    if (field === "title" || field === "description" || field === "hashtags") {
      setGenerated((current) => {
        if (!current.has(field)) return current;
        const next = new Set(current);
        next.delete(field);
        return next;
      });
    }
  };
  const generateField = (field: ApiMetadataField) => {
    if (generating.has(field)) return;
    if (!isLive) {
      onToast("Metadata generation is available in the live console.", "info");
      return;
    }
    setGenerating((current) => new Set(current).add(field));
    setGenerateErrors((current) => ({ ...current, [field]: undefined }));
    void writeApi.generateMetadata(sermon.id, field)
      .then((result) => {
        updateField(field, result.value);
        setGenerated((current) => new Set(current).add(field));
        if (field === "description" && !result.needs_review) setDescriptionReviewCleared(true);
        onToast(`${field} generated.`);
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "Generation failed. Try again.";
        setGenerateErrors((current) => ({ ...current, [field]: message }));
      })
      .finally(() => {
        setGenerating((current) => {
          const next = new Set(current);
          next.delete(field);
          return next;
        });
      });
  };
  const generateControl = (field: ApiMetadataField) => {
    const busy = generating.has(field);
    const label = FIELD_LABELS[field];
    if (!form[field].trim()) {
      return (
        <Button
          data-testid={`generate-${field}`}
          aria-label={`Generate ${label}`}
          aria-busy={busy}
          onClick={() => generateField(field)}
          disabled={busy}
          className="min-w-[7rem] px-3"
        >
          {busy ? "Generating…" : "Generate"}
        </Button>
      );
    }
    return (
      <Menu
        label={`Replace ${label} generation options`}
        triggerTestId={`generate-${field}`}
        triggerClassName={buttonClass("secondary", "min-w-[7rem] px-3")}
        trigger={<span className="inline-flex items-center gap-2">Replace<Icon name="chevron" className="h-4 w-4" /></span>}
        items={[{ label: `Replace ${label} with generated…`, onSelect: () => generateField(field), disabled: busy, testId: `replace-${field}` }]}
        menuClassName="w-64"
      />
    );
  };
  const fieldHeader = (field: ApiMetadataField, label: string) => (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <label htmlFor={`details-${field}`} className="text-xs font-medium text-muted">{label}</label>
      <div className="flex items-center gap-2">
        {generated.has(field) ? <span data-testid={`generated-${field}`}><Chip tone="info">Generated</Chip></span> : null}
        {generateControl(field)}
      </div>
    </div>
  );
  const fieldError = (field: ApiMetadataField) => generateErrors[field] ? (
    <p id={`generate-error-${field}`} role="alert" data-testid={`generate-error-${field}`} className="mt-1 rounded-md border border-danger bg-ink px-2 py-1 text-xs text-danger">
      {generateErrors[field]}
    </p>
  ) : null;
  const saveDetails = () => {
    const patch: DetailsPatch = {
      title: form.title,
      speaker: form.speaker,
      series_title: form.series,
      recorded_date: form.date,
      description: form.description,
      hashtags: form.hashtags,
    };
    setSaveState("saving");
    Promise.resolve(onSaveDetails?.(patch))
      .then(() => {
        setSaveState("saved");
        setSavedForm({ ...form });
      })
      .catch(() => setSaveState("error"));
  };
  const regenerateDescription = () => {
    if (regenerating || !onRegenerateDescription) return;
    setRegenerating(true);
    Promise.resolve(onRegenerateDescription()).finally(() => setRegenerating(false));
  };

  return (
    <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); saveDetails(); }}>
      <div>
        {fieldHeader("title", "Title")}
        <input id="details-title" value={form.title} onChange={(event) => updateField("title", event.target.value)} aria-invalid={generateErrors.title ? true : undefined} aria-describedby={generateErrors.title ? "generate-error-title" : undefined} className={`mt-1 ${inputCls}`} />
        {fieldError("title")}
      </div>
      <Field label="Speaker" htmlFor="details-speaker">
        <input id="details-speaker" value={form.speaker} onChange={(event) => updateField("speaker", event.target.value)} className={inputCls} />
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Series" htmlFor="details-series">
          <input id="details-series" value={form.series} onChange={(event) => updateField("series", event.target.value)} className={inputCls} />
        </Field>
        <Field label="Date" htmlFor="details-date" hint={`Recorded ${formatDate(form.date)}`}>
          <input id="details-date" type="date" value={form.date} onChange={(event) => updateField("date", event.target.value)} className={inputCls} />
        </Field>
      </div>
      <div>
        {fieldHeader("description", "Description")}
        <textarea id="details-description" value={form.description} onChange={(event) => updateField("description", event.target.value)} aria-invalid={generateErrors.description ? true : undefined} aria-describedby={generateErrors.description ? "generate-error-description" : undefined} rows={4} className={`mt-1 w-full min-w-0 rounded-md border border-line bg-ink px-3 py-2 text-sm text-mist`} />
        {fieldError("description")}
        {descriptionNeedsReview && !descriptionReviewCleared ? (
          <div role="alert" className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-danger bg-ink p-3 text-sm text-danger">
            <span className="font-semibold">Description generation failed - retry.</span>
            {onRegenerateDescription ? <Button variant="secondary" onClick={regenerateDescription} disabled={regenerating} aria-busy={regenerating}>{regenerating ? "Queueing…" : "Retry generation"}</Button> : null}
          </div>
        ) : null}
      </div>
      <div>
        {fieldHeader("hashtags", "Hashtags")}
        <input id="details-hashtags" value={form.hashtags} onChange={(event) => updateField("hashtags", event.target.value)} aria-invalid={generateErrors.hashtags ? true : undefined} aria-describedby={generateErrors.hashtags ? "generate-error-hashtags" : undefined} placeholder="#faith #hope" className={`mt-1 ${inputCls}`} />
        {fieldError("hashtags")}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" variant="secondary" disabled={!onSaveDetails || !detailsDirty || saveState === "saving"}>
          {saveState === "saving" ? "Saving…" : "Save details"}
        </Button>
        <span data-testid="details-save-state" className="text-xs text-muted" aria-live="polite">
          {saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed. Try again." : saveState === "saved" && !detailsDirty ? "Saved." : detailsDirty ? "Unsaved changes" : "No unsaved changes"}
        </span>
      </div>
    </form>
  );
}
