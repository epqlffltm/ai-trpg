// web/apps/web/src/pages/operator/bannerForm.ts
// 운영자의 배너 걸기(#994)의 입력과 보일 모양. 화면을 그리지 않는 순수한 함수다.
// 서버의 규칙(trpg-server, asset-server 의 app/banners/schemas.py)과 같다: 차례 0~999, 끝은 시작보다 뒤.
// 시나리오는 게임 서버, 캐릭터와 세계관은 asset 서버에 건다.

import { ApiError } from '../../api/errors';
import type { AssetBannerAdmin, AssetBannerCreate, ScenarioBannerAdmin, ScenarioBannerCreate } from '../../api/banners';
import { commonProblem, fieldProblem, unknownProblem, type FormProblem } from '../../auth/problem';

export const BANNER_MAX_POSITION = 999;

export type BannerTarget = 'scenario' | 'character' | 'world';

export const TARGET_LABELS: Record<BannerTarget, string> = { scenario: 'TRPG 시나리오', character: 'chat 캐릭터', world: 'story 세계관' };

export type BannerDraft = {
  target: BannerTarget;
  targetId: string;
  position: string;
  /** datetime-local 의 값(이 기기의 시각). 비우면 지금부터 */
  startsAt: string;
  /** 비우면 내릴 때까지 */
  endsAt: string;
};

export const EMPTY_BANNER: BannerDraft = { target: 'scenario', targetId: '', position: '0', startsAt: '', endsAt: '' };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** 칸마다 고칠 것. 아직 쓰지 않은 작품 ID 는 말하지 않는다 */
export function bannerHints(draft: BannerDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  if (draft.targetId.trim() && !UUID.test(draft.targetId.trim())) hints.targetId = '작품의 ID(소개 화면 주소의 마지막 부분)를 적어 주세요.';
  const position = Number(draft.position);
  if (!Number.isInteger(position) || position < 0 || position > BANNER_MAX_POSITION) hints.position = `0~${BANNER_MAX_POSITION} 사이의 정수입니다.`;
  if (draft.startsAt && draft.endsAt && new Date(draft.endsAt) <= new Date(draft.startsAt)) hints.endsAt = '끝은 시작보다 뒤여야 합니다.';
  return hints;
}

export function canHang(draft: BannerDraft): boolean {
  return draft.targetId.trim() !== '' && Object.keys(bannerHints(draft)).length === 0;
}

/** 보낼 시각. 이 기기의 시각을 UTC 로 바꾼다. 비우면 보내지 않는다 */
function toInstant(local: string): { value: string } | null {
  return local ? { value: new Date(local).toISOString() } : null;
}

function period(draft: BannerDraft): { starts_at?: string; ends_at?: string } {
  const starts = toInstant(draft.startsAt);
  const ends = toInstant(draft.endsAt);
  return { ...(starts ? { starts_at: starts.value } : {}), ...(ends ? { ends_at: ends.value } : {}) };
}

export function toScenarioBody(draft: BannerDraft): ScenarioBannerCreate {
  return { scenario_id: draft.targetId.trim(), position: Number(draft.position), ...period(draft) };
}

export function toAssetBody(draft: BannerDraft): AssetBannerCreate {
  const kind = draft.target === 'world' ? 'world' : 'character';
  return { kind, target_id: draft.targetId.trim(), position: Number(draft.position), ...period(draft) };
}

/** 목록의 한 줄. 두 서버의 배너를 같은 모양으로 */
export type BannerRow = {
  id: string;
  server: 'game' | 'asset';
  target: BannerTarget;
  name: string;
  position: number;
  startsAt: string;
  endsAt: string | null;
  shown: boolean;
};

export function scenarioRow(banner: ScenarioBannerAdmin): BannerRow {
  return { id: banner.id, server: 'game', target: 'scenario', name: banner.title, position: banner.position, startsAt: banner.starts_at, endsAt: banner.ends_at ?? null, shown: banner.shown };
}

export function assetRow(banner: AssetBannerAdmin): BannerRow {
  return { id: banner.id, server: 'asset', target: banner.kind, name: banner.name, position: banner.position, startsAt: banner.starts_at, endsAt: banner.ends_at ?? null, shown: banner.shown };
}

const FAILED = '배너를 걸지 못했습니다. 잠시 뒤에 다시 시도하세요.';

/** 걸기의 실패. 409 는 공개 목록에 나오지 않는 작품이다 */
export function describeBannerProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 409) return { message: '공개 목록에 나오는 작품만 걸 수 있습니다. 작품의 종류와 ID, 공개 여부를 확인해 주세요.' };
  if (error.status === 404) return { message: '운영자만 배너를 걸 수 있습니다.' };
  if (error.status === 422) return fieldProblem(error, '기간이나 차례를 확인해 주세요. 끝은 지금보다 뒤여야 합니다.');
  return unknownProblem(error, FAILED);
}
