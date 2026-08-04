# Implementation spec: split AI admin into AI 渠道 and LangChain 策略 pages

Companion to `docs/decisions/0003-split-provider-admin-pages.md`.
Target: replace the single `/settings/providers` page with two independent
pages under a new sidebar group `管理`.

## 1. Sidebar changes — `frontend/components/layout/Sidebar.tsx`

- Remove `{ href: "/settings/providers", label: "AI Provider", icon: CpuIcon, section: "tools" }`.
- Add two items with `section: "admin"`:
  - `{ href: "/settings/channels", label: "AI 渠道", icon: CpuIcon, section: "admin" }`
  - `{ href: "/settings/policy", label: "LangChain 策略", icon: GitBranchIcon, section: "admin" }`
- Add `adminItems` filter beside `toolItems`, gated by `isAdminUser(user)`
  (same guard used for providers today).
- After the `工具` label/divider block, render a second divider + label
  `管理` + admin items, only when `adminItems.length > 0`.

Icon: use an existing icon from `@/components/ui/icons`; if no branch icon
exists there, add `GitBranchIcon` to `frontend/components/ui/icons.tsx`
(lucide `GitBranch`), keep `strokeWidth={1.9}` sizing convention.

## 2. Routes

- Create `frontend/app/settings/channels/page.tsx` (AI 渠道).
- Create `frontend/app/settings/policy/page.tsx` (LangChain 策略).
- Remove `frontend/app/settings/providers/page.tsx`.
- Preserve old bookmarks: add a redirect from `/settings/providers` to
  `/settings/channels` in `frontend/next.config.mjs` redirects.

## 3. Shared extraction

- Move `flattenModels(channels): { channel, model }[]` out of
  `providers/page.tsx` into `frontend/features/settings/modelOptions.ts`
  and export it. Both pages import it.
- Keep `frontend/features/settings/types.ts` and `api.ts` unchanged;
  `useAiChannelMutations().remove` (DELETE) stays available but the UI keeps
  禁用渠道 as the only destructive surface (do not add a delete button).

## 4. Page A — `/settings/channels` (AI 渠道)

Reuse the channel half of the current providers page:

- Header: `Heading order={2}` "AI 渠道", subtitle "管理 AI 服务商连接、密钥与模型目录".
- Channel list column: card buttons (display_name, `provider · models.length 个模型`,
  Badge `已连接`/`缺少密钥`, extra Badge `已禁用` when `!enabled`).
- Draft form: 渠道 ID (disabled when editing), 显示名称, Provider 来源
  (PROVIDERS options with `PROVIDER_DEFAULT_URLS` autofill), Base URL.
- Secret row: `PasswordInput` + Button `验证并保存` (`saveSecret`):
  placeholder `留空表示保留现有密钥` when `has_secret`; notify with
  `已同步 N 个模型。Tool Calling 与 Vision 默认关闭，请逐项确认。`
  and latency line; handle `policy_cleared` warning pointing to the policy page.
- Actions: `保存渠道` (primary), `同步模型`, `禁用渠道` (danger, confirm via
  `confirmAction`, only when `enabled`), `刷新`.
- Model catalogue: grouped by `source`, per-model row with Checkbox
  `启用` / `Tool` / `Vision`, "能力未确认" hint when neither capability set.
- Keep `ErrorBanner`; keep `policy_cleared` toasts with copy
  "LangChain 策略已清除，请到「LangChain 策略」页重新选择三个阶段模型。"
- Remove: STAGES, policyDraft, activePolicy, savePolicy, selectionFor,
  modelOptions (now shared), and the whole bottom policy block.

## 5. Page B — `/settings/policy` (LangChain 策略)

Standalone full-width block:

- Header: `Heading order={2}` "LangChain 策略", subtitle
  "后续新 run 使用此策略；运行中的 run 保留已冻结快照。"
- Metadata row: Badge `策略版本 v{version}` + `Text` updated_at (formatted,
  or "未保存过" when null).
- Source of truth: `useAiChannels(!loading && isAdmin)`; policy draft
  initialised from `data?.policy`; options from `flattenModels(items)`.
- Three `FormControl` blocks (Vision / OCR, Agent, Review):
  - Select value encoded `channel_id::model_id`, options only from
    `model.enabled`; vision stage filters `model.capability.vision`,
    agent/review filter `model.capability.tool_calling`; disabled option
    suffix `（能力未启用）` when filtered out.
  - Caption per stage: "必须启用 Vision" / "必须启用 Tool Calling".
- Empty states:
  - No channels: "请先连接渠道并同步模型。" (link to `/settings/channels`).
  - Policy null/cleared: warning Flash "策略已被清除，请重新选择三个阶段模型。"
- Save: `Button variant="primary"` `保存阶段策略`, disabled until all three
  stages selected; on success `notify.success` with
  `策略版本 {result.policy.version} 将用于后续新 run。`
- Keep `ErrorBanner` for failures.

## 6. Interaction spec

| Element | Trigger | Behavior | Errors | Notes |
|---------|---------|----------|--------|-------|
| Channel card | click | load draft + secret placeholder | — | resets secret input |
| 验证并保存 | click | POST credential; notify discovery + validation latency | fail → ErrorBanner + notify danger | clears secret input on success |
| 保存渠道 | click | PATCH metadata | disabled when id/name empty | policy_cleared → warning |
| Model checkbox | change | PATCH model enabled/capability | policy_cleared → warning | optimistic via react-query refresh |
| 禁用渠道 | click | confirmAction → PATCH enabled:false | — | only when enabled |
| Stage Select | change | update policy draft | — | value `channel::model` |
| 保存阶段策略 | click | PUT policy | disabled until all stages set | success → version notify |

## 7. Visual compliance checklist

- Use `ui/primitives` Box/Button/FormControl/Heading/Select/Text/TextInput/Spinner.
- Mantine subcomponents only where the current page already uses them
  (Badge, Checkbox, Switch via ToggleSwitch, PasswordInput).
- lucide-react icons, `size={16}` convention.
- `sx` object syntax; responsive arrays `["1fr", "280px minmax(0, 1fr)"]`.
- Semantic colors: `fg.muted`, `fg.danger`, `border.default`, `border.muted`.
- Light/dark theme via existing `data-oopsnote-color-scheme` variables; no new
  hard-coded colors.

## 8. Verification

- `npm run lint` / `tsc` in `frontend/`.
- Manual: admin sees both pages under 管理; non-admin sees neither.
- Manual: create/secret/sync/model-toggle flows on channels page; policy
  edit + save on policy page; disable a channel used by policy → policy page
  shows cleared state.
- Per AGENTS.md: rebuild and publish production Docker after the change
  (or explicitly report skip at user request).
