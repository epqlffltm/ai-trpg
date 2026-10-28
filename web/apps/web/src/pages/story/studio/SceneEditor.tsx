// web/apps/web/src/pages/story/studio/SceneEditor.tsx
// 장면 지시의 칸(D7). 상황(모델이 읽는다), 나오는 인물(4 명까지), 일러스트와 해금 대상. 이벤트와 엔딩이 함께 쓴다.

import { Checkbox } from '@ai-trpg/ui';
import { ImagePicker } from '../../../components/ImagePicker';
import { TextAreaField } from '../../../components/TextAreaField';
import type { Choice } from './conditionsForm';
import { SCENE_CAST_MAX, SCENE_TEXT_MAX, setSceneImage, toggleSceneCast, type SceneDraft } from './sceneForm';
import { labelOr } from './worldLabels';

type Props = { prefix: string; scene: SceneDraft; cast: Choice[]; hint: string | undefined; onChange: (scene: SceneDraft) => void };

export function SceneEditor({ prefix, scene, cast, hint, onChange }: Props) {
  return (
    <fieldset className="scenario-choices">
      <legend>{prefix}의 장면</legend>
      <TextAreaField
        label={`${prefix}의 상황`}
        rows={4}
        maxLength={SCENE_TEXT_MAX}
        value={scene.text}
        onChange={(event) => onChange({ ...scene, text: event.target.value })}
        error={hint}
        hint="모델이 읽고 이 장면을 씁니다. 사용자에게는 보이지 않습니다."
      />
      <p>
        나오는 인물 <span className="hint">({scene.cast.length} / {SCENE_CAST_MAX})</span>
      </p>
      {cast.length === 0 ? <p className="hint">인물 탭에서 인물을 먼저 저장해 주세요.</p> : null}
      {cast.map((member, index) => (
        <Checkbox
          key={member.id}
          label={`${prefix}에 ${labelOr(member.name, `인물 ${index + 1}`)}`}
          checked={scene.cast.includes(member.id)}
          disabled={!scene.cast.includes(member.id) && scene.cast.length >= SCENE_CAST_MAX}
          onChange={() => onChange(toggleSceneCast(scene, member.id))}
        />
      ))}
      <ImagePicker label={`${prefix}의 일러스트`} imageId={scene.imageId} onChange={(imageId) => onChange(setSceneImage(scene, imageId))} hint="있으면 그림 창의 배경과 인물을 대신합니다." />
      <Checkbox
        label={`${prefix}의 일러스트를 갤러리에 남긴다`}
        checked={scene.collectible}
        disabled={scene.imageId === null}
        onChange={(event) => onChange({ ...scene, collectible: event.target.checked })}
        description="열린 일러스트는 계정에 남아 갤러리에 나옵니다. 일러스트가 있어야 고릅니다."
      />
    </fieldset>
  );
}
