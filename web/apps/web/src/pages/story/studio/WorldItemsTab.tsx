// web/apps/web/src/pages/story/studio/WorldItemsTab.tsx
// 세계관의 물건 탭(D7): 물건(이름, 설명, 쓰면 없어지는가, 그림). 시작 소지품은 진행 탭, 건넸을 때의 호감도는 인물의 선물 규칙이다.
// 물건을 지우면 그 물건의 시작 소지품도 지운다(worldItemsForm.ts).

import { Button, Checkbox, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { StoryWorldDetail, StoryWorldItem } from '../../../api/storyWorlds';
import { ImagePicker } from '../../../components/ImagePicker';
import { TextAreaField } from '../../../components/TextAreaField';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import { useWorldSave } from './useWorldSave';
import { labelOr } from './worldLabels';
import {
  addWorldItem,
  changeWorldItem,
  ITEM_DESCRIPTION_MAX,
  ITEM_NAME_MAX,
  removeWorldItem,
  toWorldItemsBody,
  WORLD_ITEMS_MAX,
  worldItemsHints,
} from './worldItemsForm';

export function WorldItemsTab({ world }: { world: StoryWorldDetail }) {
  const [items, setItems] = useState<StoryWorldItem[]>(() => world.items);
  const saving = useWorldSave(world.id);
  const hints = worldItemsHints(items);

  async function submit() {
    const saved = await saving.save(toWorldItemsBody(items, world));
    if (saved) setItems(saved.items);
  }

  return (
    <StudioForm label="물건" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={Object.keys(hints).length > 0} onSubmit={() => void submit()}>
      <p className="hint">사용자가 가지고 다니며 인물에게 건네는 물건입니다. 시작 소지품은 진행 탭에서, 건넸을 때 호감도가 어떻게 바뀌는지는 인물마다 정합니다.</p>
      {items.length === 0 ? <p>아직 물건이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="물건">
        {items.map((item, index) => {
          const name = labelOr(item.name, `물건 ${index + 1}`);
          const started = world.start_items.some((start) => start.item === item.id);
          return (
            <li key={item.id} className="scenario-opening">
              <TextField
                label={`물건 ${index + 1}의 이름`}
                maxLength={ITEM_NAME_MAX}
                value={item.name}
                onChange={(event) => setItems((current) => changeWorldItem(current, item.id, { name: event.target.value }))}
                error={hints[item.id]?.name}
              />
              <TextAreaField
                label={`물건 ${index + 1}의 설명(선택)`}
                rows={2}
                maxLength={ITEM_DESCRIPTION_MAX}
                value={item.description}
                onChange={(event) => setItems((current) => changeWorldItem(current, item.id, { description: event.target.value }))}
                error={hints[item.id]?.description}
              />
              <Checkbox label="쓰면 하나 없어진다" checked={item.consumable} onChange={(event) => setItems((current) => changeWorldItem(current, item.id, { consumable: event.target.checked }))} />
              <ImagePicker label={`${name}의 그림`} imageId={item.image_id ?? null} onChange={(imageId) => setItems((current) => changeWorldItem(current, item.id, { image_id: imageId }))} />
              <div className="form-actions">
                <Button variant="quiet" aria-label={`물건 ${index + 1} 지우기`} onClick={() => setItems((current) => removeWorldItem(current, item.id))}>
                  지우기
                </Button>
                {started ? <span className="hint">시작 소지품에서도 빠집니다.</span> : null}
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button variant="secondary" disabled={items.length >= WORLD_ITEMS_MAX} onClick={() => setItems((current) => addWorldItem(current, newKey('item', current.map((item) => item.id))))}>
          물건 더하기
        </Button>{' '}
        <span className="hint">
          {items.length} / {WORLD_ITEMS_MAX}
        </span>
      </p>
    </StudioForm>
  );
}
