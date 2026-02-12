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
  const eventSourceRef = useRef<EventSource | null>(null);
  const streamBufferRef = useRef<string>("");
  const streamFlushTimerRef = useRef<number | null>(null);
  const hasLoadedStreamRef = useRef<boolean>(false);

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

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const es = new EventSource(`${API_BASE}/tasks/${taskId}/events`);
    eventSourceRef.current = es;

    es.addEventListener("progress", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data as string) as {
          status?: string;
          stage?: string | null;
          message?: string | null;
        };
        const message = payload.message || payload.stage || payload.status || "处理中";
        onStatusMessage?.(message);
        setProgressLines((prev) => {
          if (prev.length > 0 && prev[prev.length - 1] === message) return prev;
          return [...prev, message];
        });
      } catch {
        // ignore
      }
    });

    es.addEventListener("llm_delta", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data as string) as { delta?: string };
        if (!payload.delta) return;
        streamBufferRef.current += payload.delta;
        if (!streamFlushTimerRef.current) {
          streamFlushTimerRef.current = window.setTimeout(() => {
            streamFlushTimerRef.current = null;
            flushStreamBuffer();
          }, 80);
        }
      } catch {
        // ignore
      }
    });

    es.addEventListener("llm_snapshot", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data as string) as { text?: string };
        const text = payload.text || "";
        streamBufferRef.current = "";
        setStreamText(text);
        hasLoadedStreamRef.current = true;
      } catch {
        // ignore
      }
    });

    es.addEventListener("done", async () => {
      try {
        es.close();
      } catch {
        // ignore
      }
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
      flushStreamBuffer();
      await onDone?.();
    });

    es.addEventListener("error", () => {
      try {
        es.close();
      } catch {
        // ignore
      }
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
      onStatusMessage?.("进度流断开，可点击“查看最新状态”刷新。");
      flushStreamBuffer();
    });

    return () => {
      try {
        es.close();
      } catch {
        // ignore
      }
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
      if (streamFlushTimerRef.current) {
        window.clearTimeout(streamFlushTimerRef.current);
        streamFlushTimerRef.current = null;
      }
    };
  }, [taskId, status, flushStreamBuffer, onStatusMessage, onDone]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
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
