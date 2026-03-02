'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Box, Button, Text } from '@primer/react';
import { Sidebar } from './Sidebar';
import { BackendStatus } from './BackendStatus';
import { clearAuthSession, getCurrentUser, onAuthChanged } from '../features/auth/store';

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

    const adminRoute = pathname.startsWith('/settings') || pathname.startsWith('/tags') || pathname.startsWith('/debug');
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
    router.replace('/login');
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
            <Text sx={{ color: 'fg.muted', fontSize: 1 }}>当前用户：{username}</Text>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <BackendStatus />
              <Button size="small" onClick={handleLogout}>退出登录</Button>
            </Box>
         </Box>
         <Box as="main" sx={{ px: [3, 4, 5], py: 4, flex: 1, width: '100%' }}>
            <div key={pathname} className="oops-page-enter">
              {children}
            </div>
         </Box>
      </Box>
    </Box>
  );
}
