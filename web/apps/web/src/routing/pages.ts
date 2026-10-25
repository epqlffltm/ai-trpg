// web/apps/web/src/routing/pages.ts
// 처음 갈 때 받는 화면들(코드 분할, 2026-10-23). 경로는 App.tsx 가 잇는다.
//
// 나눈 것: TRPG(둘러보기, 시나리오, 로비, 테이블 만들기, 테이블 방, 제작 도구), chat 의 캐릭터 만들기, 지갑·충전·주문, 마이페이지,
// 본인인증과 보호자 동의(보호자의 링크가 여는 화면도), 알림, 공지·게시판,
// 운영자의 신고 처리.
// 화면마다 조각 하나다.
// 나누지 않은 것: 첫 화면, 로그인, 가입, 비밀번호, 없는 주소. 처음 들어오는 곳이라 한 번 더 받게 하지 않는다(App.tsx 가 바로 가져온다).
// 라이브러리(React, React Router, TanStack Query)는 vite.config.ts 가 따로 묶는다.

import { lazyPage } from './lazyPage';

export const MyPage = lazyPage(() => import('../pages/me/MyPage'), 'MyPage');

export const GalleryPage = lazyPage(() => import('../pages/gallery/GalleryPage'), 'GalleryPage');
export const SettingsPage = lazyPage(() => import('../pages/settings/SettingsPage'), 'SettingsPage');
export const WalletPage = lazyPage(() => import('../pages/wallet/WalletPage'), 'WalletPage');
export const ChargePage = lazyPage(() => import('../pages/charge/ChargePage'), 'ChargePage');
export const AttendancePage = lazyPage(() => import('../pages/attendance/AttendancePage'), 'AttendancePage');
export const IdentityPage = lazyPage(() => import('../pages/identity/IdentityPage'), 'IdentityPage');
export const GuardianRequestPage = lazyPage(() => import('../pages/guardian/GuardianRequestPage'), 'GuardianRequestPage');
export const GuardianConsentPage = lazyPage(() => import('../pages/guardian/GuardianConsentPage'), 'GuardianConsentPage');
export const GuardianRevokePage = lazyPage(() => import('../pages/guardian/GuardianRevokePage'), 'GuardianRevokePage');
export const NotificationsPage = lazyPage(() => import('../pages/notifications/NotificationsPage'), 'NotificationsPage');
export const BoardIndexPage = lazyPage(() => import('../pages/board/BoardIndexPage'), 'BoardIndexPage');
export const BoardListPage = lazyPage(() => import('../pages/board/BoardListPage'), 'BoardListPage');
export const BoardSearchPage = lazyPage(() => import('../pages/board/BoardSearchPage'), 'BoardSearchPage');
export const PostPage = lazyPage(() => import('../pages/board/PostPage'), 'PostPage');
export const OrdersPage = lazyPage(() => import('../pages/orders/OrdersPage'), 'OrdersPage');
export const OrderPage = lazyPage(() => import('../pages/orders/OrderPage'), 'OrderPage');

export const ScenarioBrowsePage = lazyPage(() => import('../pages/trpg/browse/ScenarioBrowsePage'), 'ScenarioBrowsePage');
export const ScenarioPage = lazyPage(() => import('../pages/trpg/scenario/ScenarioPage'), 'ScenarioPage');
export const LobbyPage = lazyPage(() => import('../pages/trpg/lobby/LobbyPage'), 'LobbyPage');
export const TableCreatePage = lazyPage(() => import('../pages/trpg/tables/TableCreatePage'), 'TableCreatePage');
export const PastTablesPage = lazyPage(() => import('../pages/trpg/past/PastTablesPage'), 'PastTablesPage');
export const PastTablePage = lazyPage(() => import('../pages/trpg/past/PastTablePage'), 'PastTablePage');
export const TableRoomPage = lazyPage(() => import('../pages/trpg/room/TableRoomPage'), 'TableRoomPage');

