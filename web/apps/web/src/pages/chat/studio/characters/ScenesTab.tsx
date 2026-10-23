// web/apps/web/src/pages/chat/studio/characters/ScenesTab.tsx
// 이벤트 씬 탭(C6): 조건이 맞은 뒤의 첫 답에 붙어 배경과 캐릭터를 대신하는 그림.
// 조건은 장소에 갔다, 물건을 건넸다, 호감도가 그 단계에 올랐다이고, 대상은 저장한 장소·물건·호감도 단계에서 고른다.
// 해금 대상이면 한 번 연 것이 계정에 남아 갤러리(C7)에 보인다.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetCharacterDetail, AssetSceneWhen } from '../../../../api/types';
import { ImagePicker } from '../../../../components/ImagePicker';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from './CharacterForm';
import { newKey } from './keys';
import {
  addScene,
  changeScene,
  removeScene,
  SCENE_DESCRIPTION_MAX,
  SCENE_TITLE_MAX,
  sceneDrafts,
  SCENES_MAX,
  scenesHints,
  sceneTargets,
  toScenesBody,
  type SceneDraft,
} from './scenesForm';
import { useCharacterSave } from './useCharacterSave';

const KINDS: Record<AssetSceneWhen, string> = {
  reach_place: '장소에 갔다',
  give_item: '물건을 건넸다',
  affection_stage: '호감도가 그 단계에 올랐다',
};

const EMPTY_TARGETS: Record<AssetSceneWhen, string> = {
  reach_place: '저장한 장소가 없습니다. 지도 탭에서 먼저 더해 주세요.',
  give_item: '저장한 물건이 없습니다. 물건 탭에서 먼저 더해 주세요.',
  affection_stage: '저장한 호감도 단계가 없습니다. 호감도 탭에서 먼저 켜 주세요.',
};

export function ScenesTab({ character }: { character: AssetCharacterDetail }) {
  const [scenes, setScenes] = useState<SceneDraft[]>(() => sceneDrafts(character));
  const saving = useCharacterSave(character.id);
  const hints = scenesHints(scenes);

  async function submit() {
    const saved = await saving.save(toScenesBody(scenes));
    if (saved) setScenes(sceneDrafts(saved));
  }

  function change(id: string, changes: Partial<Omit<SceneDraft, 'id'>>) {
    setScenes((current) => changeScene(current, id, changes));
  }

  return (
    <CharacterForm
      label="이벤트 씬"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <p className="hint">조건이 맞은 뒤의 첫 답에 이 그림이 배경과 캐릭터를 대신합니다. 설명은 그 답을 쓸 때 모델이 읽습니다.</p>
      {scenes.length === 0 ? <p>아직 이벤트 씬이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="이벤트 씬">
        {scenes.map((scene, index) => {
          const targets = sceneTargets(character, scene.kind);
          const found = hints[scene.id] ?? {};
          return (
            <li key={scene.id} className="scenario-opening">
              <TextField
                label={`이벤트 씬 ${index + 1}의 제목`}
                maxLength={SCENE_TITLE_MAX}
                value={scene.title}
                onChange={(event) => change(scene.id, { title: event.target.value })}
                error={found.title}
              />
              <ImagePicker
                label={`이벤트 씬 ${index + 1}의 그림`}
                imageId={scene.imageId}
                onChange={(imageId) => change(scene.id, { imageId })}
                hint={found.image}
              />
              <TextAreaField
                label={`이벤트 씬 ${index + 1}의 설명(선택)`}
                rows={3}
                maxLength={SCENE_DESCRIPTION_MAX}
                value={scene.description}
                onChange={(event) => change(scene.id, { description: event.target.value })}
                error={found.description}
              />
              <SelectField
                label={`이벤트 씬 ${index + 1}의 조건`}
                value={scene.kind}
                onChange={(event) => change(scene.id, { kind: event.target.value as AssetSceneWhen })}
              >
                {Object.entries(KINDS).map(([kind, label]) => (
                  <option key={kind} value={kind}>
                    {label}
                  </option>
                ))}
              </SelectField>
              <SelectField
                label={`이벤트 씬 ${index + 1}의 대상`}
                value={scene.target}
                onChange={(event) => change(scene.id, { target: event.target.value })}
                error={found.target}
                hint={targets.length === 0 ? EMPTY_TARGETS[scene.kind] : undefined}
              >
                <option value="">고르지 않음</option>
                {targets.map((target) => (
                  <option key={target.value} value={target.value}>
                    {target.label}
                  </option>
                ))}
              </SelectField>
              <Checkbox
                label="해금 대상"
                description="한 번 열면 계정에 남아 갤러리에 보입니다. 끄면 이야기 중에만 나옵니다."
                checked={scene.collectible}
                onChange={(event) => change(scene.id, { collectible: event.target.checked })}
              />
              <div className="form-actions">
                <Button variant="quiet" aria-label={`이벤트 씬 ${index + 1} 지우기`} onClick={() => setScenes((current) => removeScene(current, scene.id))}>
                  지우기
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button
          variant="secondary"
          disabled={scenes.length >= SCENES_MAX}
          onClick={() => setScenes((current) => addScene(current, newKey('scene', current.map((scene) => scene.id))))}
        >
          이벤트 씬 더하기
        </Button>{' '}
        <span className="hint">
          {scenes.length} / {SCENES_MAX}
        </span>
      </p>
    </CharacterForm>
  );
}
