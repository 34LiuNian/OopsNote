'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { Box, Text } from '@/components/ui/primitives';
import { SidebarCollapseIcon, SidebarExpandIcon } from '@/components/ui/icons';
import { Sidebar } from './Sidebar';
import { MobileTabBar } from './MobileTabBar';
import { BackendStatus } from '../ui/BackendStatus';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <Box className="oops-app-shell">
      <Box as="header" className="oops-titlebar">
        <Box sx={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
          <button
            className="oops-titlebar__sidebar-toggle"
            type="button"
            onClick={() => setSidebarCollapsed((value) => !value)}
            aria-label={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
            aria-controls="oops-primary-sidebar"
            aria-expanded={!sidebarCollapsed}
            title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
          >
            {sidebarCollapsed ? <SidebarExpandIcon size={17} /> : <SidebarCollapseIcon size={17} />}
          </button>
          <Text className="oops-titlebar__mobile-brand">OopsNote</Text>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <BackendStatus />
        </Box>
      </Box>

      <Box className="oops-app-body">
        <Sidebar collapsed={sidebarCollapsed} />
        <Box className="oops-content-surface">
          <Box as="main" sx={{ px: [3, 4, 5], py: [3, 4], flex: 1, width: '100%', pb: ['80px', 4] }}>
            <div key={pathname} className="oops-page-enter">
              {children}
            </div>
          </Box>
        </Box>
      </Box>
      <MobileTabBar />
    </Box>
  );
}
