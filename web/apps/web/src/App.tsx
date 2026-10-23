// web/apps/web/src/App.tsx
// 경로와 화면을 잇는다. 서비스마다 /trpg, /chat, /story 아래에 둔다(앱은 하나, docs/product/screens.md 의 "프런트 구조").
// 처음 들어오는 화면(첫 화면, 로그인, 가입, 비밀번호)은 바로 가져오고, 나머지는 처음 갈 때 받는다(routing/pages.ts).

import { Route, Routes } from 'react-router';
import { RequireSession } from './auth/RequireSession';
import { AppLayout } from './layout/AppLayout';
import { HomePage } from './pages/home/HomePage';
import { LoginPage } from './pages/login/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ForgotPasswordPage } from './pages/password/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/password/ResetPasswordPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { SignupPage } from './pages/signup/SignupPage';
import {
  ChargePage,
  LobbyPage,
  MyPage,
  OrderPage,
  OrdersPage,
  RulebookEditPage,
  RulebookNewPage,
  RulebooksPage,
  ScenarioBrowsePage,
  ScenarioPage,
  TableCreatePage,
  TableRoomPage,
  WalletPage,
} from './routing/pages';

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="signup" element={<SignupPage />} />
        <Route path="password/forgot" element={<ForgotPasswordPage />} />
        {/* 인증 서버의 PASSWORD_RESET_URL 이 가리키는 곳. 바꾸면 그 설정도 바꾼다 */}
        <Route path="reset-password" element={<ResetPasswordPage />} />
        <Route
          path="me"
          element={
            <RequireSession>
              <MyPage />
            </RequireSession>
          }
        />
        <Route
          path="wallet"
          element={
            <RequireSession>
              <WalletPage />
            </RequireSession>
          }
        />
        <Route
          path="wallet/charge"
          element={
            <RequireSession>
              <ChargePage />
            </RequireSession>
          }
        />
        <Route
          path="wallet/orders"
          element={
            <RequireSession>
              <OrdersPage />
            </RequireSession>
          }
        />
        <Route
          path="wallet/orders/:orderId"
          element={
            <RequireSession>
              <OrderPage />
            </RequireSession>
          }
        />
        <Route path="trpg">
          <Route index element={<ScenarioBrowsePage />} />
          <Route path="scenarios/:scenarioId" element={<ScenarioPage />} />
          <Route
            path="lobby"
            element={
              <RequireSession>
                <LobbyPage />
              </RequireSession>
            }
          />
          <Route
            path="tables/new"
            element={
              <RequireSession>
                <TableCreatePage />
              </RequireSession>
            }
          />
          <Route
            path="tables/:tableId"
            element={
              <RequireSession>
                <TableRoomPage />
              </RequireSession>
            }
          />
          {/* 제작 도구(B9). 지금은 룰북뿐이다. 모두 만든 사람 자신의 것이다 */}
          <Route
            path="studio/rulebooks"
            element={
              <RequireSession>
                <RulebooksPage />
              </RequireSession>
            }
          />
          <Route
            path="studio/rulebooks/new"
            element={
              <RequireSession>
                <RulebookNewPage />
              </RequireSession>
            }
          />
          <Route
            path="studio/rulebooks/:rulebookId"
            element={
              <RequireSession>
                <RulebookEditPage />
              </RequireSession>
            }
          />
          <Route path="*" element={<PlaceholderPage service="TRPG" />} />
        </Route>
        <Route path="chat/*" element={<PlaceholderPage service="chat" />} />
        <Route path="story/*" element={<PlaceholderPage service="story" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
