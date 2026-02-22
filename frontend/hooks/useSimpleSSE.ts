"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type UseSimpleSSEResult = {
  isConnected: boolean;
  events: Array<{ event: string; data: any; timestamp: number }>;
  connect: (taskId: string) => Promise<void>;
  disconnect: () => void;
  clearEvents: () => void;
};

/**
 * Simple SSE hook - direct connection without complex state management
 */
export function useSimpleSSE(): UseSimpleSSEResult {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<Array<{ event: string; data: any; timestamp: number }>>([]);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const disconnect = useCallback(() => {
    console.log('[useSimpleSSE] Disconnecting...');
    
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    setIsConnected(false);
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  const connect = useCallback((taskId: string) => {
    if (!taskId) {
      console.error('[useSimpleSSE] No task ID provided');
      return;
    }

    console.log('[useSimpleSSE] Connecting to SSE for task:', taskId);
    
    // Disconnect any existing connection
    disconnect();

    try {
      // Use EventSource API - designed specifically for SSE
      // Use direct backend connection in development, proxy in production
      const isDev = process.env.NODE_ENV === 'development';
      const baseUrl = isDev ? 'http://localhost:8000' : '/api';
      const eventSource = new EventSource(`${baseUrl}/tasks/${taskId}/events`);
      console.log('[useSimpleSSE] Using', isDev ? 'direct' : 'proxy', 'connection');
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log('[useSimpleSSE] ✅ Connection opened');
        setIsConnected(true);
      };

      eventSource.onmessage = (event) => {
        console.log('[useSimpleSSE] 📩 Received message:', event.data);
        try {
          const data = JSON.parse(event.data);
          setEvents(prev => [
            ...prev,
            {
              event: 'message',
              data,
              timestamp: Date.now(),
            },
          ]);
        } catch (e) {
          console.error('[useSimpleSSE] Failed to parse message:', e);
        }
      };

      eventSource.addEventListener('progress', (event) => {
        console.log('[useSimpleSSE] 📩 Received progress event:', event.data);
        try {
          const data = JSON.parse(event.data);
          setEvents(prev => [
            ...prev,
            {
              event: 'progress',
              data,
              timestamp: Date.now(),
            },
          ]);
        } catch (e) {
          console.error('[useSimpleSSE] Failed to parse progress:', e);
        }
      });

      eventSource.addEventListener('done', (event) => {
        console.log('[useSimpleSSE] 🏁 Received done event:', event.data);
        try {
          const data = JSON.parse(event.data);
          setEvents(prev => [
            ...prev,
            {
              event: 'done',
              data,
              timestamp: Date.now(),
            },
          ]);
        } catch (e) {
          console.error('[useSimpleSSE] Failed to parse done:', e);
        }
      });

      eventSource.onerror = (error) => {
        console.error('[useSimpleSSE] ❌ SSE Error:', error);
        setIsConnected(false);
        eventSource.close();
        eventSourceRef.current = null;
      };

    } catch (error) {
      console.error('[useSimpleSSE] ❌ Failed to create EventSource:', error);
      setIsConnected(false);
    }
  }, [disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    events,
    connect,
    disconnect,
    clearEvents,
  };
}
