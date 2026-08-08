---
version: 1.0.0
name: OopsNote Graphite Workbench
status: canonical
description: A quiet, precise, content-first workbench for capturing, reviewing, organizing, and printing academic questions. Neutral graphite chrome keeps attention on problem content; semantic color communicates state, never decoration.

colors:
  action: "{colors.graphite-9}"
  action-hover: "{colors.graphite-8}"
  focus: "#2563eb"
  canvas-light: "#ffffff"
  canvas-dark: "#09090b"
  surface-light: "{colors.graphite-1}"
  surface-dark: "{colors.graphite-9}"
  border-light: "{colors.graphite-2}"
  border-dark: "{colors.graphite-8}"
  ink-light: "{colors.graphite-9}"
  ink-dark: "{colors.graphite-0}"
  muted-light: "{colors.graphite-5}"
  muted-dark: "{colors.graphite-4}"
  success: "#15803d"
  warning: "#b45309"
  danger: "#dc2626"
  info: "#2563eb"
  graphite-0: "#fafafa"
  graphite-1: "#f4f4f5"
  graphite-2: "#e4e4e7"
  graphite-3: "#d4d4d8"
  graphite-4: "#a1a1aa"
  graphite-5: "#71717a"
  graphite-6: "#52525b"
  graphite-7: "#3f3f46"
  graphite-8: "#27272a"
  graphite-9: "#18181b"

typography:
  family-ui: "Inter, Noto Sans SC, HarmonyOS Sans, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
  family-brand: "OopsNoteFont, Inter, Noto Sans SC, sans-serif"
  family-mono: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace"
  caption: "12px / 1.45 / 400"
  label: "13px / 1.35 / 600"
  body-sm: "14px / 1.5 / 400"
  body: "16px / 1.55 / 400"
  title-sm: "16px / 1.4 / 600"
  title: "20px / 1.35 / 650"
  page-title: "24px / 1.25 / 650"
  display: "32px / 1.2 / 650"

spacing:
  0: "0px"
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "24px"
  6: "32px"
  7: "40px"
  8: "48px"
  9: "64px"

rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  shell: "16px"
  full: "9999px"

components:
  button-primary: "graphite action fill, inverse label, 32-40px high, 6px radius"
  button-secondary: "canvas fill, hairline border, default ink, 32-40px high, 6px radius"
  button-tertiary: "transparent fill, default or muted ink, no persistent border"
  icon-button: "square stable target, icon only, accessible name required"
  text-input: "canvas fill, hairline border, 36-40px high, 8px radius"
  card: "flat canvas or subtle surface, hairline border, at most 8px radius"
  panel: "structural region, usually unframed; 12px radius only for modal or isolated tool"
  status-badge: "semantic subtle fill, semantic ink, compact pill reserved for status"
  notification-error: "persistent until explicit dismissal"
  page-header: "24px title, 14px muted description, actions aligned to the opposite edge"
---

# OopsNote Design System

This file is the visual contract for OopsNote. It governs the Web application and any future design artifact. `AGENTS.md` governs engineering behavior; this file governs visual and interaction behavior.

## Product Character

OopsNote is a local-first academic question-management workbench. It is used repeatedly to capture source material, inspect OCR and AI results, edit questions, classify mistakes, assemble papers, and diagnose failed work.

The interface must feel:

- quiet rather than promotional;
- precise rather than playful;
- dense but orderly rather than spacious for its own sake;
- content-first rather than card-first;
- trustworthy about progress, failure, and saved state;
- equally intentional in light and dark modes.

The product's personality comes from the OopsNote wordmark, real academic content, diagrams, page imagery, and restrained motion. Decorative gradients, floating shapes, generic illustration, and ornamental card stacks are not part of the product language.

## Reference Synthesis

This system preserves OopsNote's existing graphite shell and strengthens it with three references from [awesome-design-md](https://github.com/VoltAgent/awesome-design-md):

