// web/apps/web/src/pages/chat/studio/characters/ItemsTab.tsx
// 캐릭터의 물건 탭(C6): 물건(이름, 설명, 옷인지, 쓰면 없어지는지, 상대가 줄 수 있는지)과 사용자의 시작 소지품.
// 사용자는 대화에서 물건을 쓰거나 건넨다. 옷을 건네면 상대의 차림에 들어간다. 물건의 그림은 그림 탭에서 붙인다.
// 물건을 지우면 그 물건의 시작 소지품도 지운다(itemsForm.ts).

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetCharacterDetail, AssetItem, AssetItemKind } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from './CharacterForm';
import {
  addItem,
  addStartItem,
  changeItem,
  changeStartItem,
  hasItemsHints,
  isStartItem,
  ITEM_DESCRIPTION_MAX,
  ITEM_NAME_MAX,
  ITEMS_MAX,
  itemsDraft,
  itemsHints,
  removeItem,
  removeStartItem,
  START_ITEMS_MAX,
  toItemsBody,
  type ItemsDraft,
  type ItemsHints,
} from './itemsForm';
import { newKey } from './keys';
import { useCharacterSave } from './useCharacterSave';

const KINDS: Record<AssetItemKind, string> = { thing: '물건', clothing: '옷(건네면 상대가 입는다)' };

type Update = (change: (draft: ItemsDraft) => ItemsDraft) => void;

export function ItemsTab({ character }: { character: AssetCharacterDetail }) {
  const [draft, setDraft] = useState<ItemsDraft>(() => itemsDraft(character));
  const saving = useCharacterSave(character.id);
  const hints = itemsHints(draft);
  const update: Update = (change) => setDraft(change);

  async function submit() {
    const saved = await saving.save(toItemsBody(draft));
    if (saved) setDraft(itemsDraft(saved));
  }

  return (
    <CharacterForm
      label="물건"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={hasItemsHints(hints)}
      onSubmit={() => void submit()}
    >
      <p className="hint">대화에서 쓰거나 건넬 수 있는 물건입니다. 호감도의 규칙과 이벤트 씬이 이 물건을 가리킬 수 있습니다.</p>
      <ItemsSection draft={draft} hints={hints} update={update} />
      <StartItemsSection draft={draft} hints={hints} update={update} />
    </CharacterForm>
  );
}

function itemName(item: AssetItem, index: number): string {
  return item.name.trim() || `물건 ${index + 1}`;
}

function ItemsSection({ draft, hints, update }: { draft: ItemsDraft; hints: ItemsHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>물건</legend>
      {draft.items.length === 0 ? <p>아직 물건이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="물건">
        {draft.items.map((item, index) => (
          <li key={item.id} className="scenario-opening">
            <TextField
              label={`물건 ${index + 1}의 이름`}
              maxLength={ITEM_NAME_MAX}
              value={item.name}
              onChange={(event) => update((current) => changeItem(current, item.id, { name: event.target.value }))}
              error={hints.items[item.id]?.name}
            />
            <TextAreaField
              label={`물건 ${index + 1}의 설명(선택)`}
              rows={2}
              maxLength={ITEM_DESCRIPTION_MAX}
              value={item.description ?? ''}
              onChange={(event) => update((current) => changeItem(current, item.id, { description: event.target.value }))}
              error={hints.items[item.id]?.description}
            />
            <SelectField
              label={`물건 ${index + 1}의 종류`}
              value={item.kind ?? 'thing'}
              onChange={(event) => update((current) => changeItem(current, item.id, { kind: event.target.value as AssetItemKind }))}
            >
              {Object.entries(KINDS).map(([kind, label]) => (
                <option key={kind} value={kind}>
                  {label}
                </option>
              ))}
            </SelectField>
            <Checkbox
              label="쓰면 하나 없어진다"
              checked={item.consumable ?? false}
              onChange={(event) => update((current) => changeItem(current, item.id, { consumable: event.target.checked }))}
            />
            <Checkbox
              label="상대가 사용자에게 줄 수 있다"
              description="참이면 대화의 모델이 이 물건을 선물로 제안할 수 있습니다."
              checked={item.giftable ?? false}
              onChange={(event) => update((current) => changeItem(current, item.id, { giftable: event.target.checked }))}
            />
            <div className="form-actions">
              <Button variant="quiet" aria-label={`물건 ${index + 1} 지우기`} onClick={() => update((current) => removeItem(current, item.id))}>
                지우기
              </Button>
              {isStartItem(draft, item.id) ? <span className="hint">시작 소지품에서도 함께 지웁니다.</span> : null}
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.items.length >= ITEMS_MAX} onClick={() => update((current) => addItem(current, newKey('item', current.items.map((item) => item.id))))}>
          물건 더하기
        </Button>{' '}
        <span className="hint">
          {draft.items.length} / {ITEMS_MAX}
        </span>
      </p>
    </fieldset>
  );
}

function StartItemsSection({ draft, hints, update }: { draft: ItemsDraft; hints: ItemsHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>시작 소지품</legend>
      <p className="hint">사용자가 대화를 시작할 때 가진 물건과 그 수입니다.</p>
      {draft.startItems.length === 0 ? <p>시작 소지품이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="시작 소지품">
        {draft.startItems.map((start, index) => (
          <li key={index} className="scenario-opening">
            <SelectField
              label={`시작 소지품 ${index + 1}의 물건`}
              value={start.item}
              onChange={(event) => update((current) => changeStartItem(current, index, { item: event.target.value }))}
            >
              <option value="">고르지 않음</option>
              {draft.items.map((item, at) => (
                <option key={item.id} value={item.id}>
                  {itemName(item, at)}
                </option>
              ))}
            </SelectField>
            <TextField
              label={`시작 소지품 ${index + 1}의 수`}
              inputMode="numeric"
              value={start.count}
              onChange={(event) => update((current) => changeStartItem(current, index, { count: event.target.value }))}
              error={hints.startItems[index]}
            />
            <div className="form-actions">
              <Button variant="quiet" aria-label={`시작 소지품 ${index + 1} 지우기`} onClick={() => update((current) => removeStartItem(current, index))}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.items.length === 0 || draft.startItems.length >= START_ITEMS_MAX} onClick={() => update(addStartItem)}>
          시작 소지품 더하기
        </Button>{' '}
        <span className="hint">{draft.items.length === 0 ? '물건을 먼저 더해 주세요.' : `${draft.startItems.length} / ${START_ITEMS_MAX}`}</span>
      </p>
    </fieldset>
  );
}
