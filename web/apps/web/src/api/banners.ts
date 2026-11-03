// web/apps/web/src/api/banners.ts
// 첫 화면의 홍보 배너(#994). 시나리오의 배너는 게임 서버, 캐릭터와 세계관의 배너는 asset 서버가 가진다.
// 서버마다 따로 부르고 화면이 잇는다(#593). 보는 주소는 로그인하지 않아도 부른다(전체이용가만 온다).
// 운영자의 주소(/admin/banners)는 운영자가 아니면 404 다.

import { apiRequest } from './http';
import type { components as Asset } from './generated/asset';
import type { components as Trpg } from './generated/trpg';

export type ScenarioBanner = Trpg['schemas']['PublicBanner'];
export type AssetBanner = Asset['schemas']['PublicBanner'];
export type ScenarioBannerAdmin = Trpg['schemas']['BannerOut'];
export type AssetBannerAdmin = Asset['schemas']['BannerOut'];
export type ScenarioBannerCreate = Trpg['schemas']['BannerCreate'];
export type AssetBannerCreate = Asset['schemas']['BannerCreate'];

const GAME = '/api/v1/game';
const ASSET = '/api/v1/asset';

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

/** 지금 걸린 시나리오의 배너. 차례대로다 */
export async function fetchScenarioBanners(signal?: AbortSignal): Promise<ScenarioBanner[]> {
  const body = await apiRequest<Trpg['schemas']['PublicBannerList']>(`${GAME}/banners`, withSignal(signal));
  return body.items;
}

/** 지금 걸린 캐릭터와 세계관의 배너. 차례대로다 */
export async function fetchAssetBanners(signal?: AbortSignal): Promise<AssetBanner[]> {
  const body = await apiRequest<Asset['schemas']['PublicBannerList']>(`${ASSET}/banners`, withSignal(signal));
  return body.items;
}

/** 운영자: 시나리오의 배너 전부(지난 것까지) */
export function fetchScenarioBannersForOperator(signal?: AbortSignal): Promise<ScenarioBannerAdmin[]> {
  return apiRequest<ScenarioBannerAdmin[]>(`${GAME}/admin/banners`, withSignal(signal));
}

/** 운영자: 캐릭터와 세계관의 배너 전부(지난 것까지) */
export function fetchAssetBannersForOperator(signal?: AbortSignal): Promise<AssetBannerAdmin[]> {
  return apiRequest<AssetBannerAdmin[]>(`${ASSET}/admin/banners`, withSignal(signal));
}

/** 운영자: 시나리오의 배너를 건다. 공개 중이 아니면 409 not_published */
export function createScenarioBanner(body: ScenarioBannerCreate): Promise<ScenarioBannerAdmin> {
  return apiRequest<ScenarioBannerAdmin>(`${GAME}/admin/banners`, { method: 'POST', body });
}

/** 운영자: 캐릭터나 세계관의 배너를 건다. 공개 목록에 나오지 않으면 409 not_published */
export function createAssetBanner(body: AssetBannerCreate): Promise<AssetBannerAdmin> {
  return apiRequest<AssetBannerAdmin>(`${ASSET}/admin/banners`, { method: 'POST', body });
}

/** 운영자: 배너를 내린다. server 는 그 배너를 가진 서버다 */
export async function deleteBanner(server: 'game' | 'asset', bannerId: string): Promise<void> {
  const prefix = server === 'game' ? GAME : ASSET;
  await apiRequest<unknown>(`${prefix}/admin/banners/${encodeURIComponent(bannerId)}`, { method: 'DELETE' });
}
