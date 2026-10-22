// web/apps/web/src/main.tsx
// 화면의 입구. 읽기의 저장소(QueryClient)와 경로(BrowserRouter)를 걸고 앱을 그린다.

import '@ai-trpg/ui/styles.css';
import './app.css';
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { App } from './App';
import { createQueryClient } from './queryClient';

const root = document.getElementById('root');
if (!root) throw new Error('index.html 에 #root 가 없다');

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
