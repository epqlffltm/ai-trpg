// web/apps/web/src/pages/chat/studio/lorebooks/ChatLorebookEditPage.tsx
// 로어북 고치기(chat, /chat/studio/lorebooks/:lorebookId). 이름과 설명, 항목, 게시가 폼 하나씩이고 폼마다 저장한다.
// 캐릭터는 게시할 때 로어북의 마지막 판을 복사해 간다. 그래서 항목을 고치면 로어북을 게시한 뒤 캐릭터를 다시 게시해야 대화에 간다.

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useLocation, useParams } from 'react-router';
import type { AssetLorebookDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from '../characters/CharacterForm';
import { DeleteLorebookButton } from './DeleteLorebookButton';
import { EntriesForm } from './EntriesForm';
import { infoDraft, infoHints, LOREBOOK_DESCRIPTION_MAX, LOREBOOK_NAME_MAX, toInfoBody, type InfoDraft } from './lorebookForm';
import { LOREBOOKS_PATH } from './lorebookPaths';
import { isMissingLorebook } from './lorebookProblem';
import { lorebookQuery } from './lorebookQueries';
import { LorebookPublish } from './LorebookPublish';
import { useLorebookSave } from './useLorebookSave';

export function ChatLorebookEditPage() {
  const { lorebookId = '' } = useParams();
  const query = useQuery(lorebookQuery(lorebookId));
  return (
    <main className="page page--medium">
      <p>
        <Link to={LOREBOOKS_PATH}>내 로어북</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && isMissingLorebook(query.error) ? <Notice tone="error">로어북을 찾을 수 없습니다. 지워졌을 수 있습니다.</Notice> : null}
      {query.isError && !isMissingLorebook(query.error) ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.data ? <EditLorebook lorebook={query.data} /> : null}
    </main>
  );
}

function wasCreated(state: unknown): boolean {
  return state !== null && typeof state === 'object' && (state as Record<string, unknown>).created === true;
}

function EditLorebook({ lorebook }: { lorebook: AssetLorebookDetail }) {
  const location = useLocation();
  return (
    <>
      <h1>{lorebook.name}</h1>
      {wasCreated(location.state) ? <Notice>만들었습니다.</Notice> : null}
      <p className="hint">
        캐릭터는 게시할 때 이 로어북의 마지막 판을 복사해 갑니다. 항목을 고쳤으면 아래에서 게시한 뒤, 붙인 캐릭터도 다시 게시해야 대화에 들어갑니다.
      </p>
      <section className="page-section" aria-labelledby="lorebook-info-heading">
        <h2 id="lorebook-info-heading">이름과 설명</h2>
        <InfoForm lorebook={lorebook} />
      </section>
      <section className="page-section" aria-labelledby="lorebook-entries-heading">
        <h2 id="lorebook-entries-heading">항목</h2>
        <EntriesForm lorebook={lorebook} />
      </section>
      <section className="page-section" aria-labelledby="lorebook-publish-heading">
        <h2 id="lorebook-publish-heading">게시</h2>
        <LorebookPublish lorebook={lorebook} />
      </section>
    </>
  );
}

function InfoForm({ lorebook }: { lorebook: AssetLorebookDetail }) {
  const [draft, setDraft] = useState<InfoDraft>(() => infoDraft(lorebook));
  const saving = useLorebookSave(lorebook.id);
  const hints = infoHints(draft);

  async function submit() {
    const saved = await saving.save(toInfoBody(draft));
    if (saved) setDraft(infoDraft(saved));
  }

  return (
    <CharacterForm
      label="이름과 설명"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
      actions={<DeleteLorebookButton lorebookId={lorebook.id} name={lorebook.name} />}
    >
      <TextField
        label="이름"
        name="name"
        maxLength={LOREBOOK_NAME_MAX}
        value={draft.name}
        onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
        error={hints.name}
      />
      <TextAreaField
        label="설명(선택)"
        name="description"
        rows={3}
        maxLength={LOREBOOK_DESCRIPTION_MAX}
        value={draft.description}
        onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
        error={hints.description}
        hint="나만 보는 메모입니다. 모델에는 가지 않습니다."
      />
    </CharacterForm>
  );
}
