// web/apps/web/src/pages/story/studio/WorldProgressTab.tsx
// 세계관의 진행 탭(D7): 시간대(이름과 시작 시각), 시작 시간대, 기한, 엔딩 뒤, 보이기의 기본, 시작 장소, 시작 소지품.
// 시작 장소와 소지품은 지도·물건 탭에서 저장한 장소와 물건에서 고른다. 보이기의 기본은 인물마다 덮어쓴다(인물 탭).

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { StoryWorldDetail, StoryWorldShow } from '../../../api/storyWorlds';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { newKey } from '../../chat/studio/characters/keys';
import { useWorldSave } from './useWorldSave';
import {
  addSlot,
  addStartItem,
  changeSlot,
  changeStartItem,
  hasProgressHints,
  progressDraft,
  progressHints,
  removeSlot,
  removeStartItem,
  SLOT_NAME_MAX,
  SLOTS_MAX,
  SLOTS_MIN,
  START_ITEMS_MAX,
  toProgressBody,
  togglePanel,
  type AfterEnding,
  type ProgressDraft,
  type ProgressHints,
} from './worldProgressForm';
import { MAP_LABELS, PANEL_LABELS, REVEAL_LABELS, labelOr } from './worldLabels';

type Update = (change: (draft: ProgressDraft) => ProgressDraft) => void;

const AFTER_ENDING: Record<AfterEnding, string> = { end: '끝(엔딩을 보면 읽기만 한다)', epilogue: '후일담(엔딩 뒤에도 이어 간다)' };

export function WorldProgressTab({ world }: { world: StoryWorldDetail }) {
  const [draft, setDraft] = useState<ProgressDraft>(() => progressDraft(world));
  const saving = useWorldSave(world.id);
  const hints = progressHints(draft);
  const update: Update = (change) => setDraft(change);

  async function submit() {
    const saved = await saving.save(toProgressBody(draft, world));
    if (saved) setDraft(progressDraft(saved));
  }

  return (
    <StudioForm label="진행" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hasProgressHints(hints)} onSubmit={() => void submit()}>
      <SlotsSection draft={draft} hints={hints} update={update} />
      <SelectField label="시작 시간대" value={draft.startSlot} onChange={(event) => update((current) => ({ ...current, startSlot: event.target.value }))} hint="비우면 첫 시간대에서 시작합니다.">
        <option value="">첫 시간대</option>
        {draft.slots.map((slot, index) => (
          <option key={slot.id} value={slot.id}>
            {labelOr(slot.name, `시간대 ${index + 1}`)}
          </option>
        ))}
      </SelectField>
      <TextField
        label="기한(날 수, 비우면 없음)"
        inputMode="numeric"
        value={draft.deadline}
        onChange={(event) => update((current) => ({ ...current, deadline: event.target.value }))}
        error={hints.deadline}
      />
      <p className="hint">기한이 지나면 기한의 엔딩을 고릅니다. 마지막 날이 D-0 입니다.</p>
      <SelectField label="엔딩 뒤" value={draft.afterEnding} onChange={(event) => update((current) => ({ ...current, afterEnding: event.target.value as AfterEnding }))}>
        {Object.entries(AFTER_ENDING).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </SelectField>
      <ShowSection show={draft.show} onChange={(show) => update((current) => ({ ...current, show }))} />
      <StartSection world={world} draft={draft} hints={hints} update={update} />
    </StudioForm>
  );
}

