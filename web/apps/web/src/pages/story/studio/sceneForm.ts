// web/apps/web/src/pages/story/studio/sceneForm.ts
// 장면 지시(이벤트와 엔딩이 함께 쓴다)의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/worlds/schemas.py 의 Scene).
//
//   - 상황(text): 모델에게 주는 장면의 설명이다. 1~1000 자
//   - 나오는 인물: 장면에 불러들이는 인물 4 명까지(겹치지 않는다)
//   - 일러스트: 있으면 그림 창의 배경과 인물을 대신한다. 해금 대상(collectible)이면 열릴 때 계정의 갤러리에 남는다(일러스트가 있어야 한다)

import type { StoryWorldScene } from '../../../api/storyWorlds';
import type { Choice } from './conditionsForm';

export const SCENE_TEXT_MAX = 1000;
export const SCENE_CAST_MAX = 4;

export type SceneDraft = { text: string; cast: string[]; imageId: string | null; collectible: boolean };

export const EMPTY_SCENE: SceneDraft = { text: '', cast: [], imageId: null, collectible: false };

export function sceneDraft(scene: StoryWorldScene): SceneDraft {
  return { text: scene.text, cast: [...scene.cast], imageId: scene.image_id ?? null, collectible: scene.collectible };
}

/** 인물을 장면에 넣고 뺀다. 4 명이 차면 더 넣지 않는다 */
export function toggleSceneCast(scene: SceneDraft, id: string): SceneDraft {
  if (scene.cast.includes(id)) return { ...scene, cast: scene.cast.filter((entry) => entry !== id) };
  return scene.cast.length >= SCENE_CAST_MAX ? scene : { ...scene, cast: [...scene.cast, id] };
}

/** 일러스트를 바꾼다. 떼면 해금 대상도 끈다 */
export function setSceneImage(scene: SceneDraft, imageId: string | null): SceneDraft {
  return { ...scene, imageId, collectible: imageId === null ? false : scene.collectible };
}

export function sceneHint(scene: SceneDraft, cast: Choice[]): string | undefined {
  const text = scene.text.trim();
  if (text === '') return '장면의 상황을 적어 주세요.';
  if (text.length > SCENE_TEXT_MAX) return `상황은 ${SCENE_TEXT_MAX}자까지입니다.`;
  if (scene.cast.some((id) => !cast.some((member) => member.id === id))) return '없는 인물이 장면에 있습니다. 다시 골라 주세요.';
  return undefined;
}

export function toScene(scene: SceneDraft): StoryWorldScene {
  return { text: scene.text.trim(), cast: scene.cast, image_id: scene.imageId, collectible: scene.imageId !== null && scene.collectible };
}
