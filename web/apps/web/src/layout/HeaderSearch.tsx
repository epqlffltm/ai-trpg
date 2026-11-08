// web/apps/web/src/layout/HeaderSearch.tsx
// 머리의 작품 검색칸(#984). 적고 찾으면 검색 결과 화면(/search?q=)으로 간다. 검색어의 규칙에 맞을 때만 간다.
// 결과 화면에 있으면 그 검색어를 칸에 채워 둔다(주소가 바뀌면 다시 채운다).
// 좁은 화면에서는 칸을 접어 두고 검색 아이콘(HeaderSearchToggle)으로 펼친다. 아이콘은 좁은 화면에만 보인다(app.css).

import { Button } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { SEARCH_MAX_LENGTH, isSearchable, searchPath } from '../pages/search/searchView';

const SEARCH_FORM_ID = 'header-search';

/** 좁은 화면의 검색 아이콘. 누르면 검색칸을 펼치고 접는다 */
export function HeaderSearchToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="app-header__icon-button app-header__search-toggle"
      aria-label={open ? '검색칸 접기' : '검색칸 펼치기'}
      aria-expanded={open}
      aria-controls={SEARCH_FORM_ID}
      onClick={onToggle}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
        <path d="M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13zM15.5 15.5L20 20" />
      </svg>
    </button>
  );
}

export function HeaderSearch() {
  const location = useLocation();
  const [params] = useSearchParams();
  const current = location.pathname === '/search' ? (params.get('q') ?? '') : '';
  return <SearchBox key={current} initial={current} />;
}

function SearchBox({ initial }: { initial: string }) {
  const [q, setQ] = useState(initial);
  const navigate = useNavigate();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSearchable(q)) void navigate(searchPath(q));
  }

  return (
    <form id={SEARCH_FORM_ID} className="app-header__search" role="search" aria-label="작품 검색" onSubmit={submit}>
      <input
        type="search"
        aria-label="작품 검색어"
        placeholder="작품 이름, #태그"
        value={q}
        maxLength={SEARCH_MAX_LENGTH}
        onChange={(event) => setQ(event.target.value)}
      />
      <Button type="submit" variant="quiet" aria-label="작품 찾기">
        찾기
      </Button>
    </form>
  );
}
