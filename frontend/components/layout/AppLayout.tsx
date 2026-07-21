'use client';

import { usePathname } from 'next/navigation';
import { Box, Text } from '@/components/ui/primitives';
import { Sidebar } from './Sidebar';
import { MobileTabBar } from './MobileTabBar';
import { BackendStatus } from '../ui/BackendStatus';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
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
