# SermonPilot web design system

Source of truth: `web/tailwind.config.js`, `web/src/index.css`, and the primitives in
`web/src/components/ui.tsx`. Change a token there first, then the components. Do not add a
one-off variant in a page.

## Spacing

4px base. Tailwind's default scale is used, with these tokens in `index.css` for CSS-only work:

| Token | Value | Use |
|---|---|---|
| `--space-1` | 4px | Icon gap, chip padding |
| `--space-2` | 8px | Inline gaps, field hint |
| `--space-3` | 12px | Control padding, row padding |
| `--space-4` | 16px | Card padding, section gaps |
| `--space-6` | 24px | Between page sections |
| `--space-8` | 32px | Page top and horizontal rhythm |

Layout: `max-w-shell` (90rem) for the chrome, `max-w-[78rem]` for `main`, `px-4 lg:px-8`.

## Radii

| Token | Value | Use |
|---|---|---|
| `rounded-sm` | 6px | Chips, badges, small inline pills, inline row buttons |
| `rounded-md` | 10px | Buttons, inputs, menus, table rows, self-contained panels |
| `rounded-lg` | 14px | Cards, panels, toasts |
| `rounded-xl` | 20px | Dialogs and the top corners of a bottom sheet |

No bare `rounded`, arbitrary radii, or `rounded-2xl` in page code.

## Type scale

Tailwind is configured to this scale in `web/tailwind.config.js`; no page uses an arbitrary font size.

| Token | Size / line height | Use |
|---|---|---|
| `text-xs` | 12px / 16px | Metadata, hints, chips, table headers |
| `text-sm` | 13px / 20px | Dense secondary copy, control labels, row titles |
| `text-base` | 15px / 24px | Body copy and prose |
| `text-lg` | 17px / 22px | Card and section headings |
| `text-xl` | 18px / 24px | Reserved for page subheads |
| `text-2xl` | 24px / 30px | Page title (clamped to two lines) |

The document body defaults to 15px. Fonts: Avenir Next, Segoe UI, system-ui for prose;
`ui-monospace` for times, counts, IDs, and anything that must align in columns.

Inputs, selects and textareas render at 16px below 768px so iOS does not zoom the page on focus.

## Colour roles

All colours are CSS variables set by `.dark` and `.light` in `index.css`.

| Role | Dark | Light | Meaning |
|---|---|---|---|
| `ink` (`--bg`) | `#0e1216` | `#edf1f4` | Page background |
| `surface` | `#151b21` | `#ffffff` | Cards and panels |
| `raised` | `#1e262f` | `#f4f6f8` | Hover and nested rows |
| `selected` | `#26313d` | `#cfdae4` | Selected rail row, filter chip, row hover |
| `selected-border` | `#3a4a5c` | `#b3c2d2` | Border on a selected chip |
| `line` | `#2b3540` | `#d7dfe6` | Borders and dividers |
| `mist` (`--text`) | `#e9edef` | `#141a20` | Body text |
| `muted` | `#9aa7b4` | `#5a6a77` | Secondary text and hints |
| `accent` | `#8b7cf6` | `#5746d8` | Primary action, focus ring |
| `accentInk` | `#12101f` | `#ffffff` | Text on accent |
| `ok` | `#3ecf8e` | `#177a4c` | Success, processed |
| `warn` | `#e8b23e` | `#8a5a05` | Needs attention, pending review |
| `danger` | `#f0616d` | `#c22f3d` | Errors and destructive actions |
| `info` | `#5eb2f0` | `#1d6fb8` | Neutral information, applied locally |

Status semantics are fixed: `ok` = done/healthy, `warn` = waiting for a person, `danger` =
failed, `info` = running/applied, `neutral` = draft/unknown. A chip never changes tone for
decoration. `accent` is reserved for the primary action and the focus ring.

### Selected surface

Use `selectedClass` from `ui.tsx` (`bg-selected text-mist border-selected-line`) for a selected
rail row, the settings rail, and Activity filter chips. Row hover uses `bg-selected`. The light
theme selected surface measures 1.25:1 against the page, above the 1.2:1 floor.

### Shadows

| Token | Value | Use |
|---|---|---|
| `shadow-menu` | `0 8px 24px -12px rgb(0 0 0 / 0.45)` | Menus, combobox panels, dialogs, toasts |
| `shadow-sticky` | `0 -8px 24px -16px rgb(0 0 0 / 0.5)` | Bottom action bars and sticky save bars |

