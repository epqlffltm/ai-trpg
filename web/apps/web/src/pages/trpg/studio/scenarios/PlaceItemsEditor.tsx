// web/apps/web/src/pages/trpg/studio/scenarios/PlaceItemsEditor.tsx
// 장소에 놓인 물건의 줄들(B9 지도, #279). 장소의 창 안에서 쓴다. 줄마다 물건, 개수, 보이는가, 숨겼으면 찾는 판정.
// 보이는 물건은 그 장소에 서 본 뒤 줍기로 가져가고, 숨긴 물건은 찾은 사람이 바로 갖는다. 검사는 placesForm.ts.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import type { PlaceItemVisibility, Ruleset } from '../../../../api/types';
import { CheckSelects } from './CheckSelects';
import { MAX_PLACE_ITEMS, newPlaceItem, type PlaceItemDraft } from './placesForm';
import { STACK_MAX } from './stacksForm';
import type { EntryChoice } from './useLoreEntries';

const VISIBILITIES: Record<PlaceItemVisibility, string> = { open: '보임(서 보면 앎)', hidden: '숨김(찾아야 앎)' };

type Props = {
  drafts: PlaceItemDraft[];
  onChange: (drafts: PlaceItemDraft[]) => void;
  entries: EntryChoice[];
  rules: Ruleset | null;
  hints: Record<string, string>;
  /** 이 시나리오의 놓인 물건이 모두 몇 줄인가(이 장소 것 말고). 100 줄까지다 */
  others: number;
};

export function PlaceItemsEditor({ drafts, onChange, entries, rules, hints, others }: Props) {
  const change = (index: number, changes: Partial<PlaceItemDraft>) => onChange(drafts.map((one, at) => (at === index ? { ...one, ...changes } : one)));
  const full = others + drafts.length >= MAX_PLACE_ITEMS;
  return (
    <div className="scenario-stacks">
      {drafts.length === 0 ? <p className="hint">놓인 물건이 없습니다.</p> : null}
      {drafts.map((draft, index) => (
        <fieldset key={index} className="scenario-stack">
          <legend>놓인 물건 {index + 1}</legend>
          <div className="scenario-players__row">
            <SelectField label="물건" value={draft.entryId} onChange={(event) => change(index, { entryId: event.target.value })}>
              {draft.entryId === '' ? <option value="">고르기</option> : null}
              {draft.entryId !== '' && !entries.some((entry) => entry.id === draft.entryId) ? <option value={draft.entryId}>(붙인 로어북에 없는 물건)</option> : null}
              {entries.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name}
                </option>
              ))}
            </SelectField>
            <TextField label={`개수(1~${STACK_MAX})`} inputMode="numeric" value={draft.count} onChange={(event) => change(index, { count: event.target.value })} />
            <SelectField label="보이는가" value={draft.visibility} onChange={(event) => change(index, { visibility: event.target.value as PlaceItemVisibility })}>
              {Object.entries(VISIBILITIES).map(([visibility, label]) => (
                <option key={visibility} value={visibility}>
                  {label}
                </option>
              ))}
            </SelectField>
          </div>
          {draft.visibility === 'hidden' ? (
            <CheckSelects
              label="찾는 판정"
              rules={rules}
              ability={draft.findAbility}
              difficulty={draft.findDifficulty}
              onChange={(changes) =>
                change(index, {
                  ...(changes.ability !== undefined ? { findAbility: changes.ability } : {}),
                  ...(changes.difficulty !== undefined ? { findDifficulty: changes.difficulty } : {}),
                })
              }
            />
          ) : null}
          {hints[`item.${index}`] ? <p className="ui-field__error">{hints[`item.${index}`]}</p> : null}
          <Button variant="quiet" aria-label={`놓인 물건 ${index + 1} 지우기`} onClick={() => onChange(drafts.filter((_, at) => at !== index))}>
            지우기
          </Button>
        </fieldset>
      ))}
      <p>
        <Button
          variant="secondary"
          disabled={full || entries.length === 0}
          onClick={() =>
            onChange([
              ...drafts,
              newPlaceItem(
                drafts,
                entries.map((entry) => entry.id),
              ),
            ])
          }
        >
          놓인 물건 더하기
        </Button>
      </p>
    </div>
  );
}
