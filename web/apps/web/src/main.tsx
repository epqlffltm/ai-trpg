// web/apps/web/src/main.tsx
// 화면의 입구. 화면 쪽 설정을 입히고, 읽기의 저장소(QueryClient)와 경로(데이터 라우터)를 걸고 앱을 그린다.
// 경로는 App 안의 <Routes> 가 정한다. 데이터 라우터로 감싸는 것은 떠나기 전에 묻는 것(useBlocker, #1344)을 쓰려고다.

import '@fontsource-variable/hanken-grotesk';
import '@ai-trpg/ui/styles.css';
import './app.css';
import './genres/genreThemes.css';
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { App } from './App';
import { createQueryClient } from './queryClient';
import { applySettings, getSettingsSnapshot } from './settings/settingsStore';

const root = document.getElementById('root');
if (!root) throw new Error('index.html 에 #root 가 없다');

// 화면 쪽 설정(밝기, 글자 크기)을 그리기 전에 입혀 깜빡이지 않게 한다
applySettings(getSettingsSnapshot().settings);

// 모든 주소를 App 하나에 넘긴다. App 의 <Routes> 가 나눈다
const router = createBrowserRouter([{ path: '*', element: <App /> }]);

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
