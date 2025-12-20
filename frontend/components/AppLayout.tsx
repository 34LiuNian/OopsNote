'use client';

import { Box, Text } from '@primer/react';
import { Sidebar } from './Sidebar';
import { BackendStatus } from './BackendStatus';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: ['column', 'row'], minHeight: '100vh', bg: 'canvas.default' }}>
      <Sidebar />
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Box 
           as="header" 
           sx={{ 
             py: 3, 
             px: 4, 
             borderBottom: '1px solid', 
             borderColor: 'border.default',
             display: 'flex',
             justifyContent: 'flex-end',
             alignItems: 'center',
             bg: 'canvas.default'
           }}
         >
            <BackendStatus />
         </Box>
         <Box as="main" sx={{ p: 4, flex: 1 }}>
            {children}
         </Box>
      </Box>
    </Box>
  );
}
