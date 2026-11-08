// web/apps/web/src/pages/me/works/myWorksView.ts
// 마이페이지 제작자 탭의 내 작품(Stitch 10번)을 보이기 전의 순수한 함수. 작품의 공개 상태와 칩으로 거르기, 정렬의 고를 거리, 쓰인 수와 관심 수의 글.
// 공개 상태는 asset 서버가 주는 값(공개 범위, 공개한 판, 운영자의 숨김)으로 정한다. TRPG 시나리오는 이 값이 없어 칩을 달지 않는다.

import type { MineOrder, MyScenarioSummary } from '../../../api/types';

/** 공개 상태. 숨김이 먼저고, 공개한 판이 없으면 초안이다 */
export type WorkStatus = 'hidden' | 'draft' | 'public' | 'unlisted' | 'private';

export type StatusSource = { visibility: 'private' | 'public' | 'unlisted'; latest_version: number | null; hidden_at?: string | null };

const LABELS: Record<WorkStatus, string> = {
  hidden: '숨겨짐',
  draft: '초안',
  public: '공개 중',
  unlisted: '링크 공개',
  private: '비공개',
};

/** 거르는 칩. 아무것도 고르지 않으면 전체다(설계서의 "전체, 초안, 공개 중, 링크 공개, 숨겨짐") */
export const STATUS_CHIPS: { value: WorkStatus; label: string }[] = (['draft', 'public', 'unlisted', 'hidden'] as const).map((value) => ({
  value,
  label: LABELS[value],
}));

export function workStatus(work: StatusSource): WorkStatus {
  if (work.hidden_at) return 'hidden';
  if (work.latest_version === null) return 'draft';
  if (work.visibility === 'public') return 'public';
  if (work.visibility === 'unlisted') return 'unlisted';
  return 'private';
}

export function statusLabel(status: WorkStatus): string {
  return LABELS[status];
}

/** 고른 칩의 것만. 고르지 않았으면 모두 */
export function filterByStatus<T extends StatusSource>(works: T[], status: WorkStatus | undefined): T[] {
  return status ? works.filter((work) => workStatus(work) === status) : works;
}

/** 정렬(#1165). 차례는 서버가 정한다(쓰인 수가 같으면 최근에 고친 것부터) */
export const SORT_OPTIONS: { value: MineOrder; label: string }[] = [
  { value: 'updated', label: '최근 고친 순' },
  { value: 'started', label: '쓰인 수 순' },
];

/** 고른 값을 차례로. 모르는 값이면 최근 고친 순 */
export function sortOf(value: string): MineOrder {
  return SORT_OPTIONS.find((option) => option.value === value)?.value ?? 'updated';
}

/** 카드의 쓰인 수와 관심 수. usedLabel 은 쓰인 것의 이름(캐릭터는 대화, 세계관은 시작)이다 */
export function countsText(work: { start_count: number; heart_count: number }, usedLabel: string): string {
  return `${usedLabel} ${work.start_count.toLocaleString('ko-KR')} · 관심 ${work.heart_count.toLocaleString('ko-KR')}`;
}

/** 시나리오의 칩. 운영자의 숨김은 게임 서버가 목록에 싣지 않아 없다 */
export const SCENARIO_CHIPS = STATUS_CHIPS.filter((chip) => chip.value !== 'hidden');

/**
 * 내 시나리오의 한 줄을 캐릭터, 세계관과 같은 모양으로(#1165). 공개한 적이 없으면 초안, 링크 공개면 링크 공개, 아니면 공개 중이다.
 * 공개 상태는 게임 서버의 공개 정보(published_at, unlisted)다
 */
export function scenarioWork(row: MyScenarioSummary) {
  return {
    id: row.id,
    name: row.title,
    updated_at: row.updated_at,
    start_count: row.start_count,
    heart_count: row.heart_count,
    visibility: row.unlisted ? ('unlisted' as const) : ('public' as const),
    latest_version: row.published_at === null ? null : 1,
    hidden_at: null,
  };
}
