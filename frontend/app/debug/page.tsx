"use client";

import { useCallback, useEffect, useState } from "react";
import { Box, Button, Heading, Text, Textarea, TextInput } from "@primer/react";
import { MarkdownRenderer } from "../../components/MarkdownRenderer";
import { TaskProgressBar } from "../../components/task/TaskProgressBar";
import { useTaskProgress, ProgressStepKey } from "../../hooks/useTaskProgress";
import { useSimpleSSE } from "../../hooks/useSimpleSSE";
import { API_BASE } from "../../lib/api";

const DEFAULT_TEXT = [
  "# Debug 页面",
  "",
  "这是一段普通文本，包含 **加粗**、*斜体*，以及行内公式 $a^2 + b^2 = c^2$。",
  "",
  "## 题干",
  "给定直角三角形，已知 $a=3, b=4$，求 $c$。",
  "",
  "## 选项",
  "- A. 5",
  "- B. 6",
  "- C. 7",
  "- D. 8",
  "",
  "## 公式块",
  "$$\\frac{1}{2}mv^2 = mgh$$",
  "",
  "## LaTeX 表格（array 环境）",
  "$$\\begin{array}{|c|c|c|c|c|} \\hline & \\text{第一次} & \\text{第二次} & \\text{第三次} & \\text{第四次} \\\\ \\hline \\text{体积}/\\mathrm{mL} & 17.10 & 18.10 & 18.00 & 17.90 \\\\ \\hline \\end{array}$$",
  "",
  "## Chemfig（Backend）",
  "```chemfig",
  "[,0.7]*6(-=(*5(-N(-H)-=(-[:30]CH_2CH_2NHCOCH_3)--))-=-(-H_3CO)=)",
  "```",
  "",
  "```chemfig",
  "[,0.7]*6(-=(*5(-[0.7]N(-H)-=(-[:30,0.7](-[:330,0.7](-[:30,0.7]N(-[2,0.7]H)(-[:330,0.7](=[6,0.7]O)(-[:30,0.7]())))))--))-=-(-[,0.7]O(-[1,0.7]))=)",
  "```",
  "",
  "## 代码块（mermaid）",
  "```mermaid",
  "flowchart LN",
  "  A[输入题图] --> B[OCR/重建]",
  "  B --> C[解题]",
  "  C --> D[打标]",
  "```",
  "",
  "## 代码块（smiles）",
  "```smiles",
  "C1=CC=CC=C1",
  "```",
  "",
  "## 普通代码块",
  "```text",
  "Answer: 5",
  "Reason: 3^2 + 4^2 = 5^2",
  "```",
  "",
  "## 解析",
  "因为 $3^2 + 4^2 = 9 + 16 = 25$，所以 $c=5$。",
].join("\n");

const STEP_KEYS: ProgressStepKey[] = ["queued", "ocr", "solving", "tagging"];

