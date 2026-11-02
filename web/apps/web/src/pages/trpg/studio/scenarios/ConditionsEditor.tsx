// web/apps/web/src/pages/trpg/studio/scenarios/ConditionsEditor.tsx
// 조건의 목록을 고치는 칸(B9 퀘스트·사건 탭). 이루는 조건, 드러나는 조건, 실패하는 조건, 사건의 조건이 함께 쓴다.
// 줄마다 종류, 대상(장이면 시나리오의 장), 세는 종류면 개수, 가져가기를 쓰는 목록이면 가져가기. 목록 위에 모두/하나라도를 고른다. 검사는 conditionsForm.ts.
// 캠페인의 앞 편의 퀘스트(#481 B)는 그 종류를 고른 줄에서만 내 로어북들의 사건을 읽어 고른다(useEarlierQuests).

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import type { QuestConditionKind, QuestMatch } from '../../../../api/types';
import {
  CONDITION_MAX_COUNT,
  isCounted,
  isEarlierQuest,
  kindLabel,
  MAX_CONDITIONS,
  newCondition,
  targetKindOf,
  targetsOf,
  withKind,
  type ConditionDraft,
  type Targets,
} from './conditionsForm';
import { useEarlierQuests } from './useEarlierQuests';
import type { EntryChoice } from './useLoreEntries';

type Props = {
  /** 목록의 이름. "이루는 조건" */
  label: string;
  kinds: QuestConditionKind[];
  drafts: ConditionDraft[];
  onChange: (drafts: ConditionDraft[]) => void;
  match: QuestMatch;
  onMatch: (match: QuestMatch) => void;
  targets: Targets;
  hints: Record<number, string>;
  /** 물건 지니기에 가져가기를 두는가(퀘스트의 이루는 조건) */
  consume?: boolean;
};

type TargetProps = { draft: ConditionDraft; targets: Targets; onChange: (draft: ConditionDraft) => void };

type ChoiceProps = { label: string; value: string; choices: EntryChoice[]; onChange: (value: string) => void };

/** 고르는 칸 하나. 고른 것이 목록에 없으면(지웠다) "(찾을 수 없음)"으로 남긴다 */
function ChoiceSelect({ label, value, choices, onChange }: ChoiceProps) {
  return (
    <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      {value === '' ? <option value="">고르기</option> : null}
      {value !== '' && !choices.some((one) => one.id === value) ? <option value={value}>(찾을 수 없음)</option> : null}
      {choices.map((one) => (
        <option key={one.id} value={one.id}>
          {one.name}
        </option>
      ))}
    </SelectField>
  );
}

/** 대상을 고르는 칸. 장(chapter_at_least)은 대상 대신 시나리오의 장을 고른다 */
function TargetSelect({ draft, targets, onChange }: TargetProps) {
  const kind = targetKindOf(draft.kind);
  if (kind === null) {
    return <ChoiceSelect label="장" value={draft.chapter ?? ''} choices={targets.chapters ?? []} onChange={(chapter) => onChange({ ...draft, chapter })} />;
  }
  if (isEarlierQuest(draft.kind)) return <EarlierQuestSelect draft={draft} onChange={onChange} />;
  return <ChoiceSelect label="대상" value={draft.target} choices={targetsOf(targets, kind)} onChange={(target) => onChange({ ...draft, target })} />;
}

/** 캠페인의 앞 편의 퀘스트. 내 로어북들의 사건에서 고른다 */
function EarlierQuestSelect({ draft, onChange }: Omit<TargetProps, 'targets'>) {
  const earlier = useEarlierQuests(true);
  return (
    <div>
      {earlier.pending ? <p aria-busy="true">내 로어북의 사건을 불러오는 중</p> : null}
      {earlier.failed ? <p className="ui-field__error">내 로어북의 사건을 다 불러오지 못했습니다.</p> : null}
      <ChoiceSelect label="앞 편의 퀘스트" value={draft.target} choices={earlier.choices} onChange={(target) => onChange({ ...draft, target })} />
      <p className="hint">같은 캠페인의 앞 편 시나리오에서 퀘스트인 사건을 고르세요. 앞 편에 그 퀘스트가 있는지는 캠페인을 게시할 때 확인합니다.</p>
    </div>
  );
}

export function ConditionsEditor({ label, kinds, drafts, onChange, match, onMatch, targets, hints, consume = false }: Props) {
  const change = (index: number, draft: ConditionDraft) => onChange(drafts.map((one, at) => (at === index ? draft : one)));
  return (
    <div className="scenario-stacks">
      {drafts.length > 1 ? (
        <SelectField label={`${label}을 맞추는 법`} value={match} onChange={(event) => onMatch(event.target.value as QuestMatch)}>
          <option value="all">모두 채운다</option>
          <option value="any">하나라도 채운다</option>
        </SelectField>
      ) : null}
      {drafts.map((draft, index) => (
        <fieldset key={index} className="scenario-stack">
          <legend>
            {label} {index + 1}
          </legend>
          <div className="scenario-players__row">
            <SelectField label="종류" value={draft.kind} onChange={(event) => change(index, withKind(event.target.value as QuestConditionKind))}>
              {kinds.map((kind) => (
                <option key={kind} value={kind}>
                  {kindLabel(kind)}
                </option>
              ))}
            </SelectField>
            <TargetSelect draft={draft} targets={targets} onChange={(next) => change(index, next)} />
            {isCounted(draft.kind) ? (
              <TextField
                label={`개수(1~${CONDITION_MAX_COUNT})`}
                inputMode="numeric"
                value={draft.count}
                onChange={(event) => change(index, { ...draft, count: event.target.value })}
              />
            ) : null}
          </div>
          {consume && draft.kind === 'hold_item' ? (
            <Checkbox
              label="이룰 때 그 물건을 가져간다(배달)"
              checked={draft.consume}
              onChange={(event) => change(index, { ...draft, consume: event.target.checked })}
            />
          ) : null}
          {hints[index] ? <p className="ui-field__error">{hints[index]}</p> : null}
          <Button variant="quiet" aria-label={`${label} ${index + 1} 지우기`} onClick={() => onChange(drafts.filter((_, at) => at !== index))}>
            지우기
          </Button>
        </fieldset>
      ))}
      <p>
        <Button variant="secondary" disabled={drafts.length >= MAX_CONDITIONS} onClick={() => onChange([...drafts, newCondition(kinds)])}>
          {label} 더하기
        </Button>{' '}
        <span className="hint">
          {drafts.length} / {MAX_CONDITIONS}
        </span>
      </p>
    </div>
  );
}
