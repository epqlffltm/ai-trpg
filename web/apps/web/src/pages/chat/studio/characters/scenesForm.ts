// web/apps/web/src/pages/chat/studio/characters/scenesForm.ts
// 이벤트 씬 탭의 입력. 순수한 함수다. 규칙은 서버와 같다(asset-server/app/characters/schemas.py 의 EventScene).
//
//   - 이벤트 씬은 조건이 맞은 뒤의 첫 답에 붙어 배경과 캐릭터를 대신하는 그림이다(chat). 30 개까지
//   - 조건: 장소에 갔다(장소의 id), 물건을 건넸다(물건의 id), 호감도가 그 단계에 올랐다(단계의 이름)
//   - 해금 대상(collectible)이면 한 번 열면 계정에 남고 갤러리와 소개의 칸에 보인다. 아니면 이야기 중에만 나온다
//   - 설명(300자)은 그 답을 쓸 때 모델이 읽는 장면의 설명이다. 제목(30자)과 그림은 꼭 있어야 한다
//   - id 는 화면이 붙인다(keys.ts). 조건의 종류를 바꾸면 대상을 비운다(장소, 물건, 단계는 서로 다른 것이다)

import type { AssetCharacterDetail, AssetCharacterUpdate, AssetSceneWhen } from '../../../../api/types';

export const SCENES_MAX = 30;
export const SCENE_TITLE_MAX = 30;
export const SCENE_DESCRIPTION_MAX = 300;

export type SceneDraft = {
  id: string;
  title: string;
  imageId: string | null;
  description: string;
  collectible: boolean;
  kind: AssetSceneWhen;
  target: string;
};

export function sceneDrafts(character: AssetCharacterDetail): SceneDraft[] {
  return character.event_scenes.map((scene) => ({
    id: scene.id,
    title: scene.title,
    imageId: scene.image_id,
    description: scene.description ?? '',
    collectible: scene.collectible ?? true,
    kind: scene.when.kind,
    target: scene.when.target,
  }));
}

export function addScene(scenes: SceneDraft[], id: string): SceneDraft[] {
  if (scenes.length >= SCENES_MAX) return scenes;
  return [...scenes, { id, title: '', imageId: null, description: '', collectible: true, kind: 'reach_place', target: '' }];
}

/** 이벤트 씬을 바꾼다. 조건의 종류가 바뀌면 대상을 비운다 */
export function changeScene(scenes: SceneDraft[], id: string, changes: Partial<Omit<SceneDraft, 'id'>>): SceneDraft[] {
  return scenes.map((scene) => {
    if (scene.id !== id) return scene;
    const next = { ...scene, ...changes };
    return changes.kind && changes.kind !== scene.kind ? { ...next, target: '' } : next;
  });
}

export function removeScene(scenes: SceneDraft[], id: string): SceneDraft[] {
  return scenes.filter((scene) => scene.id !== id);
}

export type SceneHints = Record<string, Partial<Record<'title' | 'image' | 'description' | 'target', string>>>;

/** 이벤트 씬마다(id → 칸 → 글)의 문제 */
export function scenesHints(scenes: SceneDraft[]): SceneHints {
  const hints: SceneHints = {};
  for (const scene of scenes) {
    const found: SceneHints[string] = {};
    const title = scene.title.trim();
    if (title === '') found.title = '제목을 적어 주세요.';
    else if (title.length > SCENE_TITLE_MAX) found.title = `제목은 ${SCENE_TITLE_MAX}자까지입니다.`;
    if (scene.imageId === null) found.image = '그림을 올려 주세요.';
    if (scene.description.trim().length > SCENE_DESCRIPTION_MAX) found.description = `설명은 ${SCENE_DESCRIPTION_MAX}자까지입니다.`;
    if (scene.target === '') found.target = '조건의 대상을 골라 주세요.';
    if (Object.keys(found).length > 0) hints[scene.id] = found;
  }
  return hints;
}

/** 이벤트 씬 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toScenesBody(scenes: SceneDraft[]): AssetCharacterUpdate {
  return {
    event_scenes: scenes.map((scene) => ({
      id: scene.id,
      title: scene.title.trim(),
      image_id: scene.imageId as string,
      description: scene.description.trim(),
      collectible: scene.collectible,
      when: { kind: scene.kind, target: scene.target },
    })),
  };
}

/** 조건의 종류마다 고를 수 있는 대상(값과 보이는 이름). 저장한 장소, 물건, 호감도 단계에서 고른다 */
export function sceneTargets(character: AssetCharacterDetail, kind: AssetSceneWhen): { value: string; label: string }[] {
  if (kind === 'reach_place') return character.places.map((place, index) => ({ value: place.id, label: place.name || `장소 ${index + 1}` }));
  if (kind === 'give_item') return character.items.map((item, index) => ({ value: item.id, label: item.name || `물건 ${index + 1}` }));
  return (character.affection?.stages ?? []).map((stage) => ({ value: stage.name, label: stage.name }));
}
