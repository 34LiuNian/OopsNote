# Batch Continuous Surface

状态：实施规格（2026-07-23 访谈定稿）

适用仓库：`E:\works\2026\OopsNote`

目标组件：`BatchContinuousSurface`、`BatchSelectionOverlay`、`BatchCropOverlay`

## 1. 最终产品定义

批量扫描把一份 PDF 处理为一条纵向连续的文档表面。页面是渲染、裁剪和导出的物理单位，不是选区交互的边界。

完整流程：

```text
导入 PDF
  -> 在任意代表页绘制一次文档裁剪框
  -> 按相同页面比例应用到本 PDF 的每一页
  -> 切换任意页并直接检查裁剪结果
  -> 确认裁剪（此后不可修改）
  -> 在单列、等宽、首尾无缝的连续页面带框题
  -> 一个 document-space 选框投影为任意数量的页面切片
  -> 自动保存 / 提交任务
```

本组件只负责 PDF 页面带、文档裁剪、选框交互和几何切片。OCR、学科识别、题目识别和 AI 生命周期仍由现有任务链路负责。

## 2. 不可变产品决策

### 2.1 单列连续表面

- 禁止任何两页并排显示。
- 删除旧的双页选择模式、左右翻页状态机和 `sourceRect + continuationRect` 交互模型。
- 宽屏仍然只显示单列 PDF；左右空余空间由业务侧栏使用。
- 裁剪后的所有页面按相同显示宽度排列，页面首尾无几何间隙。
- 页面边界可以用不占高度的细线提示，但 document-space 不得加入页面 gap。
- 跨页选框的边界必须在页面接缝处视觉连续。

### 2.2 一次性文档裁剪

草图中的蓝框定义为 `DocumentCropRect`：

```ts
type NormalizedRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type DocumentCropRect = NormalizedRect;
```

- 用户可以先切换到任意代表页，再绘制一次蓝色裁剪框。
- 裁剪框按页面宽高比例（`0..1`）应用到当前 PDF 的每一页，不复制绝对像素值。
- 绘制阶段允许移动裁剪框和使用八方向手柄调整。
- 绘制后，连续页面带按需加载并直接显示裁剪结果；被裁掉的内容不显示，也不使用灰色蒙层作为主要检查模式。
- 用户可以切换到任意页检查相同裁剪框的结果。
- 检查不创建逐页裁剪框；所有页面仍共享同一个 `DocumentCropRect`。
- 点击“确认裁剪并开始框题”后，裁剪框永久锁定，不提供重新裁剪。
- 如果裁剪错误，唯一恢复方式是从“最近文件”菜单删除整次 batch session，再重新导入。
- 原始 PDF 始终保留；显示和导出使用派生裁剪坐标，不覆盖源文件。
- 未来可以增加单页裁剪覆盖值，但当前版本不实现、不显示相关 UI。

`DocumentCropRect` 保存在 batch session 根部。session 恢复时必须先恢复裁剪，再恢复选区。

### 2.3 一个跨页选框只有一份状态

```ts
type DocumentPoint = { x: number; y: number };
type DocumentRect = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

type SelectionSlice = {
  pageId: string;
  pageIndex: number;
  rect: NormalizedRect;
  order: number;
};

type SelectionModel = {
  id: string;
  start: DocumentPoint;
  end: DocumentPoint;
  rect: DocumentRect;
  slices: SelectionSlice[];
  questionNo: number;
  status: "pending" | "processing" | "completed" | "failed";
  taskId?: string;
  error?: string;
};
```

- 跨页在逻辑上始终是一个 `DocumentRect`。
- 页面切片只是这个矩形与各页求交后的投影。
- 拖动任一手柄修改同一个矩形，所有页面切片同步变化。
- 不允许单独调整某一页切片的宽高。
- 不允许拖动选框内部来移动整个选框；只允许八方向缩放。
- 允许不同题目选框互相重叠。

## 3. 组件边界

### 3.1 `BatchContinuousSurface`

负责：

- 创建裁剪后页面的等宽、无缝连续页面带。
- 维护页面顺序、稳定占位尺寸和 document-space 几何。
- 按需渲染视口附近页面，管理预取和有限缓存。
- 在滚动、缩放和侧栏开合时保持坐标稳定。
- 提供屏幕坐标、document-space 和原始页面像素之间的转换。
- 提供当前可视页和页码跳转接口。

不负责 session REST、任务创建、通知、路由或 AI 状态轮询。

### 3.2 `BatchCropOverlay`

负责：

- 在任意当前页创建一份 `DocumentCropRect`。
- 确认前移动和八方向调整裁剪框。
- 输出按比例应用到所有页的裁剪值。
- 在预览阶段切换页面时保持同一份裁剪状态。

