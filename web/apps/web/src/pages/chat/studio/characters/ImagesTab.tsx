// web/apps/web/src/pages/chat/studio/characters/ImagesTab.tsx
// 캐릭터의 그림 탭(C6): 대표 그림, 장소마다의 배경(기본과 시간대 다섯), 물건마다의 그림.
// 장소와 물건은 지도·물건 탭에서 저장한 것이 나온다. 이 탭은 그림 칸만 고치고, 보낼 때 최근의 목록에 얹는다(imagesForm.ts).
// 그림은 자기가 올린 것만 붙는다(대표 그림은 저장할 때, 나머지는 게시할 때 서버가 본다).
// 캐릭터 그림(표정, 옷)과 이벤트 씬은 따로 탭이 있다(SpritesTab, ScenesTab).

import { useState } from 'react';
import type { AssetCharacterDetail, AssetItem, AssetPlace } from '../../../../api/types';
import { ImagePicker } from '../../../../components/ImagePicker';
import { CharacterForm } from './CharacterForm';
import {
  imagesDraft,
  itemImage,
  placeImages,
  setItemImage,
  setPlaceBackground,
  setPlaceDefault,
  timeLabel,
  TIMES_OF_DAY,
  toImagesBody,
  type ImagesDraft,
} from './imagesForm';
import { useCharacterSave } from './useCharacterSave';

type Update = (change: (draft: ImagesDraft) => ImagesDraft) => void;

export function ImagesTab({ character }: { character: AssetCharacterDetail }) {
  const [draft, setDraft] = useState<ImagesDraft>(() => imagesDraft(character));
  const saving = useCharacterSave(character.id);
  const update: Update = (change) => setDraft(change);

  async function submit() {
    const saved = await saving.save(toImagesBody(draft, character));
    if (saved) setDraft(imagesDraft(saved));
  }

  return (
    <CharacterForm label="그림" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={false} onSubmit={() => void submit()}>
      <p className="hint">PNG, JPEG, WebP 그림을 10MB 까지 올립니다. 올리면 서버가 다시 저장해 사진의 위치 정보 같은 것이 지워집니다. 저장해야 붙습니다.</p>
      <ImagePicker
        label="대표 그림"
        imageId={draft.imageId}
        onChange={(imageId) => update((current) => ({ ...current, imageId }))}
        hint="목록과 소개에 나오는 그림입니다."
      />
      <PlacesImages character={character} draft={draft} update={update} />
      <ItemsImages character={character} draft={draft} update={update} />
    </CharacterForm>
  );
}

type SectionProps = { character: AssetCharacterDetail; draft: ImagesDraft; update: Update };

function placeName(place: AssetPlace, index: number): string {
  return place.name.trim() || `장소 ${index + 1}`;
}

function PlacesImages({ character, draft, update }: SectionProps) {
  return (
    <fieldset className="scenario-choices">
      <legend>장소의 배경</legend>
      {character.places.length === 0 ? <p>저장한 장소가 없습니다. 지도 탭에서 먼저 더해 주세요.</p> : null}
      {character.places.map((place, index) => {
        const name = placeName(place, index);
        const images = placeImages(draft, character, place.id);
        return (
          <details key={place.id} className="scenario-opening">
            <summary>
              {name} <span className="hint">(시간대 배경 {Object.keys(images.backgrounds).length}개)</span>
            </summary>
            <ImagePicker
              label={`${name}의 기본 배경`}
              imageId={images.image_id}
              onChange={(imageId) => update((current) => setPlaceDefault(current, character, place.id, imageId))}
              hint="시간대의 배경이 없으면 이 그림을 씁니다."
            />
            {TIMES_OF_DAY.map((time) => (
              <ImagePicker
                key={time}
                label={`${name}의 ${timeLabel(time)} 배경`}
                imageId={images.backgrounds[time] ?? null}
                onChange={(imageId) => update((current) => setPlaceBackground(current, character, place.id, time, imageId))}
              />
            ))}
          </details>
        );
      })}
    </fieldset>
  );
}

function itemName(item: AssetItem, index: number): string {
  return item.name.trim() || `물건 ${index + 1}`;
}

function ItemsImages({ character, draft, update }: SectionProps) {
  return (
    <fieldset className="scenario-choices">
      <legend>물건의 그림</legend>
      {character.items.length === 0 ? <p>저장한 물건이 없습니다. 물건 탭에서 먼저 더해 주세요.</p> : null}
      {character.items.map((item, index) => (
        <ImagePicker
          key={item.id}
          label={`${itemName(item, index)}의 그림`}
          imageId={itemImage(draft, character, item.id)}
          onChange={(imageId) => update((current) => setItemImage(current, item.id, imageId))}
        />
      ))}
    </fieldset>
  );
}
