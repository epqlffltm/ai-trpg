// web/apps/web/src/pages/gallery/tableSnapshotGalleryView.ts
// 갤러리(C7)의 TRPG "내 장면 그림"에 보일 글과 주소. 순수한 함수다.

import type { KeptTableSnapshot } from '../../api/tableSnapshots';

/** 칸의 이름. "추격전 · 라운드 3". 테이블을 지웠으면 "지운 테이블 · 라운드 3" */
export function tableSnapshotCaption(snapshot: Pick<KeptTableSnapshot, 'table_title' | 'round_number'>): string {
  const title = snapshot.table_title?.trim() || '지운 테이블';
  return `${title} · 라운드 ${snapshot.round_number}`;
}

/** 그 그림을 그린 테이블의 주소. 테이블을 지웠으면 null */
export function tablePath(snapshot: Pick<KeptTableSnapshot, 'table_id'>): string | null {
  return snapshot.table_id ? `/trpg/tables/${snapshot.table_id}` : null;
}
