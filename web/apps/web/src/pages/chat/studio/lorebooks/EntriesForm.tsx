// web/apps/web/src/pages/chat/studio/lorebooks/EntriesForm.tsx
// 로어북의 항목 폼. 항목마다 이름, 종류, 키워드, 내용, 늘 넣기를 적고, 저장하면 목록을 통째로 보낸다.
// 늘 넣기면 대화마다 모델에 가고, 아니면 키워드가 최근 대화에 나올 때 간다.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { AssetLoreKind, AssetLorebookDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from '../characters/CharacterForm';
import { newKey } from '../characters/keys';
import {
  addEntry,
  changeEntry,
  ENTRIES_MAX,
  ENTRY_CONTENT_MAX,
  ENTRY_NAME_MAX,
  entriesHints,
  entryDrafts,
  LORE_KINDS,
  removeEntry,
  toEntriesBody,
  type EntryDraft,
} from './entriesForm';
import { useLorebookSave } from './useLorebookSave';

export function EntriesForm({ lorebook }: { lorebook: AssetLorebookDetail }) {
  const [entries, setEntries] = useState<EntryDraft[]>(() => entryDrafts(lorebook));
  const saving = useLorebookSave(lorebook.id);
  const hints = entriesHints(entries);

  async function submit() {
    const saved = await saving.save(toEntriesBody(entries));
    if (saved) setEntries(entryDrafts(saved));
  }

  function change(id: string, changes: Partial<Omit<EntryDraft, 'id'>>) {
    setEntries((current) => changeEntry(current, id, changes));
  }

  return (
    <CharacterForm
      label="항목"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <p className="hint">이름과 내용이 모델에 갑니다. 키워드가 최근 대화에 나오면 그 항목을 읽고, 늘 넣기면 대화마다 읽습니다.</p>
      {entries.length === 0 ? <p>아직 항목이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="항목">
        {entries.map((entry, index) => {
          const found = hints[entry.id] ?? {};
          const label = `항목 ${index + 1}`;
          return (
            <li key={entry.id} className="scenario-opening">
              <TextField
                label={`${label}의 이름`}
                maxLength={ENTRY_NAME_MAX}
                value={entry.name}
                onChange={(event) => change(entry.id, { name: event.target.value })}
                error={found.name}
              />
              <SelectField
                label={`${label}의 종류`}
                value={entry.kind}
                onChange={(event) => change(entry.id, { kind: event.target.value as AssetLoreKind })}
              >
                {Object.entries(LORE_KINDS).map(([kind, text]) => (
                  <option key={kind} value={kind}>
                    {text}
                  </option>
                ))}
              </SelectField>
              <TextField
                label={`${label}의 키워드(선택, 쉼표로 나눔)`}
                value={entry.keywords}
                onChange={(event) => change(entry.id, { keywords: event.target.value })}
                error={found.keywords}
              />
              <TextAreaField
                label={`${label}의 내용`}
                rows={4}
                maxLength={ENTRY_CONTENT_MAX}
                value={entry.content}
                onChange={(event) => change(entry.id, { content: event.target.value })}
                error={found.content}
                hint={`${entry.content.length} / ${ENTRY_CONTENT_MAX}자`}
              />
              <Checkbox
                label={`${label}을 늘 넣기`}
                description="키워드가 나오지 않아도 대화마다 모델이 읽습니다. 꼭 알아야 할 것만 켜세요."
                checked={entry.constant}
                onChange={(event) => change(entry.id, { constant: event.target.checked })}
              />
              <div className="form-actions">
                <Button variant="quiet" aria-label={`${label} 지우기`} onClick={() => setEntries((current) => removeEntry(current, entry.id))}>
                  지우기
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button
          variant="secondary"
          disabled={entries.length >= ENTRIES_MAX}
          onClick={() => setEntries((current) => addEntry(current, newKey('lore', current.map((entry) => entry.id))))}
        >
          항목 더하기
        </Button>{' '}
        <span className="hint">
          {entries.length} / {ENTRIES_MAX}
        </span>
      </p>
    </CharacterForm>
  );
}
