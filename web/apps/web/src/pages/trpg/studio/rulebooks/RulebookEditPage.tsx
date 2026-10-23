// web/apps/web/src/pages/trpg/studio/rulebooks/RulebookEditPage.tsx
// 룰북 고치기(B9, /trpg/studio/rulebooks/:rulebookId). 제목, 소개, 진행 지침, 방어 규칙을 고치고 지운다.
// 템플릿은 보이기만 한다. 이미 게시한 판은 게시할 때의 규칙으로 굳어 있어 여기서 고쳐도 바뀌지 않는다고 알린다.
// 남의 것이거나 없으면 404 라 목록으로 돌아가는 길만 둔다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { ApiError } from '../../../../api/errors';
import type { RulebookDetail } from '../../../../api/types';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { rulebookDraft, type RulebookDraft } from './rulebookForm';
import { rulebookQuery, rulebookTemplatesQuery } from './rulebookQueries';
import { RulebookEditor } from './RulebookEditor';
import { templateName } from './rulebookView';
import { useDeleteRulebook, useUpdateRulebook } from './useRulebookActions';

export function RulebookEditPage() {
  const { rulebookId = '' } = useParams();
  const query = useQuery(rulebookQuery(rulebookId));
  return (
    <main className="page page--medium">
      <p>
        <Link to="/trpg/studio/rulebooks">내 룰북</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? <LoadFailed error={query.error} retry={() => void query.refetch()} /> : null}
      {query.data ? <EditRulebook rulebook={query.data} /> : null}
    </main>
  );
}

function LoadFailed({ error, retry }: { error: unknown; retry: () => void }) {
  if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
    return <Notice>룰북을 찾을 수 없습니다. 지워졌을 수 있습니다.</Notice>;
  }
  return (
    <Notice tone="error">
      룰북을 불러오지 못했습니다.{' '}
      <Button variant="quiet" onClick={retry}>
        다시 시도
      </Button>
    </Notice>
  );
}

function EditRulebook({ rulebook }: { rulebook: RulebookDetail }) {
  const templates = useQuery(rulebookTemplatesQuery());
  const updating = useUpdateRulebook(rulebook.id);
  const location = useLocation();
  const [notice, setNotice] = useState<string | null>(created(location.state) ? '만들었습니다.' : null);

  async function submit(draft: RulebookDraft) {
    setNotice(null);
    if (await updating.update(draft)) setNotice('저장했습니다.');
  }

  return (
    <>
      <h1>{rulebook.title}</h1>
      <p className="hint">
        템플릿: {templateName(templates.data, rulebook.rules.template)}. 만든 뒤에는 바꿀 수 없습니다.
      </p>
      <Notice>이미 게시한 시나리오의 판은 게시할 때의 규칙으로 굳어 있어, 여기서 고쳐도 바뀌지 않습니다. 다음에 게시하는 판부터 들어갑니다.</Notice>
      {notice ? <Notice>{notice}</Notice> : null}
      <RulebookEditor
        // 저장한 뒤 받은 룰북으로 입력을 다시 채운다(서버가 앞뒤 공백을 뗀 제목 같은 것)
        key={rulebook.updated_at}
        initial={rulebookDraft(rulebook)}
        templates={null}
        die={rulebook.rules.die}
        submitLabel="저장"
        busy={updating.busy}
        problem={updating.problem}
        onSubmit={(draft) => void submit(draft)}
        actions={<DeleteRulebook rulebook={rulebook} />}
      />
    </>
  );
}

function created(state: unknown): boolean {
  return state !== null && typeof state === 'object' && (state as Record<string, unknown>).created === true;
}

function DeleteRulebook({ rulebook }: { rulebook: RulebookDetail }) {
  const navigate = useNavigate();
  const deleting = useDeleteRulebook(rulebook.id);

  async function remove(): Promise<boolean> {
    const done = await deleting.remove();
    if (done) navigate('/trpg/studio/rulebooks', { replace: true });
    return done;
  }

  return (
    <ConfirmButton
      label="지우기"
      title="룰북 지우기"
      confirm="지우기"
      busy={deleting.busy}
      problem={deleting.problem}
      onConfirm={remove}
    >
      <p>「{rulebook.title}」 룰북을 지웁니다. 되돌릴 수 없습니다. 이 룰북을 쓰는 시나리오가 있으면 지우지 못합니다.</p>
    </ConfirmButton>
  );
}
