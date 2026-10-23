// web/apps/web/src/pages/trpg/studio/worlds/WorldEditPage.tsx
// 세계관 고치기(B9, /trpg/studio/worlds/:worldId). 제목, 소개, 설정, GM 메모, 참고 자료를 고치고 지운다.
// 이미 게시한 판은 게시할 때의 세계관으로 굳어 있어 여기서 고쳐도 바뀌지 않는다고 알린다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import type { WorldDetail } from '../../../../api/types';
import { updateWorld } from '../../../../api/worlds';
import { AssetLoad } from '../AssetLoad';
import { DeleteAssetButton } from '../DeleteAssetButton';
import { studioPath } from '../studioKinds';
import { useSaveAsset } from '../useAssetActions';
import { useSavedNotice } from '../useSavedNotice';
import { toWorldUpdate, worldDraft, type WorldDraft } from './worldForm';
import { WorldEditor } from './WorldEditor';
import { worldQuery } from './worldQueries';

export function WorldEditPage() {
  const { worldId = '' } = useParams();
  const query = useQuery(worldQuery(worldId));
  return (
    <main className="page page--medium">
      <p>
        <Link to={studioPath('worlds')}>내 세계관</Link>
      </p>
      <AssetLoad kind="worlds" pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
      {query.data ? <EditWorld world={query.data} /> : null}
    </main>
  );
}

function EditWorld({ world }: { world: WorldDetail }) {
  const saving = useSaveAsset<WorldDetail>('worlds');
  const notice = useSavedNotice();

  async function submit(draft: WorldDraft) {
    notice.clear();
    if (await saving.save(() => updateWorld(world.id, toWorldUpdate(draft)))) notice.saved();
  }

  return (
    <>
      <h1>{world.title}</h1>
      <Notice>이미 게시한 시나리오의 판은 게시할 때의 세계관으로 굳어 있어, 여기서 고쳐도 바뀌지 않습니다. 다음에 게시하는 판부터 들어갑니다.</Notice>
      {notice.notice ? <Notice>{notice.notice}</Notice> : null}
      <WorldEditor
        // 저장한 뒤 받은 세계관으로 입력을 다시 채운다(서버가 앞뒤 공백을 뗀 제목 같은 것)
        key={world.updated_at}
        initial={worldDraft(world)}
        submitLabel="저장"
        busy={saving.busy}
        problem={saving.problem}
        onSubmit={(draft) => void submit(draft)}
        actions={<DeleteAssetButton kind="worlds" assetId={world.id} title={world.title} />}
      />
    </>
  );
}
