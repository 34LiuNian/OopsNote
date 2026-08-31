"use client";

import { useState } from "react";
import { Box, Button, Heading, Text, Textarea } from "@/components/ui/primitives";
import { DesignSystemMatrix } from "@/components/ui/DesignSystemMatrix";
import { RenameDialog } from "@/components/ui/RenameDialog";
import { MarkdownRenderer } from "../../components/renderers/MarkdownRenderer";
import { ProblemContent } from "../../components/ProblemContent";
import { TaskProgressBar } from "../../components/task/TaskProgressBar";
import { useTaskProgress, ProgressStepKey } from "../../hooks/useTaskProgress";
import { confirmAction } from "@/lib/confirm";
import { notify } from "@/lib/notify";
import { isAdminUser } from "@/lib/auth";
import { useAuth } from "@/components/providers/AuthProvider";
import { SelectionDebugFixture } from "./SelectionDebugFixture";
import { AuthFixtures } from "@/components/auth/AuthFixtures";
import sxStyles from "./page.sx.module.css";

const DEFAULT_TEXT = [
  "# Debug 页面",
  "## 公式块",
  "$$\\frac{1}{2}mv^2 = mgh$$",
  "",
  "## GFM 表格",
  "| 分组 | 组中值 | 频数 |",
  "| --- | ---: | ---: |",
  "| $[4,5)$ | $4.5$ | $6$ |",
  "| $[5,6)$ | $5.5$ | $10$ |",
  "",
  "## LaTeX 表格（array 环境）",
  "$$\\begin{array}{|c|c|c|c|c|} \\hline & \\text{第一次} & \\text{第二次} & \\text{第三次} & \\text{第四次} \\\\ \\hline \\text{体积}/\\mathrm{mL} & 17.10 & 18.10 & 18.00 & 17.90 \\\\ \\hline \\end{array}$$",
  "",
  "## 化学方程式（mhchem）",
  "$$\\ce{2H2 + O2 -> 2H2O}$$",
  "",
  "## 代码块（mermaid）",
  "```mermaid",
  "flowchart LR",
  "  A[输入题图] --> B[OCR/重建]",
  "  B --> C[解题]",
  "  C --> D[打标]",
  "```",
  "",
  "## 分子结构（RDKit）",
  "```molecule",
  "C1=CC=CC=C1",
  "```",
  "",
  "## 图形（TikZJax）",
  "```tikz",
  "\\begin{tikzpicture}",
  "  \\draw[->] (0,0) -- (2,0) node[right] {$x$};",
  "  \\draw[->] (0,0) -- (0,2) node[above] {$y$};",
  "  \\draw[domain=0:1.35,smooth] plot (\\x,{\\x*\\x});",
  "\\end{tikzpicture}",
  "```",
  "",
  "## 普通代码块",
  "```text",
  "Answer: 5",
  "Reason: 3^2 + 4^2 = 5^2",
  "```",
].join("\n");

const STEP_KEYS: ProgressStepKey[] = ["queued", "ocr", "solving", "tagging"];

export default function DebugPage() {
  const { user, loading } = useAuth();
  if (!loading && !isAdminUser(user)) {
    return (
      <Box className={sxStyles.sx1}>
        <Text className={sxStyles.sx2}>Debug</Text>
        <Heading as="h2" className={sxStyles.sx3}>仅管理员可见</Heading>
        <Text className={sxStyles.sx4}>渲染调试与测试台只对管理员账号开放。</Text>
      </Box>
    );
  }

  return <DebugPageContent />;
}

