// web/apps/web/src/main.tsx
// 화면의 입구. 화면 쪽 설정을 입히고, 읽기의 저장소(QueryClient)와 경로(BrowserRouter)를 걸고 앱을 그린다.

import '@ai-trpg/ui/styles.css';
import './app.css';
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { App } from './App';
import { createQueryClient } from './queryClient';
import { applySettings, getSettingsSnapshot } from './settings/settingsStore';

const root = document.getElementById('root');
if (!root) throw new Error('index.html 에 #root 가 없다');

// 화면 쪽 설정(밝기, 글자 크기)을 그리기 전에 입혀 깜빡이지 않게 한다
applySettings(getSettingsSnapshot().settings);

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
