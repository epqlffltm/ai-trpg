// web/apps/web/src/pages/chat/studio/characters/MapTab.tsx
// 캐릭터의 지도 탭(C6): 장소(이름, 모델이 읽는 설명), 길(두 장소와 걸리는 시간), 처음 있는 장소.
// chat 의 대화는 장소 사이를 길로 옮겨 다니고 그만큼 시각이 흐른다. 장소의 배경 그림은 그림 탭에서 붙인다.
// 장소를 지우면 그 장소를 잇는 길도 지우고, 처음 있는 장소였으면 비운다(mapForm.ts).

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetCharacterDetail, AssetPlace } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from './CharacterForm';
import { newKey } from './keys';
import {
  addPath,
  addPlace,
  changePath,
  changePlace,
  hasMapHints,
  mapDraft,
  mapHints,
  PATHS_MAX,
  pathsTouching,
  PLACE_DESCRIPTION_MAX,
  PLACE_NAME_MAX,
  PLACES_MAX,
  removePath,
  removePlace,
  toMapBody,
  type MapDraft,
  type MapHints,
} from './mapForm';
import { useCharacterSave } from './useCharacterSave';

type Update = (change: (draft: MapDraft) => MapDraft) => void;

export function MapTab({ character }: { character: AssetCharacterDetail }) {
  const [draft, setDraft] = useState<MapDraft>(() => mapDraft(character));
  const saving = useCharacterSave(character.id);
  const hints = mapHints(draft);
  const update: Update = (change) => setDraft(change);

  async function submit() {
    const saved = await saving.save(toMapBody(draft, character));
    if (saved) setDraft(mapDraft(saved));
  }

  return (
    <CharacterForm
      label="지도"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={hasMapHints(hints)}
      onSubmit={() => void submit()}
    >
      <p className="hint">대화하며 장소 사이를 길로 옮겨 다니고, 길에 걸리는 시간만큼 시각이 흐릅니다. 장소가 있으면 처음 있는 장소를 골라야 게시할 수 있습니다.</p>
      <PlacesSection draft={draft} hints={hints} update={update} />
      <PathsSection draft={draft} hints={hints} update={update} />
      <SelectField
        label="처음 있는 장소"
        name="start_place"
        value={draft.startPlace}
        onChange={(event) => update((current) => ({ ...current, startPlace: event.target.value }))}
        hint="모든 시작 상황이 이 장소에서 시작합니다."
      >
        <option value="">고르지 않음</option>
        <PlaceOptions places={draft.places} />
      </SelectField>
    </CharacterForm>
  );
}

/** 장소를 고르는 칸의 보기. 이름이 아직 없으면 차례로 부른다 */
function PlaceOptions({ places }: { places: AssetPlace[] }) {
  return (
    <>
      {places.map((place, index) => (
        <option key={place.id} value={place.id}>
          {placeName(place, index)}
        </option>
      ))}
    </>
  );
}

function placeName(place: AssetPlace, index: number): string {
  return place.name.trim() || `장소 ${index + 1}`;
}

function PlacesSection({ draft, hints, update }: { draft: MapDraft; hints: MapHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>장소</legend>
      {draft.places.length === 0 ? <p>아직 장소가 없습니다. 장소가 없으면 대화는 한자리에서 이어집니다.</p> : null}
      <ol className="plain-list" aria-label="장소">
        {draft.places.map((place, index) => {
          const touching = pathsTouching(draft, place.id);
          return (
            <li key={place.id} className="scenario-opening">
              <TextField
                label={`장소 ${index + 1}의 이름`}
                maxLength={PLACE_NAME_MAX}
                value={place.name}
                onChange={(event) => update((current) => changePlace(current, place.id, { name: event.target.value }))}
                error={hints.places[place.id]?.name}
              />
              <TextAreaField
                label={`장소 ${index + 1}의 설명(선택)`}
                rows={3}
                maxLength={PLACE_DESCRIPTION_MAX}
                value={place.description ?? ''}
                onChange={(event) => update((current) => changePlace(current, place.id, { description: event.target.value }))}
                error={hints.places[place.id]?.description}
                hint="모델이 읽는 장소의 모습입니다."
              />
              <div className="form-actions">
                <Button variant="quiet" aria-label={`장소 ${index + 1} 지우기`} onClick={() => update((current) => removePlace(current, place.id))}>
                  지우기
                </Button>
                {touching > 0 ? <span className="hint">이 장소를 잇는 길 {touching}개도 함께 지웁니다.</span> : null}
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.places.length >= PLACES_MAX} onClick={() => update((current) => addPlace(current, newKey('place', current.places.map((place) => place.id))))}>
          장소 더하기
        </Button>{' '}
        <span className="hint">
          {draft.places.length} / {PLACES_MAX}
        </span>
      </p>
    </fieldset>
  );
}

function PathsSection({ draft, hints, update }: { draft: MapDraft; hints: MapHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>길</legend>
      {draft.paths.length === 0 ? <p>아직 길이 없습니다. 길은 양쪽으로 다닙니다.</p> : null}
      <ol className="plain-list" aria-label="길">
        {draft.paths.map((path, index) => (
          // 길에는 서버의 id 가 없다. 차례가 곧 그 길이다
          <li key={index} className="scenario-opening">
            <SelectField
              label={`길 ${index + 1}의 한쪽`}
              value={path.a}
              onChange={(event) => update((current) => changePath(current, index, { a: event.target.value }))}
            >
              <option value="">고르지 않음</option>
              <PlaceOptions places={draft.places} />
            </SelectField>
            <SelectField
              label={`길 ${index + 1}의 다른 쪽`}
              value={path.b}
              onChange={(event) => update((current) => changePath(current, index, { b: event.target.value }))}
            >
              <option value="">고르지 않음</option>
              <PlaceOptions places={draft.places} />
            </SelectField>
            <TextField
              label={`길 ${index + 1}의 시간(분)`}
              inputMode="numeric"
              value={path.minutes}
              onChange={(event) => update((current) => changePath(current, index, { minutes: event.target.value }))}
              error={hints.paths[index]}
            />
            <div className="form-actions">
              <Button variant="quiet" aria-label={`길 ${index + 1} 지우기`} onClick={() => update((current) => removePath(current, index))}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.places.length < 2 || draft.paths.length >= PATHS_MAX} onClick={() => update(addPath)}>
          길 더하기
        </Button>{' '}
        <span className="hint">{draft.places.length < 2 ? '장소가 둘 이상 있어야 길을 놓습니다.' : `${draft.paths.length} / ${PATHS_MAX}`}</span>
      </p>
    </fieldset>
  );
}