function DebugPageContent() {
  // Markdown 相关状态
  const [text, setText] = useState(DEFAULT_TEXT);
  const [progressIndex, setProgressIndex] = useState<number>(-1);
  const [latestLine, setLatestLine] = useState<string>("");
  const [isFailed, setIsFailed] = useState(false);
  const [isRunning, setIsRunning] = useState(true);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("示例文件.pdf");

  const progressState = useTaskProgress({
    status: isFailed ? "failed" : isRunning ? "processing" : "completed",
    streamProgress: progressIndex >= 0 ? [STEP_KEYS[progressIndex]] : [],
  });

  const handleSetStep = (idx: number) => {
    setProgressIndex(idx);
    setLatestLine(`模拟进入 ${STEP_KEYS[idx]} 阶段`);
    setIsFailed(false);
    setIsRunning(true);
  };

  const handleSetFailed = () => {
    if (progressIndex >= 0) {
      setIsFailed(true);
      setIsRunning(false);
      setLatestLine("模拟处理失败");
    }
  };

  const handleReset = () => {
    setProgressIndex(-1);
    setLatestLine("");
    setIsFailed(false);
    setIsRunning(true);
  };

  const handleSetCompleted = () => {
    setProgressIndex(STEP_KEYS.length - 1);
    setLatestLine("任务完成");
    setIsFailed(false);
    setIsRunning(false);
  };

  return (
    <Box className={sxStyles.sx1}>
      <DesignSystemMatrix />
      <Box>
        <Text className={sxStyles.sx2}>Debug</Text>
        <Heading as="h2" className={sxStyles.sx3}>Debug 页面</Heading>
        <Text className={sxStyles.sx4}>
          在左侧编辑 Markdown，右侧实时预览渲染效果。
        </Text>
      </Box>

      {/* TaskProgressBar 测试区域 */}
      <Box className={sxStyles.sx5}>
        <Heading as="h3" className={sxStyles.sx6}>TaskProgressBar 组件测试</Heading>
        <Text className={sxStyles.sx7}>
          当前状态：isFailed={isFailed ? "true" : "false"}, isRunning={isRunning ? "true" : "false"}, progressIndex={progressIndex}
        </Text>
        <TaskProgressBar
          progressState={progressState}
          latestLine={latestLine}
          error={isFailed ? "模拟错误：处理失败" : undefined}
          statusMessage={isFailed ? "处理失败" : undefined}
        />
        <Box className={sxStyles.sx8}>
          <Button size="small" onClick={handleReset}>重置</Button>
          {STEP_KEYS.map((step, idx) => (
            <Button
              key={step}
              size="small"
              variant={progressIndex === idx ? "primary" : "default"}
              onClick={() => handleSetStep(idx)}
            >
              设置：{step}
            </Button>
          ))}
          <Button size="small" variant="danger" onClick={handleSetFailed}>
            模拟失败
          </Button>
          <Button size="small" variant="primary" onClick={handleSetCompleted}>
            完成
          </Button>
        </Box>
      </Box>

      <Box className={sxStyles.sx9}>
        <Heading as="h3" className={sxStyles.sx10}>通知与对话框测试</Heading>
        <Text className={sxStyles.sx11}>
          验证 Mantine 通知、危险操作确认和表单对话框的明暗主题表现。
        </Text>
        <Box className={sxStyles.sx12}>
          <Button size="small" variant="primary" onClick={() => notify.success({ title: "保存成功", description: "示例内容已保存。" })}>成功通知</Button>
          <Button size="small" onClick={() => notify.info({ title: "正在同步", description: "这是信息提示。" })}>信息通知</Button>
          <Button size="small" variant="danger" onClick={() => notify.error({ title: "操作失败", description: "这是错误提示。" })}>错误通知</Button>
          <Button size="small" onClick={() => confirmAction({
            title: "删除示例内容",
            message: "确认后会显示成功提示，不会删除实际数据。",
            confirmLabel: "删除",
            destructive: true,
            onConfirm: () => { notify.success({ title: "已确认删除", description: "这只是调试操作。" }); },
          })}>确认对话框</Button>
          <Button size="small" onClick={() => setRenameOpen(true)}>重命名对话框</Button>
        </Box>
        <RenameDialog
          opened={renameOpen}
          title="重命名示例文件"
          label="文件名"
          value={renameValue}
          onChange={setRenameValue}
          onCancel={() => setRenameOpen(false)}
          onConfirm={() => {
            setRenameOpen(false);
            notify.success({ title: "已重命名", description: renameValue.trim() });
          }}
        />
      </Box>

      <AuthFixtures />

      <SelectionDebugFixture />

      <Box className={sxStyles.sx13}>
        <Button size="small" onClick={() => setText(DEFAULT_TEXT)}>恢复默认示例</Button>
      </Box>

      <Box id="problem-illustration-fixtures" className={sxStyles.sx14}>
        <Box id="problem-illustration-auto" className={sxStyles.sx15}>
          <Heading as="h3" className={sxStyles.sx16}>TikZ/SVG 右侧自适应</Heading>
          <ProblemContent
            problemText={"已知函数 $f(x)=x^2$，观察右图并回答。\n图形默认位于右侧，默认字号与题目正文一致。"}
            contentFormat="oopsmark-v1"
            options={[{ key: "A", text: "$1$" }, { key: "B", text: "$2$" }, { key: "C", text: "$3$" }, { key: "D", text: "$4$" }]}
            diagramDetected
            diagramKind="tikz"
            diagramSvg={'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80"><rect id="theme-background" width="120" height="80" fill="#fff"/><path id="theme-axis" d="M10 70H110M20 75V5" fill="none" stroke="#000" stroke-width="3"/><path id="theme-series" d="M25 65Q55 60 100 15" fill="none" stroke="#0ea5e9" stroke-width="3"/><path id="theme-glyph" d="M50 40L60 40L55 50Z"/></svg>'}
            diagramCanvasWidthEm={12}
            diagramCanvasHeightEm={8}
          />
        </Box>
        <Box id="problem-illustration-custom" className={sxStyles.sx17}>
          <Heading as="h3" className={sxStyles.sx18}>题图左侧 125%</Heading>
          <ProblemContent
            problemText={"题图与 TikZ 二选一。\n这个样例使用手动大小。"}
            contentFormat="oopsmark-v1"
            diagramDetected
            diagramKind="image"
            diagramImagePath="/favicon.svg"
            diagramPlacement={{ kind: "side", side: "left" }}
            diagramScaleAdjustmentPercent={125}
          />
        </Box>
      </Box>

      <Box
        className={sxStyles.sx19}
      >
        <Box className={sxStyles.sx20}>
          <Heading as="h3" className={sxStyles.sx21}>输入</Heading>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={24}
            block
          />
        </Box>
        <Box className={sxStyles.sx22}>
          <Heading as="h3" className={sxStyles.sx23}>预览</Heading>
          <Box className={sxStyles.sx24}>
            <MarkdownRenderer text={text} format="oopsmark-v1" />
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
