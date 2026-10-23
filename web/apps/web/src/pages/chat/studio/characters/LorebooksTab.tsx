// web/apps/web/src/pages/chat/studio/characters/LorebooksTab.tsx
// 캐릭터의 로어북 탭(C6). 내 로어북을 3 개까지 붙이고 차례를 정한다. 대화에서 키워드가 나오면 모델이 그 항목을 읽는다.
// 고르는 목록은 내 로어북의 최근 100 개다. 붙인 것마다 게시했는지 알린다(게시하지 않았거나 지워졌으면 캐릭터의 게시가 막힌다).
// 캐릭터를 게시할 때 로어북의 마지막 판을 복사하므로, 로어북을 고쳤으면 로어북과 캐릭터를 차례로 다시 게시해야 대화에 간다.

import { Button, Notice, SelectField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { AssetCharacterDetail } from '../../../../api/types';
import { lorebookPath, LOREBOOKS_PATH, NEW_LOREBOOK_PATH } from '../lorebooks/lorebookPaths';
import { lorebookPickerQuery } from '../lorebooks/lorebookQueries';
import { CharacterForm } from './CharacterForm';
import {
  attachedLorebooks,
  attachLorebook,
  detachLorebook,
  lorebookChoices,
  lorebookIds,
  LOREBOOKS_MAX,
  moveLorebookUp,
  toLorebooksBody,
  type AttachedLorebook,
} from './lorebooksForm';
import { useCharacterSave } from './useCharacterSave';

export function LorebooksTab({ character }: { character: AssetCharacterDetail }) {
  const [ids, setIds] = useState<string[]>(() => lorebookIds(character));
  const [choice, setChoice] = useState('');
  const picker = useQuery(lorebookPickerQuery());
  const saving = useCharacterSave(character.id);
  const mine = picker.data?.items ?? [];
  const choices = lorebookChoices(ids, mine);

  async function submit() {
    const saved = await saving.save(toLorebooksBody(ids));
    if (saved) setIds(lorebookIds(saved));
  }

  function attach() {
    setIds((current) => attachLorebook(current, choice));
    setChoice('');
  }

  return (
    <CharacterForm
      label="로어북"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={false}
      onSubmit={() => void submit()}
    >
      <p className="hint">
        대화에서 키워드가 나오면 모델이 붙인 로어북의 항목을 읽습니다. 위의 로어북부터 읽습니다. 캐릭터를 게시할 때 로어북마다 마지막으로 게시한 판이
        들어갑니다. <Link to={LOREBOOKS_PATH}>내 로어북</Link>
      </p>
      {picker.isError ? (
        <Notice tone="error">
          내 로어북을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void picker.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {ids.length === 0 ? <p>아직 붙인 로어북이 없습니다.</p> : null}
      <ol className="plain-list" aria-label="붙인 로어북">
        {attachedLorebooks(ids, mine).map((attached, index) => (
          <AttachedItem
            key={attached.id}
            attached={attached}
            index={index}
            known={picker.isSuccess}
            onUp={() => setIds((current) => moveLorebookUp(current, index))}
            onDetach={() => setIds((current) => detachLorebook(current, attached.id))}
          />
        ))}
      </ol>
      {picker.isSuccess && mine.length === 0 ? (
        <p>
          아직 만든 로어북이 없습니다. <Link to={NEW_LOREBOOK_PATH}>로어북 만들기</Link>
        </p>
      ) : null}
      {mine.length > 0 ? (
        <div className="scenario-choices">
          <SelectField label="붙일 로어북" value={choice} onChange={(event) => setChoice(event.target.value)} disabled={ids.length >= LOREBOOKS_MAX}>
            <option value="">고르지 않음</option>
            {choices.map((lorebook) => (
              <option key={lorebook.id} value={lorebook.id}>
                {lorebook.name}
              </option>
            ))}
          </SelectField>
          <Button variant="secondary" disabled={choice === '' || ids.length >= LOREBOOKS_MAX} onClick={attach}>
            붙이기
          </Button>{' '}
          <span className="hint">
            {ids.length} / {LOREBOOKS_MAX}
          </span>
        </div>
      ) : null}
    </CharacterForm>
  );
}

type ItemProps = { attached: AttachedLorebook; index: number; known: boolean; onUp: () => void; onDetach: () => void };

function AttachedItem({ attached, index, known, onUp, onDetach }: ItemProps) {
  const { summary } = attached;
  const label = summary?.name ?? `로어북 ${index + 1}`;
  return (
    <li className="scenario-opening">
      {summary ? <Link to={lorebookPath(attached.id)}>{summary.name}</Link> : <span>{label}</span>}{' '}
      <span className="hint">{statusText(attached, known)}</span>
      <div className="form-actions">
        <Button variant="quiet" aria-label={`${label}을(를) 앞으로`} disabled={index === 0} onClick={onUp}>
          앞으로
        </Button>
        <Button variant="quiet" aria-label={`${label} 떼기`} onClick={onDetach}>
          떼기
        </Button>
      </div>
    </li>
  );
}

function statusText({ summary }: AttachedLorebook, known: boolean): string {
  if (!known) return '';
  if (!summary) return '내 로어북 목록에 없습니다. 지워졌다면 떼어야 게시할 수 있습니다.';
  if (summary.latest_version === null) return `항목 ${summary.entry_count}개 · 아직 게시하지 않았습니다. 로어북을 게시해야 캐릭터를 게시할 수 있습니다.`;
  return `항목 ${summary.entry_count}개 · ${summary.latest_version}판까지 게시`;
}
