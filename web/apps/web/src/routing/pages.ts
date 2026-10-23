// web/apps/web/src/routing/pages.ts
// 처음 갈 때 받는 화면들(코드 분할, 2026-10-23). 경로는 App.tsx 가 잇는다.
//
// 나눈 것: TRPG(둘러보기, 시나리오, 로비, 테이블 만들기, 테이블 방, 제작 도구), 지갑·충전·주문, 마이페이지. 화면마다 조각 하나다.
// 나누지 않은 것: 첫 화면, 로그인, 가입, 비밀번호, 없는 주소. 처음 들어오는 곳이라 한 번 더 받게 하지 않는다(App.tsx 가 바로 가져온다).
// 라이브러리(React, React Router, TanStack Query)는 vite.config.ts 가 따로 묶는다.

import { lazyPage } from './lazyPage';

export const MyPage = lazyPage(() => import('../pages/me/MyPage'), 'MyPage');

export const WalletPage = lazyPage(() => import('../pages/wallet/WalletPage'), 'WalletPage');
export const ChargePage = lazyPage(() => import('../pages/charge/ChargePage'), 'ChargePage');
export const OrdersPage = lazyPage(() => import('../pages/orders/OrdersPage'), 'OrdersPage');
export const OrderPage = lazyPage(() => import('../pages/orders/OrderPage'), 'OrderPage');

export const ScenarioBrowsePage = lazyPage(() => import('../pages/trpg/browse/ScenarioBrowsePage'), 'ScenarioBrowsePage');
export const ScenarioPage = lazyPage(() => import('../pages/trpg/scenario/ScenarioPage'), 'ScenarioPage');
export const LobbyPage = lazyPage(() => import('../pages/trpg/lobby/LobbyPage'), 'LobbyPage');
export const TableCreatePage = lazyPage(() => import('../pages/trpg/tables/TableCreatePage'), 'TableCreatePage');
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
