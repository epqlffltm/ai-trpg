// web/apps/web/src/pages/trpg/studio/scenarios/startForm.ts
// 시나리오 만들기의 입력: 제목, 소개, 추천 서술 모델. 서버가 만들 때 꼭 받는 것이 제목과 추천 모델이다. 순수한 함수다.
// 나머지(등급, 재료, 스타팅 …)는 만든 뒤 탭에서 채운다.

import type { ScenarioStart } from '../../../../api/scenarios';
import { DESCRIPTION_MAX, TITLE_MAX } from '../rulebooks/rulebookForm';

export type StartDraft = { title: string; description: string; narrationModel: string };

export function newStartDraft(): StartDraft {
  return { title: '', description: '', narrationModel: '' };
}

export function startHints(draft: StartDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const title = draft.title.trim();
  if (title === '') hints.title = '제목을 적어 주세요.';
  else if (title.length > TITLE_MAX) hints.title = `제목은 ${TITLE_MAX}자까지입니다.`;
  if (draft.description.length > DESCRIPTION_MAX) hints.description = `소개는 ${DESCRIPTION_MAX}자까지입니다.`;
  if (draft.narrationModel === '') hints.narration_model = '추천 서술 모델을 골라 주세요.';
  return hints;
}

export function toStartBody(draft: StartDraft): ScenarioStart {
  return { title: draft.title.trim(), description: draft.description, narration_model: draft.narrationModel };
}
