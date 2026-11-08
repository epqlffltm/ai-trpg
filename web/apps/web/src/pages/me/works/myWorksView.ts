// web/apps/web/src/pages/me/works/myWorksView.ts
// 마이페이지 제작자 탭의 내 작품(Stitch 10번)을 보이기 전의 순수한 함수. 작품의 공개 상태와 칩으로 거르기.
// 공개 상태는 asset 서버가 주는 값(공개 범위, 공개한 판, 운영자의 숨김)으로 정한다. TRPG 시나리오는 이 값이 없어 칩을 달지 않는다.

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
