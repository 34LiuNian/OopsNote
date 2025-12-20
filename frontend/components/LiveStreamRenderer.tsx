"use client";

import { useEffect, useMemo, useState } from "react";
import { Box, Text, ButtonGroup, Button } from "@primer/react";
import { CodeIcon, EyeIcon } from "@primer/octicons-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkBreaks from "remark-breaks";
import rehypeKatex from "rehype-katex";

function useThrottledValue<T>(value: T, delayMs: number): T {
  const [throttled, setThrottled] = useState(value);

  useEffect(() => {
    if (delayMs <= 0) {
      setThrottled(value);
      return;
    }

    const handle = setTimeout(() => setThrottled(value), delayMs);
    return () => clearTimeout(handle);
  }, [value, delayMs]);

  return throttled;
}

// 简单的 JSON 字段提取与格式化
function extractAndFormat(jsonStr: string): string {
  if (!jsonStr) return "";

  // 1. 尝试完整解析
  try {
    const obj = JSON.parse(jsonStr);
    return formatObject(obj);
  } catch (e) {
    // 解析失败，尝试修复末尾并解析（简单的修复：尝试添加 "}"）
    // 但流式数据可能断在任何地方，修复比较困难。
    // 转为正则提取。
  }

  // 2. 正则提取关键字段
  // 针对流式未闭合的情况，我们尝试匹配 "key": "value...
  const keys = [
    { key: "problem_text", label: "题目" },
    { key: "answer", label: "答案" },
    { key: "explanation", label: "解析" },
    { key: "analysis", label: "分析" },
    { key: "thought", label: "思考" },
    { key: "stage_message", label: "阶段信息" }
  ];

  let output = "";
  let foundAny = false;

  for (const { key, label } of keys) {
    // 匹配 "key": "value..."，支持转义引号，允许末尾没有引号（未闭合）
    // 注意：这个正则假设 value 是字符串。如果 value 是对象/数组，这个正则会失效。
    // 对于 options 数组，我们需要单独处理，或者忽略。
    const regex = new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)(?:"|$)`);
    const match = jsonStr.match(regex);
    if (match) {
      foundAny = true;
      // 处理转义字符：把 \" 变回 "，\n 变回换行
      let content = match[1];
      try {
        // JSON.parse(`"${content}"`) 可以处理转义，但如果 content 不完整（末尾有半个转义），会报错
        // 简单处理：
        content = content.replace(/\\"/g, '"').replace(/\\n/g, '\n').replace(/\\\\/g, '\\');
      } catch (e) {}
      
      output += `**${label}**:\n${content}\n\n`;
    }
  }

  // 如果看起来不像 JSON（不以 { 开头），或者没提取到任何已知字段，直接返回原文本
  if (!foundAny && !jsonStr.trim().startsWith("{")) {
    return jsonStr;
  }

  return output || "(正在解析流式内容...)";
}

function formatObject(obj: any): string {
  let res = "";
  const fieldMap: Record<string, string> = {
    problem_text: "题目",
    answer: "答案",
    explanation: "解析",
    analysis: "分析",
    thought: "思考",
    stage_message: "阶段信息"
  };

  // 优先顺序
  const order = ["stage_message", "problem_text", "options", "answer", "explanation", "analysis", "thought"];
  
  order.forEach(key => {
    if (obj[key]) {
      if (key === "options" && Array.isArray(obj.options)) {
        res += `**选项**:\n`;
        obj.options.forEach((o: any) => {
            const k = o.key || o.label || "";
            const t = o.text || o.value || "";
            res += `- ${k}. ${t}\n`;
        });
        res += "\n";
      } else if (typeof obj[key] === 'string') {
        res += `**${fieldMap[key] || key}**:\n${obj[key]}\n\n`;
      }
    }
  });

  return res;
}

export function LiveStreamRenderer({ text }: { text: string }) {
  const [mode, setMode] = useState<'raw' | 'preview'>('preview');

  // Preview 渲染节流：避免每个 token 都触发一次完整 Markdown/KaTeX 渲染导致闪动。
  const throttledText = useThrottledValue(text, mode === 'preview' ? 80 : 0);

  const formattedText = useMemo(() => {
    if (mode === 'raw') return text;
    return extractAndFormat(throttledText);
  }, [text, throttledText, mode]);

  return (
    <Box sx={{ p: 2, bg: 'canvas.subtle', borderRadius: 2, mb: 3, display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Text sx={{ fontWeight: 'bold' }}>实时输出</Text>
        <ButtonGroup>
          <Button 
            size="small" 
            variant={mode === 'raw' ? 'primary' : 'default'} 
            onClick={() => setMode('raw')}
            leadingVisual={CodeIcon}
          >
            Raw JSON
          </Button>
          <Button 
            size="small" 
            variant={mode === 'preview' ? 'primary' : 'default'} 
            onClick={() => setMode('preview')}
            leadingVisual={EyeIcon}
          >
            Preview
          </Button>
        </ButtonGroup>
      </Box>

      <Box 
        sx={{ 
          maxHeight: 400, 
          overflowY: 'auto', 
          bg: 'canvas.default', 
          p: 2, 
          borderRadius: 1, 
          border: '1px solid', 
          borderColor: 'border.default' 
        }}
      >
        {mode === 'raw' ? (
          <Box as="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'mono', fontSize: 1, m: 0 }}>
            {text}
          </Box>
        ) : (
          <Box sx={{ fontSize: 1, '& .katex': { fontSize: '1.1em' } }}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
              rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
              components={{
                p: ({ children }) => <Box as="p" sx={{ m: 0, mb: 2, whiteSpace: 'pre-wrap' }}>{children}</Box>,
                ul: ({ children }) => <Box as="ul" sx={{ pl: 3, mt: 0, mb: 2 }}>{children}</Box>,
                ol: ({ children }) => <Box as="ol" sx={{ pl: 3, mt: 0, mb: 2 }}>{children}</Box>,
                li: ({ children }) => <Box as="li" sx={{ mb: 1, whiteSpace: 'pre-wrap' }}>{children}</Box>,
                pre: ({ children }) => (
                  <Box
                    as="pre"
                    sx={{
                      whiteSpace: 'pre-wrap',
                      fontFamily: 'mono',
                      fontSize: 1,
                      m: 0,
                      mb: 2,
                      p: 2,
                      borderRadius: 1,
                      border: '1px solid',
                      borderColor: 'border.default',
                      bg: 'canvas.subtle',
                      overflowX: 'auto',
                    }}
                  >
                    {children}
                  </Box>
                ),
                code: ({ children }) => (
                  <Box as="code" sx={{ fontFamily: 'mono', fontSize: 1 }}>
                    {children}
                  </Box>
                ),
              }}
            >
              {formattedText}
            </ReactMarkdown>
          </Box>
        )}
      </Box>
    </Box>
  );
}
