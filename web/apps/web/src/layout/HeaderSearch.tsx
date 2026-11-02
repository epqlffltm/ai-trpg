// web/apps/web/src/layout/HeaderSearch.tsx
// 머리의 작품 검색칸(#984). 적고 찾으면 검색 결과 화면(/search?q=)으로 간다. 검색어의 규칙에 맞을 때만 간다.
// 결과 화면에 있으면 그 검색어를 칸에 채워 둔다(주소가 바뀌면 다시 채운다).

import { Button } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { SEARCH_MAX_LENGTH, isSearchable, searchPath } from '../pages/search/searchView';

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
    <form className="app-header__search" role="search" aria-label="작품 검색" onSubmit={submit}>
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