确认后组件退出编辑态，不再允许修改。

### 3.3 `BatchSelectionOverlay`

负责：

- 创建、选择、取消和八方向调整一个 document-space 选区。
- 透明绘制选框内部、连续边界和跨页投影。
- 输出 `SelectionModel`，不直接保存或提交。
- 处理 pointer capture、自动滚动、`Esc`、`pointercancel`、失焦、页面隐藏和卸载清理。
- 允许通过右侧列表选中被重叠选框遮挡的选区。

### 3.4 纯几何模块

`batchContinuousGeometry.ts` 不依赖 React 或 DOM，至少包含：

```ts
buildPageMetrics(...)
screenToDocumentPoint(...)
pageToDocumentPoint(...)
documentToPagePoint(...)
intersectSelectionWithPage(...)
splitSelectionAcrossPages(...)
mapSelectionToCroppedSource(...)
mapCroppedRectToOriginalSource(...)
```

DOM 测量和纯计算不得混在一起。

## 4. 仓库和组件库策略

第一阶段在 OopsNote 仓库内实现，不创建独立 npm 包：

```text
frontend/components/batch-continuous/
  BatchContinuousSurface.tsx
  BatchCropOverlay.tsx
  BatchSelectionOverlay.tsx
  batchContinuousGeometry.ts
  batchContinuousTypes.ts
  batchContinuous.css
  index.ts

frontend/features/upload/adapters/
  batchPageSourceAdapter.ts
  batchSessionSelectionAdapter.ts
  batchSelectionExportAdapter.ts
```

通用组件禁止 import upload API、Next router、通知系统或 OopsNote session DTO。业务 adapter 负责 PDF、REST、session、裁图和任务。

只有 core 没有 OopsNote 私有依赖、React 层有独立 fixture、真实项目回归稳定且出现第二个消费者后，才考虑拆为：

```text
@oopsnote/continuous-selection-core
@oopsnote/continuous-selection-react
```

## 5. 页面几何和渲染

```ts
type PageMetric = {
  pageId: string;
  pageIndex: number;
  sourceWidth: number;
  sourceHeight: number;
  crop: DocumentCropRect;
  croppedSourceWidth: number;
  croppedSourceHeight: number;
  documentTop: number;
  documentBottom: number;
  displayWidth: number;
  displayHeight: number;
};
```

- 所有裁剪页面使用同一 `displayWidth`。
- `displayHeight` 按每页裁剪后宽高比计算。
- 下一页的 `documentTop` 必须等于上一页的 `documentBottom`。
- PDF 元数据必须在 bitmap 渲染前提供源宽高，用于建立稳定占位。
- 页面加载失败仍保留准确占位和错误状态，后续页面不能塌陷。
- 首屏只渲染视口附近页面；建议前后各预取 2 页。
- 页面 bitmap 使用有限 LRU 缓存；10 页 PDF 不得一次性解码全部页面。
- 导出只解码选区实际涉及的页面。

## 6. 裁剪工作流

### 6.1 页面导航

- 左侧栏用于页面导航，不显示缩略图。
- 显示页码列表和当前可视页，点击页码滚动连续页面带。
- 裁剪阶段也可以通过页码切换代表页和检查页。
- 页码跳转同时保留在 PDF 视图控制条中。
- 不显示上一页、下一页按钮。

### 6.2 裁剪状态

```text
unconfigured
  -> drawing
  -> previewing (连续页面带直接显示裁剪结果)
  -> editing (可返回代表页继续调整)
  -> confirmed (永久锁定)
```

- 确认前允许返回编辑态。
- 确认后不允许返回，不实现 undo/redo。
- 选题交互只能在 `confirmed` 后启用。

## 7. 选区交互

### 7.1 创建

- 只接受主按钮和裁剪后页面内容区域。
- `pointerdown` 记录 document-space 起点并设置 pointer capture。
- 普通拖动使用 `clientX/clientY`，不依赖 `movementX/movementY` 累加。
- 接近视口上下边缘时自动滚动，十字光标和选框持续使用同一坐标系。
- Pointer Lock 不是核心模型；如果实现，只能作为浏览器边界增强，不能在 `pointerdown` 立即申请。
- 松开时按原始 PDF 像素判断最小尺寸；过小选区丢弃并短暂提示“选区过小”。
- 新建选框立即成为当前选框，并在右侧列表高亮。

### 7.2 取消和清理

- `Esc` 只取消当前草稿，不影响已有选框。
- `pointercancel`、blur、visibility hidden 和 unmount 必须清理 pointer capture、自动滚动、自绘光标和草稿。
- 取消后不得保存空 segment。

### 7.3 选中、编辑和锁定

