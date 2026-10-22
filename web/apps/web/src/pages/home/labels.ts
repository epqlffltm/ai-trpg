// web/apps/web/src/pages/home/labels.ts
// 서버의 값(영문의 이름)을 화면의 글로 바꾼다.

import type { TableSummary } from '../../api/types';

const TABLE_STATUS: Record<TableSummary['status'], string> = {
  recruiting: '모집 중',
  playing: '진행 중',
  ended: '끝남',
};

export function tableStatusLabel(status: TableSummary['status']): string {
  return TABLE_STATUS[status];
}

/** 성인 등급만 표시를 붙인다. 전체이용가는 붙이지 않는다 */
export function ratingBadge(rating: 'all' | 'adult'): string | null {
  return rating === 'adult' ? '성인' : null;
}
