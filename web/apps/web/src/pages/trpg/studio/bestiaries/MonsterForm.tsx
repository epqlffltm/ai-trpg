// web/apps/web/src/pages/trpg/studio/bestiaries/MonsterForm.tsx
// 몬스터 하나의 입력(창 안). 더하기와 고치기가 함께 쓴다. 보내면 몬스터의 목록을 다시 읽고 창을 닫는다.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { addMonster, updateMonster } from '../../../../api/bestiaries';
import type { Monster, MonsterKind } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { useItemActions } from '../collection/useItemActions';
import {
  MONSTER_CONTENT_MAX,
  MONSTER_KINDS,
  MONSTER_NAME_MAX,
  monsterDraft,
  monsterHints,
  newMonsterDraft,
  toMonsterBody,
  type MonsterDraft,
} from './monsterForm';

type Props = { bestiaryId: string; monster: Monster | null; done: () => void };

export function MonsterForm({ bestiaryId, monster, done }: Props) {
  const [draft, setDraft] = useState<MonsterDraft>(() => (monster ? monsterDraft(monster) : newMonsterDraft()));
  const actions = useItemActions('bestiaries', bestiaryId);
  const hints = monsterHints(draft);

  function update(changes: Partial<MonsterDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Object.keys(hints).length > 0) return;
    const body = toMonsterBody(draft);
    const sent = await actions.run(() => (monster ? updateMonster(bestiaryId, monster.id, body) : addMonster(bestiaryId, body)));
    if (sent) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="몬스터">
      <ProblemNotice problem={actions.problem} />
      <TextField
        label="이름"
        name="name"
        maxLength={MONSTER_NAME_MAX}
        value={draft.name}
        onChange={(event) => update({ name: event.target.value })}
        error={draft.name === '' ? undefined : hints.name}
      />
      <SelectField label="종류" name="kind" value={draft.kind} onChange={(event) => update({ kind: event.target.value as MonsterKind })}>
        {Object.entries(MONSTER_KINDS).map(([kind, label]) => (
          <option key={kind} value={kind}>
            {label}
          </option>
        ))}
      </SelectField>
      <TextAreaField
        label="설명(선택)"
        name="content"
        rows={5}
        maxLength={MONSTER_CONTENT_MAX}
        value={draft.content}
        onChange={(event) => update({ content: event.target.value })}
        error={hints.content}
        hint={`서술하는 AI 가 읽는 생김새와 버릇입니다. ${draft.content.length} / ${MONSTER_CONTENT_MAX}자`}
      />
      <Checkbox
        label="네임드"
        description="판 전체에 한 마리만 둡니다. 두 조우에 함께 놓을 수 없습니다."
        checked={draft.unique}
        onChange={(event) => update({ unique: event.target.checked })}
      />
      <div className="actions">
        <Button type="submit" busy={actions.busy} disabled={Object.keys(hints).length > 0}>
          {monster ? '저장' : '더하기'}
        </Button>
      </div>
    </form>
  );
}
