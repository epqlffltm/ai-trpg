// web/apps/web/src/pages/trpg/studio/rulebooks/RulebookEditPage.tsx
// 룰북 고치기(B9, /trpg/studio/rulebooks/:rulebookId). 제목, 소개, 진행 지침, 방어 규칙을 고치고 지운다.
// 템플릿은 보이기만 한다. 이미 게시한 판은 게시할 때의 규칙으로 굳어 있어 여기서 고쳐도 바뀌지 않는다고 알린다.
// 남의 것이거나 없으면 404 라 목록으로 돌아가는 길만 둔다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import type { RulebookDetail } from '../../../../api/types';
import { AssetLoad } from '../AssetLoad';
import { DeleteAssetButton } from '../DeleteAssetButton';
import { useSavedNotice } from '../useSavedNotice';
import { rulebookDraft, type RulebookDraft } from './rulebookForm';
import { rulebookQuery, rulebookTemplatesQuery } from './rulebookQueries';
import { RulebookEditor } from './RulebookEditor';
import { templateName } from './rulebookView';
import { useUpdateRulebook } from './useRulebookActions';

export function RulebookEditPage() {
  const { rulebookId = '' } = useParams();
  const query = useQuery(rulebookQuery(rulebookId));
  return (
    <main className="page page--medium">
      <p>
        <Link to="/trpg/studio/rulebooks">내 룰북</Link>
      </p>
      <AssetLoad kind="rulebooks" pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
      {query.data ? <EditRulebook rulebook={query.data} /> : null}
    </main>
  );
}

function EditRulebook({ rulebook }: { rulebook: RulebookDetail }) {
  const templates = useQuery(rulebookTemplatesQuery());
  const updating = useUpdateRulebook(rulebook.id);
  const notice = useSavedNotice();

  async function submit(draft: RulebookDraft) {
    notice.clear();
    if (await updating.update(draft)) notice.saved();
  }

  return (
    <>
      <h1>{rulebook.title}</h1>
      <p className="hint">
        템플릿: {templateName(templates.data, rulebook.rules.template)}. 만든 뒤에는 바꿀 수 없습니다.
      </p>
      <Notice>이미 게시한 시나리오의 판은 게시할 때의 규칙으로 굳어 있어, 여기서 고쳐도 바뀌지 않습니다. 다음에 게시하는 판부터 들어갑니다.</Notice>
      {notice.notice ? <Notice>{notice.notice}</Notice> : null}
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
        actions={<DeleteAssetButton kind="rulebooks" assetId={rulebook.id} title={rulebook.title} />}
      />
    </>
  );
}
