// web/apps/web/src/pages/me/shortcuts/MyShortcutsPage.tsx
// 내 단축어(/me/shortcuts, #981). 계정의 것이고 chat 과 story 의 어느 대화에서든 "/이름"으로 부른다.
// 목록을 통째로 읽고 저장한다. 작품(캐릭터, 세계관)에 같은 이름의 단축어가 있으면 그 작품에서는 작품의 것이 쓰인다.
// 로그인해야 열린다(App.tsx 의 RequireSession).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { replaceMyShortcuts, type ShortcutList } from '../../../api/shortcuts';
import { ShortcutsFields } from '../../../components/shortcuts/ShortcutsFields';
import { shortcutDrafts, shortcutsHints, toShortcuts, type ShortcutDraft } from '../../../components/shortcuts/shortcutsForm';
import { putQueryData } from '../../../queryClient';
import { CharacterForm as SaveForm } from '../../chat/studio/characters/CharacterForm';
import { useCharacterSending } from '../../chat/studio/characters/useCharacterSending';
import { describeShortcutsProblem } from './shortcutsProblem';
import { myShortcutsKey, myShortcutsQuery } from './shortcutsQueries';

export function MyShortcutsPage() {
  const query = useQuery(myShortcutsQuery());
  return (
    <main className="page page--medium">
      <p>
        <Link to="/me">내 정보</Link>
      </p>
      <h1>내 단축어</h1>
      <p className="hint">
        대화와 이야기에서 /이름 으로 부르면 본문이 그 턴의 말 끝에 붙어 모델에 갑니다. 어느 작품에서든 씁니다. 작품에 같은 이름의 단축어가 있으면 작품의
        것이 먼저입니다.
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.data ? <EditForm list={query.data} /> : null}
    </main>
  );
}

function EditForm({ list }: { list: ShortcutList }) {
  const queryClient = useQueryClient();
  const [shortcuts, setShortcuts] = useState<ShortcutDraft[]>(() => shortcutDrafts(list.items));
  const [saved, setSaved] = useState(false);
  const sending = useCharacterSending(describeShortcutsProblem);
  const hints = shortcutsHints(shortcuts);

  async function submit() {
    setSaved(false);
    const result = await sending.send(() => replaceMyShortcuts({ items: toShortcuts(shortcuts) }));
    if (!result) return;
    setSaved(true);
    setShortcuts(shortcutDrafts(result.items));
    await putQueryData(queryClient, myShortcutsKey(), result);
  }

  return (
    <SaveForm
      label="내 단축어"
      busy={sending.busy}
      problem={sending.problem}
      saved={saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <ShortcutsFields shortcuts={shortcuts} hints={hints} onChange={setShortcuts} />
    </SaveForm>
  );
}
