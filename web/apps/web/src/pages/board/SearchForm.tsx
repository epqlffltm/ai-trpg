// web/apps/web/src/pages/board/SearchForm.tsx
// 글 검색의 입력. 검색어의 규칙(boardView.ts 의 searchHint)에 맞을 때만 검색 화면으로 간다. board 가 있으면 그 게시판에서만 찾는다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { MAX_QUERY_LENGTH, normalizeQuery, searchHint, searchPath } from './boardView';

export function SearchForm({ initial = '', board }: { initial?: string; board?: string | undefined }) {
  const [q, setQ] = useState(initial);
  const navigate = useNavigate();
  const hint = searchHint(q);
  const blocked = normalizeQuery(q) === '' || hint !== null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!blocked) void navigate(searchPath(q, board));
  }

  return (
    <form className="board-search" role="search" aria-label="글 검색" onSubmit={submit} noValidate>
      <TextField label="검색어" value={q} maxLength={MAX_QUERY_LENGTH * 2} onChange={(event) => setQ(event.target.value)} error={hint ?? undefined} />
      <Button type="submit" variant="secondary" disabled={blocked}>
        찾기
      </Button>
    </form>
  );
}
