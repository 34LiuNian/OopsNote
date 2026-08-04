# 0003: Split AI provider admin into channels and policy pages

Status: proposed

## Context

`/settings/providers` currently mixes two different resources on one page:

1. Channel management (provider connection, secret, model catalogue) owned by
   `POST /settings/ai/channels` and `POST /settings/ai/channels/{id}/credential`.
2. The global LangChain three-stage policy owned by `PUT /settings/ai/policy`.

The policy is a global, run-freezing configuration independent of any selected
channel. Stacking it under a channel editor makes it look like a channel
attribute and forces scrolling through channel-specific content to reach a
cross-channel setting.

User request: split into two independent pages, placed in a new sidebar group
`管理` next to the existing `工具` group, with clearer names.

## Decision

1. **Routes**
   - `/settings/channels` — AI 渠道（channel list, detail, secret, model catalogue）
   - `/settings/policy` — 阶段策略（global three-stage policy editor）

2. **Sidebar** — add a new group `管理` after `工具`:
   - 渠道 (`/settings/channels`, CpuIcon)
   - 阶段策略 (`/settings/policy`, GitBranchIcon or similar)
   Remove `AI Provider` from the `工具` group. `设置` and `渲染调试` stay.

3. **Channels page** keeps the existing channel editor surface (list card,
   draft form, secret entry with `验证并保存`, model catalogue grouped by
   source with per-model 启用/Tool/Vision checkboxes, 禁用渠道) and drops the
   policy section entirely.

4. **Policy page** is a standalone full-width block:
   - Title + frozen-snapshot hint (`后续新 run 使用此策略；运行中的 run 保留已冻结快照。`)
   - Policy version + updated_at metadata
   - Three stage selects (Vision / OCR, Agent, Review), each a
     channel `::` model combination filtered by capability
     (vision / tool_calling), same option source as today
     (`flattenModels` over enabled models)
   - 保存阶段策略 primary action
   - Empty/cleared policy state with re-select guidance

## Visual compliance

- Use OopsNote design tokens (Primer-style `fgColor`/`bgColor`/`borderColor`
  variables, `--oops-*` radius/shadow/transition) and the shared
  `ui/primitives` components; keep Mantine subcomponents
  (`Badge`, `Checkbox`, `Switch`, `PasswordInput`) and `lucide-react` icons
  consistent with the rest of the app.
- Keep light/dark theme support via `html[data-oopsnote-color-scheme]`.
- Responsive grid pattern `["1fr", "280px minmax(0, 1fr)"]` for the channel
  list/detail split; policy page uses a single-column card stack.

## Open items

- Rename options for the two entries (渠道 / 阶段策略 vs AI 渠道 / LangChain 策略).
- Whether `设置` should also move into `管理` (currently in `工具`).
- Production publish after implementation (AGENTS.md default).