| Reference | Adopt | Reject |
| --- | --- | --- |
| [Linear](https://getdesign.md/design-md/linear.app/DESIGN.md) | 4px rhythm, surface ladder, hairline depth, compact controls, scarce accent, real product content as the protagonist | dark-only presentation, lavender branding, marketing-scale display type, negative tracking |
| [Cal.com](https://getdesign.md/design-md/cal/DESIGN.md) | monochrome action layer, clear primary/secondary actions, real UI instead of decorative mockups, restrained shadow | marketing whitespace, repeated 12-16px cards, pill-heavy grouped navigation |
| [Notion](https://getdesign.md/design-md/notion/DESIGN.md) | content-first hierarchy, calm chrome, readable body rhythm, borders before shadows | warm beige canvas, sticker palette, pill CTAs, decorative hero treatment |

The references are observational analyses, not upstream product specifications. OopsNote does not copy their brand colors, typography, or marketing composition.

## Source Of Truth

Visual authority is ordered as follows:

1. `DESIGN.md` defines intent, usage, and allowed exceptions.
2. `frontend/app/design-tokens.css` owns raw color, spacing, type, radius, shadow, motion, and layout values.
3. `frontend/theme.ts` adapts those CSS variables to Mantine.
4. `frontend/components/ui/primitives.tsx` adapts legacy `sx` call sites to the same variables.
5. Components consume semantic tokens and shared primitives. They do not create local palettes.

Feature CSS may define geometry that belongs to its domain, such as an image crop handle or a paper aspect ratio. It may not redefine global color, typography, action hierarchy, or elevation. Raw rendering colors are limited to source-image/SVG processing, application icon metadata, and the batch-selection overlay. Functional gradients are limited to spatial masks, in-progress selection borders, and data-distribution tracks; every exception is named in the design audit.

## Color

### Neutral foundation

Graphite is the only structural palette. The light canvas is white with graphite-1 for quiet regions. The dark canvas is near-black with graphite-9 and graphite-8 as lifted surfaces.

Primary actions use graphite ink. OopsNote does not require a saturated brand color to make an action look primary.

### Semantic color

- Blue: focus, information, and links where link affordance is otherwise ambiguous.
- Green: successful completion and confirmed healthy state.
- Amber: warning, queued review, or attention required.
- Red: destructive action, failure, invalid state, or persistent error notification.

Semantic color must retain its meaning. Do not use success green as decoration or danger red as a general accent.

### Contrast and dark mode

- Body text must meet WCAG AA against its surface.
- Muted text must remain readable; it is not disabled text.
- Every semantic foreground must have a paired subtle background in both schemes.
- Light and dark modes preserve hierarchy, not literal values.
- Raw hex, `rgb()`, and `rgba()` values belong only in the token source or in documented image/canvas rendering exceptions.

## Typography

The UI uses one sans-serif voice. Inter is preferred; Chinese falls through to Noto Sans SC or HarmonyOS Sans. The custom OopsNote font is reserved for the product wordmark. Monospace is reserved for IDs, code, logs, paths, and machine output.

Rules:

- Page titles are 24px, not hero-scale.
- Compact panel titles are 16-20px.
- Default UI copy is 14px; long-form problem content may use 16px.
- Labels use 13px at weight 600.
- Body weight is 400; emphasis is normally 600 or 650.
- Letter spacing is 0. Do not import marketing-style negative tracking.
- Font size does not scale with viewport width. Responsive layout changes wrapping and composition instead.
- Use tabular numerals for counts, durations, quotas, and progress.

## Spacing And Density

The canonical scale is 4, 8, 12, 16, 24, 32, 40, 48, and 64px.

- 4px: icon/text micro-gap, tightly related controls.
- 8px: field internals, compact row gaps.
- 12px: normal control and list-row gap.
- 16px: default group gap and compact panel padding.
- 24px: page section gap and standard panel padding.
- 32px: desktop page gutter or major separation.
- 40-64px: empty states and exceptional page-level breathing room.

Repeated operational rows should be compact. Empty states may breathe. Do not use large marketing-section spacing inside settings, lists, task views, or editors.

## Shape

- 4px: tiny chips, code blocks, dense menu items.
- 6px: buttons, navigation rows, compact controls.
- 8px: inputs, repeated cards, notifications, normal framed content.
- 12px: modals, isolated tools, media wells, authentication panel.
- 16px: application content shell only.
- Full radius: avatars, status dots, and genuine segmented/pill controls only.

Do not use rounded rectangles as decoration. Do not use pill shapes for ordinary commands. Repeated cards must not exceed 8px radius.

## Elevation

Hierarchy is built in this order:

1. spacing;
2. surface change;
3. hairline border;
4. shadow, only when an element actually floats.

Flat cards use no shadow. Hover may strengthen the border but must not shift layout. Menus, popovers, modals, and drag previews may use medium or floating shadows. Avoid glassmorphism, atmospheric glow, and stacked card-on-card composition.

## Layout

### Application shell

- Desktop title bar: 58px.
- Expanded primary sidebar: 208px.
- Collapsed primary rail: 58px.
- Context sidebar: 240px.
- Main content uses a stable constrained gutter and scrolls independently.
- The content shell may use its existing 16px top-left radius; inner page sections remain unframed.

### Responsive behavior

- Mobile: below 544px. Primary sidebar disappears; core navigation moves to the bottom bar.
- Compact/tablet: 544-1023px. Grids reduce columns and secondary tools become drawers.
- Desktop: 1024px and above. Preserve dense, side-by-side workflows.
- Touch targets are at least 44px on coarse pointers, even when the visible control is smaller.
- Fixed-format viewers, boards, steppers, and toolbars use stable dimensions and do not resize when labels or state change.
- Text wraps before it overlaps. Long identifiers truncate with an accessible full-value affordance.

## Components

### Buttons

- Use `Button` for commands with text.
- Leading icons use `leadingVisual`; trailing icons use `trailingVisual`.
- Use `IconButton` for icon-only commands and provide `aria-label`.
- Primary is reserved for the next or most consequential non-destructive action in the current scope.
- Destructive buttons use the danger variant, never the primary neutral fill.
- Button groups represent one choice or a tightly related tool set; unrelated commands must not be segmented together.
- Loading and disabled states preserve dimensions.

### Forms

- Labels remain visible; placeholders are examples, not labels.
- Inputs use 8px radius and 36-40px visual height.
- Validation tied to a field stays inline and is announced accessibly.
- Request or system failures use persistent notifications.
- Save state must distinguish saving, saved, and failed. Failed must never look saved.

### Navigation

- Active navigation uses surface and border/indicator changes, not a saturated fill.
- Icons and labels align on one baseline.
- Collapsed navigation provides tooltips or native titles.
- Navigation density remains stable between routes.

### Cards and panels

- A card represents one repeatable entity such as a task, question, draft, or member.
- A page section is not automatically a card.
- Do not nest cards. Use dividers, subheadings, or layout regions inside a card.
- Operational lists should prefer rows or tables when comparison matters.

### Notifications and errors

- Success and informational notifications may auto-close.
- Error notifications never auto-close; the user dismisses them explicitly.
- All red notifications are normalized by `frontend/lib/notify.ts`; callers cannot opt them back into auto-close. Identical error evidence receives one stable notification ID.
- React Query cache failures and browser-level unhandled errors report through the same notification path, so a page does not need to remember a second global error mechanism.
- Page-level request failures use notifications instead of raw red body text.
- A local rendering failure may keep an inline diagnostic to identify the broken object, and must also raise an error notification.
- Error messages preserve actionable detail and must not expose secrets.

### Empty, loading, and progress states

- Empty states explain what is absent and expose the most relevant next action when one exists.
- Skeletons or stable spinners occupy the final layout region; loading must not cause large jumps.
- Progress communicates the current stage, not only an indeterminate animation.
- Animations respect `prefers-reduced-motion`.

### Academic content

- Problem text, options, formulas, tables, and diagrams are the visual protagonist.
- Do not crop primary source imagery when the user needs to inspect it.
- OopsMark output must remain readable at narrow widths and printable without UI chrome.
- Monospace is for machine content; mathematical notation uses the established KaTeX pipeline.

## Motion

- Fast feedback: 150ms.
- Normal UI transition: 250ms.
- Slow transitions are exceptional and capped near 400ms.
- Animate opacity, color, and small transforms. Avoid perpetual decorative motion.
- No entrance animation may delay interaction.
- Progress animation is allowed only while work is active.

## Do

- Let real questions, diagrams, scans, and generated papers provide visual interest.
- Use graphite surfaces and semantic status colors consistently.
- Prefer borders and spacing over shadows.
- Keep repeated workflows compact and scannable.
- Preserve explicit state and failure evidence.
- Verify light, dark, desktop, tablet, mobile, keyboard, and reduced-motion behavior.

## Do Not

- Do not copy a reference product's brand color or marketing layout.
- Do not add decorative gradients, decorative circles, glow, bokeh, or dot-grid backgrounds. Functional data and spatial masks must use a documented audit exception.
- Do not create a second local token palette.
- Do not hardcode colors, global radius, typography, or shadows in components.
- Do not use oversized hero typography inside the application.
- Do not use cards as generic page sections or nest cards.
- Do not use icon components directly beside `Button` text.
- Do not hide deterministic errors behind retries or silent fallback UI.

## Review Checklist

Before merging a frontend change, confirm:

- tokens come from the authoritative source;
- the component has default, hover/pressed, focus-visible, disabled, loading, and error states where applicable;
- icon and label alignment uses the shared Button contract;
- no text overlaps or causes control resizing;
- light and dark hierarchy match;
- mobile and coarse-pointer behavior are intentional;
- errors use the correct inline/notification boundary;
- the page remains work-focused and content-first;
- typecheck, lint, design-system audit, and relevant visual tests pass.
