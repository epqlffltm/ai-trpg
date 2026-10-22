// web/apps/web/src/App.tsx
// 경로와 화면을 잇는다. 서비스마다 /trpg, /chat, /story 아래에 둔다(앱은 하나, docs/product/screens.md 의 "프런트 구조").

import { Route, Routes } from 'react-router';
import { AppLayout } from './layout/AppLayout';
import { HomePage } from './pages/home/HomePage';
import { LoginPage } from './pages/login/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PlaceholderPage } from './pages/PlaceholderPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="trpg/*" element={<PlaceholderPage service="TRPG" />} />
        <Route path="chat/*" element={<PlaceholderPage service="chat" />} />
        <Route path="story/*" element={<PlaceholderPage service="story" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
