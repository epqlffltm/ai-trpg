// web/apps/web/src/pages/trpg/studio/scenarios/picturesForm.ts
// 시나리오의 그림 탭(#1163)의 입력. 로어 항목 하나에 그림 하나(entry_id, image_id)이고 목록을 통째로 보낸다. 순수한 함수다.
// 장소 항목은 테이블 방의 그림 창의 배경, 인물 항목은 그 인물의 그림, 사건 항목은 컷신이다.
// 서버(trpg-server/app/assets/scenarios/schemas.py 의 EntryPicture)는 200개까지, 항목마다 하나를 받는다.

import type { ScenarioDetail, ScenarioUpdate } from '../../../../api/types';

export const MAX_PICTURES = 200;

export type PictureRow = { entryId: string; imageId: string };

export function picturesDraft(scenario: ScenarioDetail): PictureRow[] {
  return scenario.pictures.map((picture) => ({ entryId: picture.entry_id, imageId: picture.image_id }));
}

/** 그 항목에 붙인 그림. 없으면 null */
export function pictureOf(rows: PictureRow[], entryId: string): string | null {
  return rows.find((row) => row.entryId === entryId)?.imageId ?? null;
}

/**
 * 그 항목의 그림을 바꾼다. null 이면 뗀다. 이미 있던 항목은 자리를 지키고, 새 항목은 끝에 붙인다.
 * 가득 찼으면 새 항목은 붙이지 않는다(바꾸기와 떼기는 된다)
 */
export function withPicture(rows: PictureRow[], entryId: string, imageId: string | null): PictureRow[] {
  if (imageId === null) return rows.filter((row) => row.entryId !== entryId);
  if (rows.some((row) => row.entryId === entryId)) return rows.map((row) => (row.entryId === entryId ? { entryId, imageId } : row));
  return rows.length < MAX_PICTURES ? [...rows, { entryId, imageId }] : rows;
}

/** 그림을 붙일 수 있는 항목(붙인 로어북의 장소, 인물, 사건)이 아닌 것의 그림. 로어북을 뗐거나 항목을 지웠거나 종류가 바뀌었다 */
export function strayPictures(rows: PictureRow[], known: string[]): PictureRow[] {
  return rows.filter((row) => !known.includes(row.entryId));
}

/** 그림 탭의 칸만 보낸다 */
export function toPicturesBody(rows: PictureRow[]): ScenarioUpdate {
  return { pictures: rows.map((row) => ({ entry_id: row.entryId, image_id: row.imageId })) };
}
