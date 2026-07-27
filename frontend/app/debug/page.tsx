"use client";

import { useState } from "react";
import { Box, Button, Heading, Text, Textarea } from "@/components/ui/primitives";
import { MarkdownRenderer } from "../../components/renderers/MarkdownRenderer";
import { ProblemContent } from "../../components/ProblemContent";
import { TaskProgressBar } from "../../components/task/TaskProgressBar";
import { useTaskProgress, ProgressStepKey } from "../../hooks/useTaskProgress";

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
  // Markdown 相关状态
  const [text, setText] = useState(DEFAULT_TEXT);
  const [progressIndex, setProgressIndex] = useState<number>(-1);
  const [latestLine, setLatestLine] = useState<string>("");
  const [isFailed, setIsFailed] = useState(false);
  const [isRunning, setIsRunning] = useState(true);

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
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box>
        <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Debug</Text>
        <Heading as="h2" sx={{ fontSize: 3 }}>Debug 页面</Heading>
        <Text sx={{ color: "fg.muted", mt: 1 }}>
          在左侧编辑 Markdown，右侧实时预览渲染效果。
        </Text>
      </Box>

      {/* TaskProgressBar 测试区域 */}
      <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
        <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>TaskProgressBar 组件测试</Heading>
        <Text sx={{ fontSize: 0, color: "fg.muted", mb: 2 }}>
          当前状态：isFailed={isFailed ? "true" : "false"}, isRunning={isRunning ? "true" : "false"}, progressIndex={progressIndex}
        </Text>
        <TaskProgressBar
          progressState={progressState}
          latestLine={latestLine}
          error={isFailed ? "模拟错误：处理失败" : undefined}
          statusMessage={isFailed ? "处理失败" : undefined}
        />
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mt: 2 }}>
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

      <Box sx={{ display: "flex", gap: 2 }}>
        <Button size="small" onClick={() => setText(DEFAULT_TEXT)}>恢复默认示例</Button>
      </Box>

      <Box id="problem-illustration-fixtures" sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
        <Box id="problem-illustration-auto" sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
          <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>TikZ/SVG 右侧自适应</Heading>
          <ProblemContent
            problemText={"已知函数 $f(x)=x^2$，观察右图并回答。\n图形默认位于右侧，高度与完整作答内容栏一致。"}
            contentFormat="oopsmark-v1"
            options={[{ key: "A", text: "$1$" }, { key: "B", text: "$2$" }, { key: "C", text: "$3$" }, { key: "D", text: "$4$" }]}
            diagramDetected
            diagramKind="tikz"
            diagramSvg={'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80"><rect id="theme-background" width="120" height="80" fill="#fff"/><path id="theme-axis" d="M10 70H110M20 75V5" fill="none" stroke="#000" stroke-width="3"/><path id="theme-series" d="M25 65Q55 60 100 15" fill="none" stroke="#0ea5e9" stroke-width="3"/></svg>'}
          />
        </Box>
        <Box id="problem-illustration-custom" sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
          <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>题图左侧 125%</Heading>
          <ProblemContent
            problemText={"题图与 TikZ 二选一。\n这个样例使用手动大小。"}
            contentFormat="oopsmark-v1"
            diagramDetected
            diagramKind="image"
            diagramImagePath="/favicon.svg"
            diagramPosition="left"
            diagramScalePercent={125}
          />
        </Box>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: ["1fr", "1fr 1fr"],
          gap: 3,
          alignItems: "stretch",
        }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Heading as="h3" sx={{ fontSize: 2 }}>输入</Heading>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={24}
            block
          />
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Heading as="h3" sx={{ fontSize: 2 }}>预览</Heading>
          <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
            <MarkdownRenderer text={text} format="oopsmark-v1" />
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
