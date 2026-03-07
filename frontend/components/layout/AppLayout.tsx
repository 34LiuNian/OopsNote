'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Box, Button, Text } from '@primer/react';
import { PersonIcon } from '@primer/octicons-react';
import { Sidebar } from './Sidebar';
import { MobileTabBar } from './MobileTabBar';
import { BackendStatus } from '../ui/BackendStatus';
import { clearAuthSession, getCurrentUser, onAuthChanged } from '../../features/auth/store';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [username, setUsername] = useState('');

  useEffect(() => {
    const isLoginRoute = pathname.startsWith('/login');
    if (isLoginRoute) {
      setReady(true);
      return;
    }

    const user = getCurrentUser();
    if (!user) {
      const next = encodeURIComponent(pathname || '/');
      router.replace(`/login?next=${next}`);
      return;
    }

    const adminRoute = pathname.startsWith('/settings') || pathname.startsWith('/tags') || pathname.startsWith('/debug') || pathname.startsWith('/users');
    if (adminRoute && user.role !== 'admin') {
      router.replace('/');
      return;
    }

    setUsername(user.username);
    setReady(true);
  }, [pathname, router]);

  useEffect(() => {
    return onAuthChanged(() => {
      const user = getCurrentUser();
      setUsername(user?.username ?? '');
    });
  }, []);

  useEffect(() => {
    // Use double-rAF + requestIdleCallback to ensure content has actually painted
    // before signaling the splash screen to dismiss.
    let cancelled = false;

    function signalReady() {
      if (cancelled) return;
      if (typeof (window as any).__markOopsSplashAppReady === 'function') {
        (window as any).__markOopsSplashAppReady();
      }
    }

    // Double-rAF ensures at least one full frame has been painted.
    const rafId = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if ('requestIdleCallback' in window) {
          (window as any).requestIdleCallback(signalReady, { timeout: 3000 });
        } else {
          setTimeout(signalReady, 200);
        }
      });
    });

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(rafId);
    };
  }, []);

  if (!ready) {
    return null;
  }

  if (pathname.startsWith('/login')) {
    return <>{children}</>;
  }

  const handleLogout = () => {
    clearAuthSession();
    // 使用硬跳转（非 SPA 路由），确保 React 树完全卸载，
    // 释放任务列表、LLM 流式数据等大对象占用的 JS 堆内存。
    window.location.href = '/login';
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: ['column', 'row'], minHeight: '100vh', bg: 'canvas.default' }}>
      <Sidebar />
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Box 
           as="header" 
           className="oops-glass"
           sx={{ 
             py: 2, 
             px: 4, 
             bg: 'canvas.overlay',
             borderBottom: '1px solid', 
             borderColor: 'border.muted',
             display: 'flex',
             justifyContent: 'space-between',
             alignItems: 'center',
             position: 'sticky',
             top: 0,
             zIndex: 20,
             height: 50,
           }}
         >
            <Box sx={{ display: ['flex', 'none'], alignItems: 'center', gap: 2, color: 'fg.default' }}>
              <Text sx={{ fontWeight: 'bold', fontSize: 3, fontFamily: "'OopsNoteFont', 'Inter', 'HarmonyOS Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>OopsNote</Text>
            </Box>
            <Box sx={{ display: ['none', 'flex'] }} />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <BackendStatus />
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'fg.muted' }}>
                <PersonIcon size={14} />
                <Text sx={{ fontSize: 1 }}>{username}</Text>
              </Box>
              <Button size="small" onClick={handleLogout}>退出登录</Button>
            </Box>
         </Box>
         <Box as="main" sx={{ px: [3, 4, 5], py: [3, 4], flex: 1, width: '100%', pb: ['80px', 4] }}>
            <div key={pathname} className="oops-page-enter">
              {children}
            </div>
         </Box>
      </Box>
      <MobileTabBar />
    </Box>
  );
}
