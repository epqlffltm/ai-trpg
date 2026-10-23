// web/apps/web/src/pages/chat/studio/lorebooks/LorebookPublish.tsx
// 로어북의 게시. 지금 저장된 초안을 새 판으로 굳히고(바뀐 것 500 자), 낸 판의 목록을 보인다. 막는 것은 없다(항목이 없어도 된다).
// 게시해도 붙인 캐릭터의 판은 그대로다. 캐릭터를 다시 게시하면 이 판을 복사해 간다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import type { AssetLorebookDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { TextAreaField } from '../../../../components/TextAreaField';
import { formatDate } from '../../../../format/dateTime';
import { NOTE_MAX } from '../characters/PublishTab';
import { lorebookVersionsQuery } from './lorebookQueries';
import { useLorebookPublish } from './useLorebookPublish';

export function LorebookPublish({ lorebook }: { lorebook: AssetLorebookDetail }) {
  const publishing = useLorebookPublish(lorebook.id);
  const [note, setNote] = useState('');
  const [published, setPublished] = useState<number | null>(null);
  const blocked = note.length > NOTE_MAX;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    setPublished(null);
    const result = await publishing.publish(note);
    if (!result) return;
    setPublished(result.number);
    setNote('');
  }

  return (
    <>
      <form onSubmit={(event) => void submit(event)} noValidate aria-label="게시">
        <p className="hint">지금 저장된 내용이 새 판으로 굳습니다. 저장하지 않은 고침은 들어가지 않습니다.</p>
        {published !== null ? <Notice>{published}판을 게시했습니다. 붙인 캐릭터를 다시 게시하면 이 판이 들어갑니다.</Notice> : null}
        <ProblemNotice problem={publishing.problem} />
        <TextAreaField
          label="바뀐 것(선택)"
          name="note"
          rows={3}
          maxLength={NOTE_MAX}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          error={blocked ? `${NOTE_MAX}자까지입니다.` : undefined}
          hint={`${note.length} / ${NOTE_MAX}자. 아래 판의 목록에 남습니다.`}
        />
        <div className="form-actions">
          <Button type="submit" busy={publishing.busy} disabled={blocked}>
            게시
          </Button>
        </div>
      </form>
      <Versions lorebookId={lorebook.id} />
    </>
  );
}

function Versions({ lorebookId }: { lorebookId: string }) {
  const versions = useQuery(lorebookVersionsQuery(lorebookId));
  return (
    <>
      <h3>낸 판</h3>
      {versions.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {versions.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void versions.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {versions.isSuccess && versions.data.length === 0 ? <p>아직 낸 판이 없습니다.</p> : null}
      <ul className="plain-list studio-list" aria-label="판">
        {(versions.data ?? []).map((version) => (
          <li key={version.id} className="studio-list__item">
            <strong>{version.number}판</strong> <span className="hint">{formatDate(version.created_at)}</span>
            {version.note ? <p className="studio-list__description">{version.note}</p> : null}
          </li>
        ))}
      </ul>
    </>
  );
}
