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
| `rounded-sm` | 6px | Chips, badges, small inline pills |
| `rounded-md` | 10px | Buttons, inputs, menus, table rows |
| `rounded-lg` | 14px | Cards, panels, toasts |
| `rounded-xl` | 20px | Dialogs |

## Type scale

| Token | Size | Use |
|---|---|---|
| `text-xs` | 12px | Metadata, hints, chips, table headers |
| `--font-sm` | 13px | Dense secondary copy |
| `text-sm` / `--font-base` | 15px | Body and controls |
| `--font-lg` | 17px | Card headings |
| `text-lg` | 18px | Section headings |
| `text-2xl` / `--font-2xl` | 24px / 30px | Page title (clamped to two lines) |

Fonts: Avenir Next, Segoe UI, system-ui for prose; `ui-monospace` for times, counts, IDs, and
anything that must align in columns.

## Colour roles

All colours are CSS variables set by `.dark` and `.light` in `index.css`.

| Role | Dark | Light | Meaning |
|---|---|---|---|
| `ink` (`--bg`) | `#0e1216` | `#edf1f4` | Page background |
| `surface` | `#151b21` | `#ffffff` | Cards and panels |
| `raised` | `#1e262f` | `#f4f6f8` | Hover and nested rows |
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
decoration.

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
| `< 640` | Bottom bar, 56px targets | One column, stacked |
| `640-767` | Bottom bar | Two-column forms begin |
| `768-1023` | Left rail, top sticky header | Two-column forms, max-width copy |
| `>= 1024` | Left rail, sticky detail aside | Review grid `minmax(0,1fr) 20rem` |

The nav switches exactly once, at `md` (768px). No page may introduce horizontal overflow at
390, 768, 1024, or 1440. Long text clamps with `truncate` or `line-clamp-2` and always carries
the full value in `title`.

## Motion

Durations are 140-200ms. Hover and focus transitions only animate colour, border, and filter.
`prefers-reduced-motion` removes shimmer, sheet, menu, and stagger animation in `index.css`.
Never put essential information behind motion.
