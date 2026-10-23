// web/apps/web/src/pages/trpg/studio/collection/CollectionEditPage.tsx
// 묶음 재료(로어북, 몬스터 모음) 하나의 화면. 위에 제목과 소개(고치기, 지우기), 아래에 담긴 것(children)이 있다.
// 이미 게시한 판은 게시할 때의 것으로 굳어 있어 여기서 고쳐도 바뀌지 않는다고 알린다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import type { StudioKind } from '../../../../api/studio';
import type { AssetSummary } from '../../../../api/types';
import { AssetLoad } from '../AssetLoad';
import { DeleteAssetButton } from '../DeleteAssetButton';
import { kindText, studioPath } from '../studioKinds';
import { assetDetailKey } from '../studioQueries';
import { useSaveAsset } from '../useAssetActions';
import { useSavedNotice } from '../useSavedNotice';
import { collectionDraft, toCollectionBody, type CollectionDraft } from './collectionForm';
import { CollectionEditor } from './CollectionEditor';

type Props = {
  kind: StudioKind;
  assetId: string;
  /** 묶음 하나를 읽는다(로어북, 몬스터 모음) */
  load: (assetId: string, signal: AbortSignal) => Promise<AssetSummary>;
  update: (body: { title: string; description: string }) => Promise<AssetSummary>;
  /** 담긴 것의 영역 */
  children: ReactNode;
};

export function CollectionEditPage({ kind, assetId, load, update, children }: Props) {
  const query = useQuery({ queryKey: assetDetailKey(kind, assetId), queryFn: ({ signal }) => load(assetId, signal) });
  return (
    <main className="page page--medium">
      <p>
        <Link to={studioPath(kind)}>{kindText(kind).title}</Link>
      </p>
      <AssetLoad kind={kind} pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
      {query.data ? (
        <>
          <EditCollection kind={kind} asset={query.data} update={update} />
          {children}
        </>
      ) : null}
    </main>
  );
}

type EditProps = { kind: StudioKind; asset: AssetSummary; update: Props['update'] };

function EditCollection({ kind, asset, update }: EditProps) {
  const saving = useSaveAsset<AssetSummary>(kind);
  const notice = useSavedNotice();

  async function submit(draft: CollectionDraft) {
    notice.clear();
    if (await saving.save(() => update(toCollectionBody(draft)))) notice.saved();
  }

  return (
    <>
      <h1>{asset.title}</h1>
      <Notice>이미 게시한 시나리오의 판은 게시할 때의 것으로 굳어 있어, 여기서 고쳐도 바뀌지 않습니다. 다음에 게시하는 판부터 들어갑니다.</Notice>
      {notice.notice ? <Notice>{notice.notice}</Notice> : null}
      <CollectionEditor
        key={asset.updated_at}
        label={kindText(kind).label}
        initial={collectionDraft(asset)}
        submitLabel="저장"
        busy={saving.busy}
        problem={saving.problem}
        onSubmit={(draft) => void submit(draft)}
        actions={<DeleteAssetButton kind={kind} assetId={asset.id} title={asset.title} />}
      />
    </>
  );
}
