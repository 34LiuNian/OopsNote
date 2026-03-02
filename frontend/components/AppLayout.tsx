'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { Box } from '@primer/react';
import { Sidebar } from './Sidebar';
import { BackendStatus } from './BackendStatus';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

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
             justifyContent: 'flex-end',
             alignItems: 'center',
             position: 'sticky',
             top: 0,
             zIndex: 20,
             height: 50,
           }}
         >
            <BackendStatus />
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
