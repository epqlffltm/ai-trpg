// web/apps/web/src/pages/conversations/ConversationsPage.tsx
// 내 채팅(/conversations). 왼쪽 메뉴 열의 "내 채팅"과 좁은 화면의 맨 아래 탭 바 "내 채팅"이 여는 화면이다.
// 로그인해야 열린다(RequireSession). 왼쪽 메뉴 열의 최근 대화와 같은 한 목록(TRPG 테이블, 캐릭터 대화, 스토리를 섞어 최근 것부터)을
// 줄을 늘려 보인다. 위의 칩으로 종류를 거르고, 검색칸은 이름과 둘째 줄에서 찾는다(읽어 온 줄 안에서).

import { ChipGroup, type Chip } from '@ai-trpg/ui';
import { useState } from 'react';
import { RecentList, useRecentRows } from '../../layout/SidebarRecent';
import { filterRecent, RECENT_KIND_LABELS, RECENT_PAGE_ROWS, type RecentKind } from '../../layout/sidebarRecentView';

type KindChoice = RecentKind | 'all';

const KIND_CHIPS: Chip<KindChoice>[] = [
  { value: 'all', label: '전체' },
  { value: 'trpg', label: RECENT_KIND_LABELS.trpg },
  { value: 'character', label: RECENT_KIND_LABELS.character },
  { value: 'story', label: RECENT_KIND_LABELS.story },
];

export function ConversationsPage() {
  const recent = useRecentRows(RECENT_PAGE_ROWS);
  const [kind, setKind] = useState<KindChoice>('all');
  const [search, setSearch] = useState('');
  const rows = filterRecent(recent.rows, kind === 'all' ? null : kind, search);
  const filtered = kind !== 'all' || search.trim() !== '';
  return (
    <main className="page page--medium">
      <h1>내 채팅</h1>
      <div className="conversations-filters">
        <input
          type="search"
          className="ui-field__input conversations-filters__search"
          aria-label="대화 검색"
          placeholder="대화 검색"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <ChipGroup label="종류" chips={KIND_CHIPS} selected={kind} onChange={(value) => setKind(value ?? 'all')} />
      </div>
      <section className="sidebar-recent sidebar-recent--page" aria-label="내 채팅">
        <RecentList
          recent={{ ...recent, rows }}
          label="내 채팅 목록"
          empty={filtered ? '맞는 대화가 없어요.' : '아직 대화가 없어요.'}
        />
      </section>
    </main>
  );
}