- 单击已有选框只负责选中，不删除。
- 未提交选框显示八个手柄并允许缩放。
- 选框内部不可拖动。
- 已提交、处理中、已完成、失败和需人工复核选框全部锁定几何。
- 失败选框允许用同一张已生成截图重试，不重新裁剪。
- 需人工复核选框保留原任务和截图，只增加复核原因；可标记为“扫不到题”“题目区域不完整”“包含多道完整题目”或“其他异常”。
- 复核标记不会被任务轮询覆盖；清除标记后恢复标记前的任务状态。
- 已完成选框可从右侧列表打开对应任务；更多任务操作留待后续。
- 重叠区域无法直接点中下层框时，通过右侧列表选择。

### 7.4 视觉

- 选框内部透明。
- 默认边界为浅绿色细线。
- 八个手柄为深绿色分段线：四角是圆角 L 形，四边中点是短条。
- 左上角显示小型题号标记。
- 待提交、处理中、完成、失败、需人工复核有明确状态颜色。
- 处理中边框显示沿周长运动的跑马灯效果；系统开启 reduced motion 时停止动画。
- 跨页边界穿过页面接缝连续绘制，不显示两个独立框。

## 8. 工作区布局

```text
top workflow toolbar
  back | save state | delete selected | invert | submit pending

workspace
  left page rail (220px, collapsible, no thumbnails)
  center document viewport
    sticky PDF controls: zoom out | zoom value | zoom in | fit width | page / total
    continuous cropped page surface
  right selection rail (300px, collapsible)
```

### 8.1 顶部工具栏

只放批次级命令：

- 返回。
- 自动保存状态。
- 删除当前未提交选框。
- 反色预览。
- 提交全部待处理选框。
- 左右侧栏的展开按钮。

不放学科和备注。任务提交固定使用自动识别学科，不实现备注输入。

### 8.2 PDF 视图控制条

- 放大、缩小、缩放比例、适合宽度和页码位于页面组件上方，不放入左右侧栏或批次工具栏。
- 控制条在文档滚动时保持可见，并占用独立布局高度，不遮挡选框。
- 普通滚轮滚动文档。
- `Ctrl + 滚轮` 缩放，并以鼠标指针所在文档位置为缩放中心。
- 保留页码输入和总页数；移除上一页、下一页按钮。

### 8.3 侧栏

- 左侧栏只显示无缩略图的页面导航。
- 右侧栏按文档位置显示全部选框：题号、页范围、状态、失败原因和人工复核原因。
- 点击右侧条目滚动定位并选中选框。
- 未提交条目进入编辑态；已完成条目提供打开任务；失败条目提供重试。
- 已完成或失败的截图即使内容异常也先按一道题正常提交，再由右侧栏标记需人工复核；异常标记不删除任务或截图。
- 两侧栏可独立折叠，折叠后由顶部图标恢复。
- 桌面默认展开；宽度不足时先折叠左侧，再折叠右侧；窄屏使用抽屉。

## 9. 排序和题号

- 选框按文档位置排序，不按创建时间排序。
- 主排序键为选框顶部 document-space 坐标。
- 顶部相同时按左侧坐标排序。
- 未提交选框的题号随排序更新。
- 已提交题号锁定，避免任务编号变化。

## 10. Session、提交和删除语义

### 10.1 新 schema

```ts
type PersistedSelection = {
  id: string;
  parts: SelectionSlice[];
  question_no: number;
  status: SelectionModel["status"];
  review_reason?: "unreadable" | "incomplete" | "multiple_questions" | "other";
  review_previous_status?: SelectionModel["status"];
  review_resolved?: boolean;
  task_id?: string;
  problem_ids: string[];
  error?: string;
};

type BatchSession = {
  crop_rect: DocumentCropRect;
  crop_confirmed: boolean;
  segments: PersistedSelection[];
  // existing source/session fields
};
```

- 读取旧数据时，把 `rect + continuation` 转为 `parts[]`。
- 新数据保存 `parts[]`，Core/API 必须支持任意长度。
- 不再把旧 `continuation` 作为新交互事实。

### 10.2 自动保存

- 创建、缩放、删除选框后短暂防抖自动保存。
- 工具栏显示“已保存”“正在保存”“保存失败，正在重试”。
- 自动保存失败不阻止提交。
- 不提供手动保存按钮。

### 10.3 提交

- “提交全部”逐个处理待提交选框；某一道失败不阻止其他题目。
- 提交接口同时保存该选框的当前几何并创建任务。
- 只有选框保存和任务创建都成功，才标记该选框提交成功。
- 因而“提交成功”必须同时代表该选框已持久化。
- 成功后保存用于任务的裁剪截图并锁定选框。
- 截图文件名必须包含 session hash 和 segment id，禁止使用仅按题号命名的全局文件名。
- AI 通过 `finalize_task` 或 `fail_task` 的独立 `review_reason` 参数上报输入异常；轮询把它映射为 `needs_review`。多题图片只保存第一道完整题目，不能创建数组或第二个任务。
- 人工清除异常后保存 `review_resolved=true`，后续轮询不得再次自动恢复同一异常。
- 失败项显示独立错误；已创建截图用于后续同图重试。

