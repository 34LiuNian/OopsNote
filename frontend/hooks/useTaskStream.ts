"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJson } from "../lib/api";

type UseTaskStreamParams = {
  taskId: string;
  status?: string | null;
  onStatusMessage?: (message: string) => void;
  onDone?: () => Promise<void> | void;
};

type UseTaskStreamState = {
  streamText: string;
  progressLines: string[];
  loadStreamOnce: () => Promise<void>;
  resetStream: () => void;
};

export function useTaskStream({ taskId, status, onStatusMessage, onDone }: UseTaskStreamParams): UseTaskStreamState {
  const [streamText, setStreamText] = useState("");
  const [progressLines, setProgressLines] = useState<string[]>([]);
  const streamBufferRef = useRef<string>("");
  const streamFlushTimerRef = useRef<number | null>(null);
  const hasLoadedStreamRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const flushStreamBuffer = useCallback(() => {
    if (!streamBufferRef.current) return;
    const chunk = streamBufferRef.current;
    streamBufferRef.current = "";
    setStreamText((prev) => {
      const next = prev + chunk;
      const MAX_CHARS = 200_000;
      return next.length > MAX_CHARS ? next.slice(next.length - MAX_CHARS) : next;
    });
  }, []);

  const loadStreamOnce = useCallback(async () => {
    try {
      const payload = await fetchJson<{ task_id: string; text?: string }>(
        `/tasks/${taskId}/stream?max_chars=200000`
      );
      const text = payload.text || "";
      streamBufferRef.current = "";
      setStreamText(text);
      hasLoadedStreamRef.current = true;
    } catch {
      // ignore: stream history is best-effort
    }
  }, [taskId]);

  const resetStream = useCallback(() => {
    streamBufferRef.current = "";
    setStreamText("");
    setProgressLines([]);
    hasLoadedStreamRef.current = false;
  }, []);

  useEffect(() => {
    if (!taskId) return;
    const shouldConnectSse = status === "pending" || status === "processing" || !hasLoadedStreamRef.current;
    if (!shouldConnectSse) return;

    // 清理之前的连接
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // Use /api proxy to avoid CORS issues
    const API_BASE = "/api";
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const connectSSE = async () => {
      console.log('[useTaskStream] connecting to SSE for task:', taskId);
      try {
        // SSE requests should be simple GET requests without custom headers
        // to avoid CORS preflight. The Accept header is optional for SSE.
        const response = await fetch(`${API_BASE}/tasks/${taskId}/events`, {
          method: "GET",
          signal: abortController.signal,
        });
        
        console.log('[useTaskStream] SSE response status:', response.status);
        
        if (!response.ok) {
          throw new Error(`SSE 连接失败：${response.status}`);
        }
        
        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("ReadableStream 不可用");
        }
        
        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "";
        
        const readStream = async () => {
          try {
            console.log('[useTaskStream] start reading stream');
            while (true) {
              const { done, value } = await reader.read();
              if (done) {
                console.log('[useTaskStream] stream done');
                break;
              }
              
              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split("\n");
              buffer = lines.pop() || "";
              
              for (const line of lines) {
                const trimmedLine = line.trim();
                
                // 跳过空行
                if (!trimmedLine) continue;
                
                console.log('[useTaskStream] raw line:', trimmedLine);
                
                // 解析 event 行
                if (trimmedLine.startsWith("event:")) {
                  currentEvent = trimmedLine.slice(6).trim();
                  console.log('[useTaskStream] event:', currentEvent);
                  continue;
                }
                
                // 解析 data 行
                if (trimmedLine.startsWith("data:")) {
                  const data = trimmedLine.slice(5).trim();
                  console.log('[useTaskStream] data:', data);
                  
                  if (currentEvent === "progress") {
                    try {
                      // 后端 SSE 发送的格式：data: {"stage": "...", "message": "..."}
                      // 直接解析为 payload 对象
                      const payload = JSON.parse(data) as {
                        status?: string;
                        stage?: string | null;
                        message?: string | null;
                      };
                      const message = payload.message || payload.stage || payload.status || "处理中";
                      console.log('[useTaskStream] progress event:', payload, 'message:', message);
                      onStatusMessage?.(message);
                      setProgressLines((prev) => {
                        if (prev.length > 0 && prev[prev.length - 1] === message) return prev;
                        return [...prev, message];
                      });
                    } catch (e) {
                      console.error('[useTaskStream] failed to parse progress event:', data, e);
                      // ignore parse errors
                    }
                  } else if (currentEvent === "llm_delta") {
                    try {
                      const payload = JSON.parse(data) as { delta?: string };
                      if (!payload.delta) continue;
                      streamBufferRef.current += payload.delta;
                      if (!streamFlushTimerRef.current) {
                        streamFlushTimerRef.current = window.setTimeout(() => {
                          streamFlushTimerRef.current = null;
                          flushStreamBuffer();
                        }, 80);
                      }
                    } catch {
                      // ignore parse errors
                    }
                  } else if (currentEvent === "llm_snapshot") {
                    try {
                      const payload = JSON.parse(data) as { text?: string };
                      const text = payload.text || "";
                      streamBufferRef.current = "";
                      setStreamText(text);
                      hasLoadedStreamRef.current = true;
                    } catch {
                      // ignore parse errors
                    }
                  } else if (currentEvent === "done") {
                    await onDone?.();
                  }
                  
                  // 重置 event
                  currentEvent = "";
                }
              }
            }
          } catch (error) {
            if (error instanceof Error && error.name !== "AbortError") {
              onStatusMessage?.('进度流断开，可点击"查看最新状态"刷新。');
            }
          } finally {
            reader.releaseLock();
            flushStreamBuffer();
          }
        };
        
        readStream();
      } catch (error) {
        if (error instanceof Error && error.name !== "AbortError") {
          onStatusMessage?.("无法连接到进度流：" + (error.message || "未知错误"));
        }
      }
    };
    
    connectSSE();
    
    // 清理函数
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (streamFlushTimerRef.current) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
    };
  }, [taskId, status, flushStreamBuffer, onStatusMessage, onDone]);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (streamFlushTimerRef.current) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
    };
  }, []);

  return {
    streamText,
    progressLines,
    loadStreamOnce,
    resetStream,
  };
}
