// web/apps/web/src/pages/trpg/studio/scenarios/picturesForm.ts
// 시나리오의 그림 탭(#1163)의 입력. 로어 항목 하나에 한 줄(entry_id, image_id, by_time)이고 목록을 통째로 보낸다. 순수한 함수다.
// 장소 항목은 테이블 방의 그림 창의 배경, 인물 항목은 그 인물의 그림, 사건 항목은 컷신이다.
// 장소의 배경은 하루의 때마다 따로 둘 수 있다(by_time). 없는 때는 기본 그림(image_id)이다. 기본 그림이 있어야 줄이 있다.
// 서버(trpg-server/app/assets/scenarios/schemas.py 의 EntryPicture)는 200줄까지, 항목마다 한 줄을 받는다.
// 때마다의 그림이 장소 항목에만 있는지는 게시 점검이 본다(picture_time_not_place).

import type { DayTime, ScenarioDetail, ScenarioUpdate } from '../../../../api/types';
import { DAY_TIMES } from './wandersForm';

export const MAX_PICTURES = 200;

export type TimePictures = Partial<Record<DayTime, string>>;

export type PictureRow = { entryId: string; imageId: string; byTime: TimePictures };

export function picturesDraft(scenario: ScenarioDetail): PictureRow[] {
  return scenario.pictures.map((picture) => ({ entryId: picture.entry_id, imageId: picture.image_id, byTime: readTimes(picture.by_time) }));
}

/** 서버의 때마다의 그림에서 아는 때만 읽는다 */
function readTimes(byTime: Record<string, string> | undefined): TimePictures {
  const times: TimePictures = {};
  for (const time of DAY_TIMES) {
    const imageId = byTime?.[time];
    if (imageId) times[time] = imageId;
  }
  return times;
}

function rowOf(rows: PictureRow[], entryId: string): PictureRow | undefined {
  return rows.find((row) => row.entryId === entryId);
}

/** 그 항목에 붙인 기본 그림. 없으면 null */
export function pictureOf(rows: PictureRow[], entryId: string): string | null {
  return rowOf(rows, entryId)?.imageId ?? null;
}

/** 그 항목의 그 때의 그림. 없으면 null */
export function timePictureOf(rows: PictureRow[], entryId: string, time: DayTime): string | null {
  return rowOf(rows, entryId)?.byTime[time] ?? null;
}

/** 그 항목에 때마다의 그림이 몇 개 있나 */
export function timeCount(rows: PictureRow[], entryId: string): number {
  return Object.keys(rowOf(rows, entryId)?.byTime ?? {}).length;
}

/**
 * 그 항목의 기본 그림을 바꾼다. null 이면 줄을 뗀다(때마다의 그림도 함께). 이미 있던 항목은 자리와 때마다의 그림을 지키고,
 * 새 항목은 끝에 붙인다. 가득 찼으면 새 항목은 붙이지 않는다(바꾸기와 떼기는 된다)
 */
export function withPicture(rows: PictureRow[], entryId: string, imageId: string | null): PictureRow[] {
  if (imageId === null) return rows.filter((row) => row.entryId !== entryId);
  if (rowOf(rows, entryId)) return rows.map((row) => (row.entryId === entryId ? { ...row, imageId } : row));
  return rows.length < MAX_PICTURES ? [...rows, { entryId, imageId, byTime: {} }] : rows;
}

/** 그 항목의 그 때의 그림을 바꾼다. null 이면 뗀다. 기본 그림이 없는 항목(줄이 없다)이면 그대로다 */
export function withTimePicture(rows: PictureRow[], entryId: string, time: DayTime, imageId: string | null): PictureRow[] {
  return rows.map((row) => {
    if (row.entryId !== entryId) return row;
    const byTime = { ...row.byTime };
    if (imageId === null) delete byTime[time];
    else byTime[time] = imageId;
    return { ...row, byTime };
  });
}

/** 그 항목의 때마다의 그림을 모두 뗀다 */
export function withoutTimes(rows: PictureRow[], entryId: string): PictureRow[] {
  return rows.map((row) => (row.entryId === entryId ? { ...row, byTime: {} } : row));
}

/** 그림을 붙일 수 있는 항목(붙인 로어북의 장소, 인물, 사건)이 아닌 것의 그림. 로어북을 뗐거나 항목을 지웠거나 종류가 바뀌었다 */
export function strayPictures(rows: PictureRow[], known: string[]): PictureRow[] {
  return rows.filter((row) => !known.includes(row.entryId));
}

/** 그림 탭의 칸만 보낸다. 때마다의 그림은 하루의 차례로 적는다 */
export function toPicturesBody(rows: PictureRow[]): ScenarioUpdate {
  return {
    pictures: rows.map((row) => ({
      entry_id: row.entryId,
      image_id: row.imageId,
      by_time: Object.fromEntries(DAY_TIMES.flatMap((time) => (row.byTime[time] ? [[time, row.byTime[time]]] : []))),
    })),
  };
}
