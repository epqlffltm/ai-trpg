// web/apps/web/src/pages/trpg/studio/worlds/worldForm.ts
// 세계관 만들기와 고치기(B9)의 입력. 처음 값, 보내기 전의 검사, 서버에 보낼 본문. 순수한 함수다.
// 한도는 서버의 것이다(trpg-server/app/assets/models.py 의 WORLD_SETTING_MAX_LENGTH, WORLD_GM_NOTES_MAX_LENGTH).

import type { WorldCreate, WorldDetail, WorldUpdate } from '../../../../api/types';
import { DESCRIPTION_MAX, TITLE_MAX } from '../rulebooks/rulebookForm';

export const SETTING_MAX = 8000;
export const GM_NOTES_MAX = 4000;

export type WorldDraft = {
  title: string;
  description: string;
  setting: string;
  gmNotes: string;
  referencesAllowed: boolean;
};

export function newWorldDraft(): WorldDraft {
  return { title: '', description: '', setting: '', gmNotes: '', referencesAllowed: false };
}

export function worldDraft(world: WorldDetail): WorldDraft {
  return {
    title: world.title,
    description: world.description,
    setting: world.setting,
    gmNotes: world.gm_notes,
    referencesAllowed: world.references_allowed,
  };
}

/** 보내기 전에 알릴 것. 칸 이름(서버의 칸 이름) → 글. 비었으면 보낼 수 있다 */
export function worldHints(draft: WorldDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const title = draft.title.trim();
  if (title === '') hints.title = '제목을 적어 주세요.';
  else if (title.length > TITLE_MAX) hints.title = `제목은 ${TITLE_MAX}자까지입니다.`;
  if (draft.description.length > DESCRIPTION_MAX) hints.description = `소개는 ${DESCRIPTION_MAX}자까지입니다.`;
  if (draft.setting.length > SETTING_MAX) hints.setting = `설정은 ${SETTING_MAX}자까지입니다.`;
  if (draft.gmNotes.length > GM_NOTES_MAX) hints.gm_notes = `GM 메모는 ${GM_NOTES_MAX}자까지입니다.`;
  return hints;
}

export function toWorldCreate(draft: WorldDraft): WorldCreate {
  return {
    title: draft.title.trim(),
    description: draft.description,
    setting: draft.setting,
    gm_notes: draft.gmNotes,
    references_allowed: draft.referencesAllowed,
  };
}

/** 고칠 수 있는 칸을 모두 보낸다. 글을 비우면 빈 글로 보낸다(서버는 null 을 "보내지 않음"으로 읽는다) */
export function toWorldUpdate(draft: WorldDraft): WorldUpdate {
  return toWorldCreate(draft);
}