export default function DebugPage() {
  // Markdown 相关状态
  const [text, setText] = useState(DEFAULT_TEXT);
  const [chemfigStatus, setChemfigStatus] = useState<string>("未检测");
  const [chemfigLoading, setChemfigLoading] = useState(false);
  const [progressIndex, setProgressIndex] = useState<number>(-1);
  const [latestLine, setLatestLine] = useState<string>("");
  const [isFailed, setIsFailed] = useState(false);
  const [isRunning, setIsRunning] = useState(true);

  // SSE 测试相关状态
  const [sseTaskId, setSseTaskId] = useState<string>("");
  const [sseStatus, setSseStatus] = useState<string>("");
  const [sseProgressLines, setSseProgressLines] = useState<string[]>([]);
  const { isConnected, events, connect, disconnect, clearEvents } = useSimpleSSE();

  const sseProgressState = useTaskProgress({
    status: isConnected ? "processing" : "pending",
    streamProgress: sseProgressLines,
    statusMessage: sseStatus,
  });

  // 处理 SSE 事件
  useEffect(() => {
    if (events.length === 0) return;
    const lastEvent = events[events.length - 1];
    if (lastEvent.event === 'progress') {
      const message = lastEvent.data.message || lastEvent.data.stage || '处理中';
      setSseStatus(message);
      setSseProgressLines((prev) => {
        if (prev.length > 0 && prev[prev.length - 1] === message) return prev;
        return [...prev, message];
      });
    } else if (lastEvent.event === 'done') {
      setSseStatus('任务完成');
    }
  }, [events]);

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

  // SSE 测试函数
  const handleSseCreateTask = async () => {
    try {
      setSseStatus("创建任务中...");
      const response = await fetch(`${API_BASE}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
          action: "single"
        })
      });
      if (!response.ok) throw new Error("创建任务失败");
      const data = await response.json();
      setSseTaskId(data.task_id);
      setSseStatus(`任务已创建：${data.task_id}`);
    } catch (error) {
      setSseStatus(`错误：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const handleSseConnect = () => {
    if (!sseTaskId) {
      setSseStatus("请先创建或输入任务 ID");
      return;
    }
    clearEvents();
    connect(`http://localhost:8000/tasks/${sseTaskId}/events`);
    setSseStatus("SSE 已连接");
  };

  const handleSseSimulate = async () => {
    if (!sseTaskId) {
      setSseStatus("请先创建或输入任务 ID");
      return;
    }
    try {
      setSseStatus("触发模拟处理...");
      const response = await fetch(`${API_BASE}/tasks/${sseTaskId}/simulate`, {
        method: "POST"
      });
      if (!response.ok) throw new Error("模拟处理失败");
      setSseStatus("模拟处理已触发");
    } catch (error) {
      setSseStatus(`错误：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const handleSseReset = () => {
    disconnect();
    setSseTaskId("");
    setSseStatus("已重置");
    clearEvents();
  };

  const handleSseOneClick = async () => {
    await handleSseCreateTask();
    setTimeout(() => {
      handleSseConnect();
      setTimeout(() => {
        handleSseSimulate();
      }, 500);
    }, 500);
  };

  const handleCheckChemfig = async () => {
    setChemfigLoading(true);
    setChemfigStatus("检测中...");
    try {
      const response = await fetch(`${API_BASE}/latex/chemfig`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          content: "\\chemfig{H-O-H}",
          inline: true,
        }),
      });
      if (response.ok) {
        setChemfigStatus(`可访问 (${response.status})`);
      } else {
        setChemfigStatus(`不可访问 (${response.status})`);
      }
    } catch (error) {
      setChemfigStatus(error instanceof Error ? `错误: ${error.message}` : "错误: 请求失败");
    } finally {
      setChemfigLoading(false);
    }
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

      {/* SSE 测试区域 */}
      <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
        <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>SSE 测试</Heading>
        <Box sx={{ display: "flex", gap: 2, mb: 3, flexWrap: "wrap" }}>
          <Button size="small" onClick={handleSseOneClick} disabled={isConnected || !!sseTaskId} variant="primary">
            一键测试
          </Button>
          <Button size="small" onClick={handleSseCreateTask} disabled={isConnected || !!sseTaskId}>
            创建任务
          </Button>
          <Button size="small" onClick={handleSseConnect} disabled={isConnected || !sseTaskId}>
            连接 SSE
          </Button>
          <Button size="small" onClick={handleSseSimulate} disabled={!sseTaskId || isConnected}>
            模拟处理
          </Button>
          <Button size="small" onClick={handleSseReset} disabled={isConnected || !sseTaskId} variant="danger">
            重置
          </Button>
        </Box>

        <Box sx={{ mb: 2 }}>
          <Text sx={{ fontSize: 0, fontWeight: "bold" }}>任务 ID:</Text>
          <TextInput
            value={sseTaskId}
            onChange={(e) => setSseTaskId(e.target.value)}
            sx={{ fontSize: 0, fontFamily: "mono", ml: 2 }}
            width={300}
          />
        </Box>

        <Box sx={{ mb: 2 }}>
          <Text sx={{ fontSize: 0, fontWeight: "bold" }}>连接:</Text>
          <Text sx={{ fontSize: 0, ml: 2, color: isConnected ? "success.fg" : "danger.fg" }}>
            {isConnected ? "已连接" : "未连接"}
          </Text>
        </Box>

        <Box sx={{ mb: 2 }}>
          <Text sx={{ fontSize: 0, fontWeight: "bold" }}>状态:</Text>
          <Text sx={{ fontSize: 0, ml: 2 }}>{sseStatus || "无"}</Text>
        </Box>

        <Box sx={{ p: 2, border: "1px solid", borderColor: "border.default", borderRadius: 2, bg: "canvas.subtle" }}>
          <Heading as="h4" sx={{ fontSize: 1, mb: 2 }}>事件日志 ({events.length})</Heading>
          <Box sx={{ maxHeight: 200, overflowY: "auto", fontFamily: "mono", fontSize: 0 }}>
            {events.length === 0 ? (
              <Text sx={{ color: "fg.muted" }}>暂无事件</Text>
            ) : (
              events.map((event, i) => (
                <Box key={i} sx={{ mb: 1, pb: 1, borderBottom: "1px solid", borderColor: "border.muted" }}>
                  <Text sx={{ color: "accent.fg", fontWeight: "bold" }}>
                    [{new Date(event.timestamp).toLocaleTimeString()}] {event.event}
                  </Text>
                  <Box sx={{ whiteSpace: "pre-wrap", ml: 2 }}>
                    {JSON.stringify(event.data, null, 2)}
                  </Box>
                </Box>
              ))
            )}
          </Box>
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
            <MarkdownRenderer text={text} />
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
