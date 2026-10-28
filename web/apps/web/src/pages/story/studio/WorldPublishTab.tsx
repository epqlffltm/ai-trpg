// web/apps/web/src/pages/story/studio/WorldPublishTab.tsx
// 세계관의 게시 탭(D7). 지금 저장된 초안을 새 판으로 굳히고(바뀐 것 500 자), 낸 판의 목록을 보인다.
// 게시 점검에 문제가 있으면 게시를 끈다(서버도 409 로 막는다). 게시한 뒤에 알리는 것(warnings)과 소개에서 걸러 낸 것을 보인다.
// 이미 시작한 세션은 그때의 판을 그대로 쓴다. 새로 시작하는 세션부터 새 판이다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import type { StoryWorldDetail, StoryWorldPublished } from '../../../api/storyWorlds';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { TextAreaField } from '../../../components/TextAreaField';
import { formatDate } from '../../../format/dateTime';
import { removedLine } from '../../chat/studio/characters/removedHtml';
import { useWorldPublish } from './useWorldPublish';
import { worldWarningText } from './worldPublishText';
import { worldCheckQuery, worldVersionsQuery } from './worldQueries';

export const NOTE_MAX = 500;

export function WorldPublishTab({ world }: { world: StoryWorldDetail }) {
  const check = useQuery(worldCheckQuery(world.id));
  const publishing = useWorldPublish(world.id);
  const [note, setNote] = useState('');
  const [published, setPublished] = useState<StoryWorldPublished | null>(null);
  const blocked = check.data?.ready === false || note.length > NOTE_MAX;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    setPublished(null);
    const result = await publishing.publish(note);
    if (!result) return;
    setPublished(result);
    setNote('');
  }

  return (
    <>
      <form onSubmit={(event) => void submit(event)} noValidate aria-label="게시">
        <p className="hint">지금 저장된 내용이 새 판으로 굳습니다. 저장하지 않은 고침은 들어가지 않습니다. 이미 시작한 세션은 그 세션의 판을 그대로 씁니다.</p>
        {published ? <Published worldId={world.id} result={published} /> : null}
        <ProblemNotice problem={publishing.problem} />
        <TextAreaField
          label="바뀐 것(선택)"
          name="note"
          rows={3}
          maxLength={NOTE_MAX}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          error={note.length > NOTE_MAX ? `${NOTE_MAX}자까지입니다.` : undefined}
          hint={`${note.length} / ${NOTE_MAX}자. 아래 판의 목록에 남습니다.`}
        />
        <div className="form-actions">
          <Button type="submit" busy={publishing.busy} disabled={blocked}>
            게시
          </Button>
          {check.data?.ready === false ? <span className="hint">게시 점검의 문제를 먼저 고쳐 주세요.</span> : null}
        </div>
      </form>
      <Versions worldId={world.id} />
    </>
  );
}

function Published({ worldId, result }: { worldId: string; result: StoryWorldPublished }) {
  return (
    <Notice>
      {result.number}판을 게시했습니다. <Link to={`/story/worlds/${worldId}`}>소개 보기</Link>
      {result.removed.length > 0 ? <> 소개에서 {result.removed.length}개를 걸러 냈습니다: {result.removed.map(removedLine).join(', ')}.</> : null}
      {result.warnings.length > 0 ? (
        <ul className="plain-list" aria-label="알리는 것">
          {result.warnings.map((name) => (
            <li key={name}>{worldWarningText(name)}</li>
          ))}
        </ul>
      ) : null}
    </Notice>
  );
}

function Versions({ worldId }: { worldId: string }) {
  const versions = useQuery(worldVersionsQuery(worldId));
  return (
    <section className="page-section" aria-labelledby="world-versions-heading">
      <h2 id="world-versions-heading">낸 판</h2>
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
    </section>
  );
}