Do not add another shadow for the same role. Controls may use `shadow-sm` for a micro lift.

### Measured contrast (light theme)

| Sample | Ratio | Requirement |
|---|---|---|
| Body text `#141a20` on page `#edf1f4` | 15.43:1 | AA (4.5:1) |
| Muted `#5a6a77` on surface `#ffffff` | 5.58:1 | AA (4.5:1) |
| Disabled label (45% text over surface) | 2.90:1 | Exempt, disabled control |

Dark: body 15.96:1, muted 7.07:1, accent ink on accent 6.42:1.

## Control heights

| Element | Height |
|---|---|
| Chip | 24px minimum |
| Button, input, select, switch hit area | 44px minimum |
| List row | 56px minimum |
| Library row / job expanded row | 64px minimum |
| Meter (vertical service level) | 40px |
| Logo and avatar | 32px |

Icon-only controls are always 44x44 and always carry an `aria-label` plus `title`. Toggles use
`role="switch"` and `aria-checked`.

## Control vocabulary

### Button (`Button`, `buttonClass`)

- `primary`: accent fill, accent-ink text. One per view. Approve, save, submit.
- `secondary`: raised fill, line border. The default. Cancel, retry, reveal.
- `ghost`: no fill or border, muted text. Inline low-priority actions such as undo.
- `danger`: transparent with danger border, fills on hover. Reject, delete, restore.

Never place a second primary beside the first. Secondary actions belong in `Menu`.

### Menu (`Menu`)

A labelled trigger (`aria-haspopup="menu"`, `aria-expanded`, `aria-controls`) with a chevron,
and a `role="menu"` panel of `role="menuitem"` buttons. Arrow keys, Home/End, Escape, focus
return, and outside click are handled by the primitive. Use a menu for overflow, not for the
primary path. Triggers read as a verb (`More actions`, `Replace`, `Library actions`).

### Chip (`Chip`)

24px pill for state only: plan status, teaching status, file kind, service health. Uppercase,
mono, 12px. Not clickable.

`StatusChip` accepts a lifecycle state and no free text. The six labels and tones:

| State | Label | Tone |
|---|---|---|
| `draft` | `Draft` | `neutral` |
| `needs_review` | `Needs review` | `warn` |
| `processing` | `Processing` | `info` |
| `ready` | `Ready to publish` | `ok` |
| `published` | `Published` | `ok` |
| `failed` | `Failed` | `danger` |

### Input and select

`inputCls`, 44px, `bg-ink`, line border, accent border on focus. Labels are always visible
(`Field` or a `<label>`); placeholders are examples, never labels. Dates keep the native date
input and repeat the human date underneath.

### Switch

`Switch` is the compact table/row control; `Toggle` is the full-width labelled settings row.
Both expose `role="switch"` and `aria-checked`. Use `Switch` where the label lives in the
surrounding row, `Toggle` where the control is the row.

### Toast (`useToast`, `ToastHost`)

Bottom-centre on mobile, bottom-right on desktop, max three at once. Success and info use
`role="status"` + `aria-live="polite"`; errors use `role="alert"` + `aria-live="assertive"`.
Hover and focus pause the timer. Destructive actions offer Undo in the toast.

## Layout breakpoints

| Width | Navigation | Content |
|---|---|---|
| `< 640` | Bottom bar, 56px targets | One column, stacked; Library filters open in a 90dvh sheet |
| `640-767` | Bottom bar | Two-column forms begin; Library filter controls join the search row |
| `768-1023` | Left rail, top sticky header | Two-column forms, max-width copy; Library rows stay two-line |
| `>= 1024` | Left rail, sticky detail aside | Review grid `minmax(0,1fr) 20rem`; Library gains the series column |

The nav switches exactly once, at `md` (768px). The teaching workspace switches to two columns
at `lg` (1024px); tabs become accordion rows below `md`. Interactive controls use
`touch-action: manipulation`, and hover styles are gated behind `@media (hover: hover) and
(pointer: fine)` by Tailwind's `hoverOnlyWhenSupported`. Sheets are capped at `90dvh` with
`overscroll-behavior: contain`. No page may introduce horizontal overflow at 320, 390, 768,
1024, or 1440. Long text clamps with `truncate` or `line-clamp-2` and always carries the full
value in `title`.

## Motion

Durations are 140-200ms. Hover and focus transitions only animate colour, border, and filter.
`prefers-reduced-motion` removes shimmer, sheet, menu, and stagger animation in `index.css`.
Never put essential information behind motion.
