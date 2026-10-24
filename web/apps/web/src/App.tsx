// web/apps/web/src/App.tsx
// 경로와 화면을 잇는다. 서비스마다 /trpg, /chat, /story 아래에 둔다(앱은 하나, docs/product/screens.md 의 "프런트 구조").
// 처음 들어오는 화면(첫 화면, 로그인, 가입, 비밀번호)은 바로 가져오고, 나머지는 처음 갈 때 받는다(routing/pages.ts).

import { Outlet, Route, Routes } from 'react-router';
import { RequireOperator } from './auth/RequireOperator';
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
  AttendancePage,
  BestiariesPage,
  BestiaryEditPage,
  BestiaryNewPage,
  CharacterEditPage,
  CharacterNewPage,
  CharactersPage,
  ChargePage,
  ChatLorebookEditPage,
  ChatLorebookNewPage,
  ChatLorebooksPage,
  GuardianConsentPage,
  GuardianRequestPage,
  GuardianRevokePage,
  IdentityPage,
  LobbyPage,
  LorebookEditPage,
  LorebookNewPage,
  LorebooksPage,
  MessageReportPage,
  MyPage,
  NotificationsPage,
  OrderPage,
  OrdersPage,
  ReportsPage,
  RulebookEditPage,
  RulebookNewPage,
  RulebooksPage,
  ScenarioBrowsePage,
  ScenarioEditPage,
  ScenarioNewPage,
  ScenarioPage,
  ScenariosPage,
  StudioPage,
  TableCreatePage,
  TableRoomPage,
  WalletPage,
  WorldEditPage,
  WorldNewPage,
  WorldsPage,
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
          path="me/identity"
          element={
            <RequireSession>
              <IdentityPage />
            </RequireSession>
          }
        />
        <Route
          path="me/guardian"
          element={
            <RequireSession>
              <GuardianRequestPage />
            </RequireSession>
          }
        />
        {/* 인증 서버의 GUARDIAN_CONSENT_URL, GUARDIAN_REVOKE_URL 이 가리키는 곳. 보호자는 로그인하지 않는다. 바꾸면 그 설정도 바꾼다 */}
        <Route path="guardian/consent" element={<GuardianConsentPage />} />
        <Route path="guardian/revoke" element={<GuardianRevokePage />} />
        <Route
          path="notifications"
          element={
            <RequireSession>
              <NotificationsPage />
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
          path="wallet/attendance"
          element={
            <RequireSession>
              <AttendancePage />
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
          {/* 제작 도구(B9). 모두 만든 사람 자신의 것이라 묶음째 로그인해야 열린다 */}
          <Route
            path="studio"
            element={
              <RequireSession>
                <Outlet />
              </RequireSession>
            }
          >
            <Route index element={<StudioPage />} />
            <Route path="rulebooks" element={<RulebooksPage />} />
            <Route path="rulebooks/new" element={<RulebookNewPage />} />
            <Route path="rulebooks/:rulebookId" element={<RulebookEditPage />} />
            <Route path="worlds" element={<WorldsPage />} />
            <Route path="worlds/new" element={<WorldNewPage />} />
            <Route path="worlds/:worldId" element={<WorldEditPage />} />
            <Route path="lorebooks" element={<LorebooksPage />} />
            <Route path="lorebooks/new" element={<LorebookNewPage />} />
            <Route path="lorebooks/:lorebookId" element={<LorebookEditPage />} />
            <Route path="bestiaries" element={<BestiariesPage />} />
            <Route path="bestiaries/new" element={<BestiaryNewPage />} />
            <Route path="bestiaries/:bestiaryId" element={<BestiaryEditPage />} />
            <Route path="scenarios" element={<ScenariosPage />} />
            <Route path="scenarios/new" element={<ScenarioNewPage />} />
            <Route path="scenarios/:scenarioId" element={<ScenarioEditPage />} />
          </Route>
          <Route path="*" element={<PlaceholderPage service="TRPG" />} />
        </Route>
        {/* 운영자의 화면(E). 운영자가 아니면 없는 화면이다. /admin/ 은 프록시가 막으므로(인증 서버의 관리 화면) 쓰지 않는다 */}
        <Route
          path="operator"
          element={
            <RequireSession>
              <RequireOperator>
                <Outlet />
              </RequireOperator>
            </RequireSession>
          }
        >
          <Route path="reports" element={<ReportsPage />} />
          <Route path="reports/messages/:reportId" element={<MessageReportPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="chat">
          {/* 캐릭터 만들기(C6). 모두 만든 사람 자신의 것이라 묶음째 로그인해야 열린다 */}
          <Route
            path="studio/characters"
            element={
              <RequireSession>
                <Outlet />
              </RequireSession>
            }
          >
            <Route index element={<CharactersPage />} />
            <Route path="new" element={<CharacterNewPage />} />
            <Route path=":characterId" element={<CharacterEditPage />} />
          </Route>
          {/* chat 의 로어북. 캐릭터의 로어북 탭이 붙인다. 모두 만든 사람 자신의 것이다 */}
          <Route
            path="studio/lorebooks"
            element={
              <RequireSession>
                <Outlet />
              </RequireSession>
            }
          >
            <Route index element={<ChatLorebooksPage />} />
            <Route path="new" element={<ChatLorebookNewPage />} />
            <Route path=":lorebookId" element={<ChatLorebookEditPage />} />
          </Route>
          <Route index element={<PlaceholderPage service="chat" />} />
          <Route path="*" element={<PlaceholderPage service="chat" />} />
        </Route>
        <Route path="story/*" element={<PlaceholderPage service="story" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
