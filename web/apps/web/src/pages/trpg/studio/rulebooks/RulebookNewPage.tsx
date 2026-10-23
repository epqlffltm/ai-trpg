// web/apps/web/src/pages/trpg/studio/rulebooks/RulebookNewPage.tsx
// 룰북 만들기(B9, /trpg/studio/rulebooks/new). 템플릿을 읽고, 입력은 RulebookEditor 다. 만들면 그 룰북의 고치기로 간다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router';
import type { RulebookTemplates } from '../../../../api/types';
import { newRulebookDraft, type RulebookDraft } from './rulebookForm';
import { rulebookTemplatesQuery } from './rulebookQueries';
import { RulebookEditor } from './RulebookEditor';
import { useCreateRulebook } from './useRulebookActions';

export function RulebookNewPage() {
  const templates = useQuery(rulebookTemplatesQuery());
  return (
    <main className="page page--medium">
      <p>
        <Link to="/trpg/studio/rulebooks">내 룰북</Link>
      </p>
      <h1>새 룰북</h1>
      {templates.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {templates.isError ? (
        <Notice tone="error">
          템플릿을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void templates.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {templates.data ? <CreateForm templates={templates.data} /> : null}
    </main>
  );
}

function CreateForm({ templates }: { templates: RulebookTemplates }) {
  const navigate = useNavigate();
  const creating = useCreateRulebook();

  async function submit(draft: RulebookDraft) {
    const made = await creating.create(draft);
    if (made) navigate(`/trpg/studio/rulebooks/${made.id}`, { replace: true, state: { created: true } });
  }

  return (
    <RulebookEditor
      initial={newRulebookDraft(templates)}
      templates={templates}
      die={null}
      submitLabel="만들기"
      busy={creating.busy}
      problem={creating.problem}
      onSubmit={(draft) => void submit(draft)}
    />
  );
}