### 10.4 删除整次批量扫描

- 删除入口只在“最近文件”记录的菜单中，不放入当前工作区。
- 删除 batch session、其中选框和任务关联关系。
- 不删除已经生成的任务、题目或题目截图。
- 删除后再次导入相同 PDF 会创建新 session 并重新进入裁剪阶段。
- 题库/任务详情中的“定位到批量扫描”必须检查 session 是否存在。
- 目标失效时入口显示为灰色禁用，并说明原批量扫描记录已删除；不得删除题目或跳转到空页面。

## 11. 测试要求

### 11.1 几何单元测试

必须覆盖：

- 全页比例裁剪在不同源分辨率页面上的映射。
- 等宽显示、不同裁剪后高度的 document-top 累加。
- 页面接缝没有 gap。
- 单页、跨 2 页、3 页和最后一页切片。
- 从下向上和从上向下拖动。
- 八方向 resize 统一修改 document rect。
- 超界 clamp、零面积和反向矩形。
- 裁剪后坐标映射回原始 PDF 像素。
- 按顶部、再按左侧的稳定排序。

### 11.2 交互 E2E

必须覆盖：

- 在任意页画裁剪框。
- 检查页直接显示裁剪结果，被裁内容不显示。
- 确认前可调整，确认后不可调整。
- 裁剪完成后恢复 session 一致。
- 单列页面等宽并首尾无缝。
- 自动滚动向上、向下跨页创建一个选框。
- 跨 2 页和 3 页选框边界连续。
- 单击选中、不删除；八个手柄可调整；内部不可移动。
- 重叠选框可通过右栏定位。
- `Esc`、pointercancel、blur、visibility hidden 和卸载清理。
- 过小选区被丢弃并提示。
- 处理中跑马灯和 reduced motion。
- `Ctrl + 滚轮` 以鼠标文档位置缩放。
- 自动保存状态、失败重试且不阻止提交。
- 部分提交失败不阻止其他题目。
- 失败任务同图重试且几何锁定。
- 删除 session 不删除任务；失效定位按钮变灰。
- 左右侧栏折叠、窄屏抽屉和文字不溢出。

### 11.3 性能

- 10 页 PDF 首屏只渲染视口附近页面。
- 左侧栏不创建页面缩略图。
- 页面占位在 bitmap 完成前稳定存在。
- 滚动不触发全部页面解码。
- 选区更新不触发 PDF 重渲染。
- 导出只解码选区涉及页面。

## 12. 验收门槛

1. 不存在双页并排、左右翻页选择状态机或新的 `source + continuation` 核心状态。
2. 一次裁剪按比例作用于当前 PDF 全部页面，确认后不可修改。
3. 裁剪预览只显示裁剪结果，且可切换任意页检查。
4. 页面单列、等宽、无缝，跨页边界视觉和坐标连续。
5. 跨页选区是一个可八方向缩放的 `DocumentRect`。
6. 侧栏、缩放、滚动和懒加载不造成选区坐标漂移。
7. `parts[]` 支持任意页数并兼容读取旧 session。
8. 自动保存失败不阻止提交；提交成功同时证明选框已保存。
9. 删除 session 不删除任务、题目或截图，失效定位入口正确禁用。
10. Python、TypeScript、几何单测和对应 Playwright E2E 全部通过。

## 13. 实施顺序

### Phase A：schema 和纯几何

- 增加 `crop_rect`、`crop_confirmed` 和 `parts[]`。
- 添加旧 session 读取兼容。
- 完成页面、裁剪、切片和原图映射单测。

### Phase B：裁剪和连续页面带

- 实现任意页绘制、跨页检查和确认锁定。
- 实现稳定占位、按需渲染、等宽无缝页面带。
- 实现页码导航、缩放和 `Ctrl + 滚轮`。

### Phase C：选区覆盖层和侧栏

- 实现创建、自动滚动、连续跨页框和八个手柄。
- 实现左右侧栏、排序、定位、状态和跑马灯。

### Phase D：session 和任务集成

- 实现自动保存、提交即持久化、部分失败和同图重试。
- 实现 session 删除和失效任务定位。
- 移除旧 BatchSegmenter/双页路径。

### Phase E：回归和性能

- 完成几何、E2E、响应式和 10 页性能验收。
- 只有所有门槛通过后才替换现有批量扫描入口。
