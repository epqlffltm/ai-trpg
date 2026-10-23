// web/apps/web/src/pages/trpg/studio/lorebooks/EntryForm.tsx
// 로어북 항목 하나의 입력(창 안). 더하기와 고치기가 함께 쓴다. 보내면 항목의 목록을 다시 읽고 창을 닫는다.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { addEntry, updateEntry } from '../../../../api/lorebooks';
import type { LoreEntry, LoreKind } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { useItemActions } from '../collection/useItemActions';
import {
  ENTRY_CONTENT_MAX,
  ENTRY_NAME_MAX,
  entryDraft,
  entryHints,
  LORE_KIND_HINTS,
  LORE_KINDS,
  newEntryDraft,
  toEntryBody,
  type EntryDraft,
} from './entryForm';

type Props = { lorebookId: string; entry: LoreEntry | null; done: () => void };

export function EntryForm({ lorebookId, entry, done }: Props) {
  const [draft, setDraft] = useState<EntryDraft>(() => (entry ? entryDraft(entry) : newEntryDraft()));
  const actions = useItemActions('lorebooks', lorebookId);
  const hints = entryHints(draft);

  function update(changes: Partial<EntryDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (Object.keys(hints).length > 0) return;
    const body = toEntryBody(draft);
    const sent = await actions.run(() => (entry ? updateEntry(lorebookId, entry.id, body) : addEntry(lorebookId, body)));
    if (sent) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="항목">
      <ProblemNotice problem={actions.problem} />
      <TextField
        label="이름"
        name="name"
        maxLength={ENTRY_NAME_MAX}
        value={draft.name}
        onChange={(event) => update({ name: event.target.value })}
        error={draft.name === '' ? undefined : hints.name}
      />
      <SelectField
        label="종류"
        name="kind"
        value={draft.kind}
        onChange={(event) => update({ kind: event.target.value as LoreKind })}
        hint={LORE_KIND_HINTS[draft.kind]}
      >
        {Object.entries(LORE_KINDS).map(([kind, label]) => (
          <option key={kind} value={kind}>
            {label}
          </option>
        ))}
      </SelectField>
      <div className="field-with-hint">
        <TextField
          label="키워드(선택, 쉼표로 나눔)"
          name="keywords"
          value={draft.keywords}
          onChange={(event) => update({ keywords: event.target.value })}
          error={hints.keywords}
        />
        <p className="ui-field__hint">서술하는 AI 가 장면에서 이 낱말을 보면 이 항목을 읽습니다. 5개까지입니다.</p>
      </div>
      <TextAreaField
        label="설명(선택)"
        name="content"
        rows={5}
        maxLength={ENTRY_CONTENT_MAX}
        value={draft.content}
        onChange={(event) => update({ content: event.target.value })}
        error={hints.content}
        hint={`${draft.content.length} / ${ENTRY_CONTENT_MAX}자`}
      />
      {draft.kind === 'person' ? (
        <div className="field-with-hint">
          <TextField
            label="지목할 때 맞는 이름(선택, 쉼표로 나눔)"
            name="true_names"
            value={draft.trueNames}
            onChange={(event) => update({ trueNames: event.target.value })}
            error={hints.true_names}
          />
          <p className="ui-field__hint">앉은 사람이 이 인물의 진짜 이름을 짚을 때 맞다고 받는 이름입니다. 비우면 위의 이름 하나입니다.</p>
        </div>
      ) : null}
      <div className="actions">
        <Button type="submit" busy={actions.busy} disabled={Object.keys(hints).length > 0}>
          {entry ? '저장' : '더하기'}
        </Button>
      </div>
    </form>
  );
}
