// web/apps/web/src/pages/story/studio/WorldMapTab.tsx
// 세계관의 지도 탭(D7): 장소(이름, 모델이 읽는 설명, 기본 배경, 시간대마다의 배경), 길(두 장소와 걸리는 시간).
// 시간대는 진행 탭에서 저장한 것이다. 장소를 지우면 그 장소를 잇는 길도 지우고, 시작 장소였으면 비운다(worldMapForm.ts).

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { StoryWorldDetail, StoryWorldPlace } from '../../../api/storyWorlds';
import { ImagePicker } from '../../../components/ImagePicker';
import { TextAreaField } from '../../../components/TextAreaField';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import { useWorldSave } from './useWorldSave';
import { labelOr } from './worldLabels';
import {
  addWorldPath,
  addWorldPlace,
  changeWorldPath,
  changeWorldPlace,
  hasWorldMapHints,
  PLACE_DESCRIPTION_MAX,
  PLACE_NAME_MAX,
  removeWorldPath,
  removeWorldPlace,
  setBackground,
  toWorldMapBody,
  WORLD_PATHS_MAX,
  WORLD_PLACES_MAX,
  worldMapDraft,
  worldMapHints,
  worldPathsTouching,
  type WorldMapDraft,
  type WorldMapHints,
} from './worldMapForm';

type Update = (change: (draft: WorldMapDraft) => WorldMapDraft) => void;

export function WorldMapTab({ world }: { world: StoryWorldDetail }) {
  const [draft, setDraft] = useState<WorldMapDraft>(() => worldMapDraft(world));
  const saving = useWorldSave(world.id);
  const hints = worldMapHints(draft);
  const update: Update = (change) => setDraft(change);

  async function submit() {
    const saved = await saving.save(toWorldMapBody(draft, world));
    if (saved) setDraft(worldMapDraft(saved));
  }

  return (
    <StudioForm label="지도" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hasWorldMapHints(hints)} onSubmit={() => void submit()}>
      <p className="hint">
        이야기는 장소 사이를 길로 옮겨 다니고, 길에 걸리는 시간만큼 시각이 흐릅니다. 시작 장소는 진행 탭에서 고릅니다. 그림은 PNG, JPEG, WebP 를 10MB 까지 올리고, 저장해야 붙습니다.
      </p>
      <PlacesSection world={world} draft={draft} hints={hints} update={update} />
      <PathsSection draft={draft} hints={hints} update={update} />
    </StudioForm>
  );
}

function PlaceOptions({ places }: { places: StoryWorldPlace[] }) {
  return (
    <>
      {places.map((place, index) => (
        <option key={place.id} value={place.id}>
          {labelOr(place.name, `장소 ${index + 1}`)}
        </option>
      ))}
    </>
  );
}

function PlacesSection({ world, draft, hints, update }: { world: StoryWorldDetail; draft: WorldMapDraft; hints: WorldMapHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>장소</legend>
      {draft.places.length === 0 ? <p>아직 장소가 없습니다. 장소가 하나는 있어야 게시합니다.</p> : null}
      <ol className="plain-list" aria-label="장소">
        {draft.places.map((place, index) => {
          const touching = worldPathsTouching(draft, place.id);
          const name = labelOr(place.name, `장소 ${index + 1}`);
          return (
            <li key={place.id} className="scenario-opening">
              <TextField
                label={`장소 ${index + 1}의 이름`}
                maxLength={PLACE_NAME_MAX}
                value={place.name}
                onChange={(event) => update((current) => changeWorldPlace(current, place.id, { name: event.target.value }))}
                error={hints.places[place.id]?.name}
              />
              <TextAreaField
                label={`장소 ${index + 1}의 설명(선택)`}
                rows={3}
                maxLength={PLACE_DESCRIPTION_MAX}
                value={place.description ?? ''}
                onChange={(event) => update((current) => changeWorldPlace(current, place.id, { description: event.target.value }))}
                error={hints.places[place.id]?.description}
                hint="모델이 읽는 장소의 모습입니다."
              />
              <details>
                <summary>
                  {name}의 그림 <span className="hint">(시간대 배경 {Object.keys(place.backgrounds).length}개)</span>
                </summary>
                <ImagePicker
                  label={`${name}의 기본 배경`}
                  imageId={place.image_id ?? null}
                  onChange={(imageId) => update((current) => changeWorldPlace(current, place.id, { image_id: imageId }))}
                  hint="시간대의 배경이 없으면 이 그림을 씁니다."
                />
                {world.slots.map((slot) => (
                  <ImagePicker
                    key={slot.id}
                    label={`${name}의 ${slot.name} 배경`}
                    imageId={place.backgrounds[slot.id] ?? null}
                    onChange={(imageId) => update((current) => setBackground(current, place.id, slot.id, imageId))}
                  />
                ))}
              </details>
              <div className="form-actions">
                <Button variant="quiet" aria-label={`장소 ${index + 1} 지우기`} onClick={() => update((current) => removeWorldPlace(current, place.id))}>
                  지우기
                </Button>
                {touching > 0 ? <span className="hint">이 장소를 잇는 길 {touching}개도 함께 지웁니다.</span> : null}
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button
          variant="secondary"
          disabled={draft.places.length >= WORLD_PLACES_MAX}
          onClick={() => update((current) => addWorldPlace(current, newKey('place', current.places.map((place) => place.id))))}
        >
          장소 더하기
        </Button>{' '}
        <span className="hint">
          {draft.places.length} / {WORLD_PLACES_MAX}
        </span>
      </p>
    </fieldset>
  );
}

function PathsSection({ draft, hints, update }: { draft: WorldMapDraft; hints: WorldMapHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>길</legend>
      {draft.paths.length === 0 ? <p>아직 길이 없습니다. 길은 양쪽으로 다닙니다.</p> : null}
      <ol className="plain-list" aria-label="길">
        {draft.paths.map((path, index) => (
          // 길에는 서버의 id 가 없다. 차례가 곧 그 길이다
          <li key={index} className="scenario-opening">
            <SelectField label={`길 ${index + 1}의 한쪽`} value={path.a} onChange={(event) => update((current) => changeWorldPath(current, index, { a: event.target.value }))}>
              <option value="">고르지 않음</option>
              <PlaceOptions places={draft.places} />
            </SelectField>
            <SelectField label={`길 ${index + 1}의 다른 쪽`} value={path.b} onChange={(event) => update((current) => changeWorldPath(current, index, { b: event.target.value }))}>
              <option value="">고르지 않음</option>
              <PlaceOptions places={draft.places} />
            </SelectField>
            <TextField
              label={`길 ${index + 1}의 시간(분)`}
              inputMode="numeric"
              value={path.minutes}
              onChange={(event) => update((current) => changeWorldPath(current, index, { minutes: event.target.value }))}
              error={hints.paths[index]}
            />
            <div className="form-actions">
              <Button variant="quiet" aria-label={`길 ${index + 1} 지우기`} onClick={() => update((current) => removeWorldPath(current, index))}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.places.length < 2 || draft.paths.length >= WORLD_PATHS_MAX} onClick={() => update(addWorldPath)}>
          길 더하기
        </Button>{' '}
        <span className="hint">{draft.places.length < 2 ? '장소가 둘 이상 있어야 길을 놓습니다.' : `${draft.paths.length} / ${WORLD_PATHS_MAX}`}</span>
      </p>
    </fieldset>
  );
}