function SlotsSection({ draft, hints, update }: { draft: ProgressDraft; hints: ProgressHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>시간대</legend>
      <p className="hint">하루를 나눈 때입니다. 시작 시각이 차례로 커지고, 마지막 시간대는 자정을 넘어 첫 시간대까지 이어집니다. 장소의 시간대 배경과 인물의 일정이 이것을 씁니다.</p>
      <ol className="plain-list" aria-label="시간대">
        {draft.slots.map((slot, index) => (
          <li key={slot.id} className="scenario-opening">
            <TextField
              label={`시간대 ${index + 1}의 이름`}
              maxLength={SLOT_NAME_MAX}
              value={slot.name}
              onChange={(event) => update((current) => changeSlot(current, slot.id, { name: event.target.value }))}
              error={hints.slots[slot.id]?.name}
            />
            <TextField
              label={`시간대 ${index + 1}의 시작 시각(시)`}
              inputMode="numeric"
              value={slot.startHour}
              onChange={(event) => update((current) => changeSlot(current, slot.id, { startHour: event.target.value }))}
              error={hints.slots[slot.id]?.startHour}
            />
            <div className="form-actions">
              <Button variant="quiet" aria-label={`시간대 ${index + 1} 지우기`} disabled={draft.slots.length <= SLOTS_MIN} onClick={() => update((current) => removeSlot(current, slot.id))}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={draft.slots.length >= SLOTS_MAX} onClick={() => update((current) => addSlot(current, newKey('slot', current.slots.map((slot) => slot.id))))}>
          시간대 더하기
        </Button>{' '}
        <span className="hint">
          {draft.slots.length} / {SLOTS_MAX}
        </span>
      </p>
    </fieldset>
  );
}

function ShowSection({ show, onChange }: { show: StoryWorldShow; onChange: (show: StoryWorldShow) => void }) {
  return (
    <fieldset className="scenario-choices">
      <legend>보이기의 기본</legend>
      <p className="hint">인물마다 덮어쓸 수 있습니다.</p>
      <SelectField label="인물의 공개" value={show.reveal} onChange={(event) => onChange({ ...show, reveal: event.target.value as StoryWorldShow['reveal'] })} hint="실루엣은 만나기 전까지 이름과 그림을 가리고, 숨김은 만나기 전까지 목록에 없습니다.">
        {Object.entries(REVEAL_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </SelectField>
      <SelectField label="지도의 인물" value={show.map} onChange={(event) => onChange({ ...show, map: event.target.value as StoryWorldShow['map'] })} hint="가 본 장소에 만난 인물이 있으면 지도에 보일지입니다. 단계는 인물마다 정합니다.">
        {Object.entries(MAP_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </SelectField>
      <p>인물 창의 항목</p>
      {Object.entries(PANEL_LABELS).map(([field, label]) => (
        <Checkbox
          key={field}
          label={label}
          checked={show.panel.includes(field as StoryWorldShow['panel'][number])}
          onChange={() => onChange(togglePanel(show, field as StoryWorldShow['panel'][number]))}
        />
      ))}
    </fieldset>
  );
}

function StartSection({ world, draft, hints, update }: { world: StoryWorldDetail; draft: ProgressDraft; hints: ProgressHints; update: Update }) {
  return (
    <fieldset className="scenario-choices">
      <legend>시작</legend>
      <SelectField
        label="시작 장소"
        value={draft.startPlace}
        onChange={(event) => update((current) => ({ ...current, startPlace: event.target.value }))}
        hint={world.places.length === 0 ? '지도 탭에서 장소를 먼저 저장해 주세요. 시작 장소가 있어야 게시합니다.' : '시작 장소가 있어야 게시합니다.'}
      >
        <option value="">고르지 않음</option>
        {world.places.map((place, index) => (
          <option key={place.id} value={place.id}>
            {labelOr(place.name, `장소 ${index + 1}`)}
          </option>
        ))}
      </SelectField>
      <p>시작 소지품</p>
      {world.items.length === 0 ? <p className="hint">물건 탭에서 물건을 먼저 저장해 주세요.</p> : null}
      <ol className="plain-list" aria-label="시작 소지품">
        {draft.startItems.map((start, index) => (
          <li key={index} className="scenario-opening">
            <SelectField label={`소지품 ${index + 1}의 물건`} value={start.item} onChange={(event) => update((current) => changeStartItem(current, index, { item: event.target.value }))}>
              <option value="">고르지 않음</option>
              {world.items.map((item, at) => (
                <option key={item.id} value={item.id}>
                  {labelOr(item.name, `물건 ${at + 1}`)}
                </option>
              ))}
            </SelectField>
            <TextField
              label={`소지품 ${index + 1}의 수`}
              inputMode="numeric"
              value={start.count}
              onChange={(event) => update((current) => changeStartItem(current, index, { count: event.target.value }))}
              error={hints.startItems[index]}
            />
            <div className="form-actions">
              <Button variant="quiet" aria-label={`소지품 ${index + 1} 지우기`} onClick={() => update((current) => removeStartItem(current, index))}>
                지우기
              </Button>
            </div>
          </li>
        ))}
      </ol>
      <p>
        <Button variant="secondary" disabled={world.items.length === 0 || draft.startItems.length >= START_ITEMS_MAX} onClick={() => update(addStartItem)}>
          소지품 더하기
        </Button>
      </p>
    </fieldset>
  );
}