// 제작 도구(B9). 만들기(허브)와 재료마다의 목록, 만들기, 고치기
export const StudioPage = lazyPage(() => import('../pages/trpg/studio/StudioPage'), 'StudioPage');
export const RulebooksPage = lazyPage(() => import('../pages/trpg/studio/rulebooks/RulebooksPage'), 'RulebooksPage');
export const RulebookNewPage = lazyPage(() => import('../pages/trpg/studio/rulebooks/RulebookNewPage'), 'RulebookNewPage');
export const RulebookEditPage = lazyPage(() => import('../pages/trpg/studio/rulebooks/RulebookEditPage'), 'RulebookEditPage');
export const WorldsPage = lazyPage(() => import('../pages/trpg/studio/worlds/WorldsPage'), 'WorldsPage');
export const WorldNewPage = lazyPage(() => import('../pages/trpg/studio/worlds/WorldNewPage'), 'WorldNewPage');
export const WorldEditPage = lazyPage(() => import('../pages/trpg/studio/worlds/WorldEditPage'), 'WorldEditPage');
export const LorebooksPage = lazyPage(() => import('../pages/trpg/studio/lorebooks/LorebooksPage'), 'LorebooksPage');
export const LorebookNewPage = lazyPage(() => import('../pages/trpg/studio/lorebooks/LorebookNewPage'), 'LorebookNewPage');
export const LorebookEditPage = lazyPage(() => import('../pages/trpg/studio/lorebooks/LorebookEditPage'), 'LorebookEditPage');
export const BestiariesPage = lazyPage(() => import('../pages/trpg/studio/bestiaries/BestiariesPage'), 'BestiariesPage');
export const BestiaryNewPage = lazyPage(() => import('../pages/trpg/studio/bestiaries/BestiaryNewPage'), 'BestiaryNewPage');
export const BestiaryEditPage = lazyPage(() => import('../pages/trpg/studio/bestiaries/BestiaryEditPage'), 'BestiaryEditPage');
export const ScenariosPage = lazyPage(() => import('../pages/trpg/studio/scenarios/ScenariosPage'), 'ScenariosPage');
export const ScenarioNewPage = lazyPage(() => import('../pages/trpg/studio/scenarios/ScenarioNewPage'), 'ScenarioNewPage');
export const ScenarioEditPage = lazyPage(() => import('../pages/trpg/studio/scenarios/ScenarioEditPage'), 'ScenarioEditPage');

// 운영자의 신고 처리(E4). 운영자만 가는 곳이라 사용자의 첫 묶음에 넣지 않는다
export const ReportsPage = lazyPage(() => import('../pages/operator/ReportsPage'), 'ReportsPage');
export const MessageReportPage = lazyPage(() => import('../pages/operator/MessageReportPage'), 'MessageReportPage');

// chat 의 캐릭터 만들기(C6). 목록, 만들기, 고치기
export const CharactersPage = lazyPage(() => import('../pages/chat/studio/characters/CharactersPage'), 'CharactersPage');
export const CharacterNewPage = lazyPage(() => import('../pages/chat/studio/characters/CharacterNewPage'), 'CharacterNewPage');
export const CharacterEditPage = lazyPage(() => import('../pages/chat/studio/characters/CharacterEditPage'), 'CharacterEditPage');

// chat 의 로어북(캐릭터가 붙이는 설정의 모음). TRPG 의 로어북(LorebooksPage)과 다른 것이라 이름 앞에 Chat 을 붙인다
export const ChatLorebooksPage = lazyPage(() => import('../pages/chat/studio/lorebooks/ChatLorebooksPage'), 'ChatLorebooksPage');
export const ChatLorebookNewPage = lazyPage(() => import('../pages/chat/studio/lorebooks/ChatLorebookNewPage'), 'ChatLorebookNewPage');
export const ChatLorebookEditPage = lazyPage(() => import('../pages/chat/studio/lorebooks/ChatLorebookEditPage'), 'ChatLorebookEditPage');
