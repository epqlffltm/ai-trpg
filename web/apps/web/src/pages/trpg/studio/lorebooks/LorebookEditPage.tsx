// web/apps/web/src/pages/trpg/studio/lorebooks/LorebookEditPage.tsx
// 로어북 하나(B9, /trpg/studio/lorebooks/:lorebookId). 제목과 소개를 고치고, 항목을 종류로 걸러 보고 더하고 고치고 지운다.

import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { deleteEntry, fetchLorebook, updateLorebook } from '../../../../api/lorebooks';
import { CollectionEditPage } from '../collection/CollectionEditPage';
import { ItemsSection } from '../collection/ItemsSection';
import { preview } from '../collection/itemsView';
import { useItemActions } from '../collection/useItemActions';
import { EntryForm } from './EntryForm';
import { LOREBOOK_MAX_ENTRIES, LORE_KINDS } from './entryForm';
import { entriesQuery } from './lorebookQueries';

export function LorebookEditPage() {
  const { lorebookId = '' } = useParams();
  return (
    <CollectionEditPage kind="lorebooks" assetId={lorebookId} load={fetchLorebook} update={(body) => updateLorebook(lorebookId, body)}>
      <Entries lorebookId={lorebookId} />
    </CollectionEditPage>
  );
}

function Entries({ lorebookId }: { lorebookId: string }) {
  const entries = useQuery(entriesQuery(lorebookId));
  const removing = useItemActions('lorebooks', lorebookId);
  return (
    <ItemsSection
      label="항목"
      max={LOREBOOK_MAX_ENTRIES}
      items={entries.data}
      pending={entries.isPending}
      failed={entries.isError}
      retry={() => void entries.refetch()}
      kindLabels={LORE_KINDS}
      summary={(entry) => (
        <>
          {entry.keywords.length > 0 ? <span className="hint">키워드 {entry.keywords.join(', ')} · </span> : null}
          {preview(entry.content)}
        </>
      )}
      form={(entry, done) => <EntryForm lorebookId={lorebookId} entry={entry} done={done} />}
      remove={(entry) => removing.run(() => deleteEntry(lorebookId, entry.id))}
      removing={removing}
    />
  );
}
