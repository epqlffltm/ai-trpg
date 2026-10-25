// web/apps/web/src/pages/board/Pager.tsx
// 쪽 넘기기. "이전", "3 / 12쪽", "다음". 쪽은 주소의 page 값이라 뒤로 가기와 링크 공유가 된다.

import { Link } from 'react-router';

type Props = { page: number; pages: number; hrefFor: (page: number) => string };

export function Pager({ page, pages, hrefFor }: Props) {
  if (pages <= 1) return null;
  return (
    <nav className="pager" aria-label="쪽">
      {page > 1 ? <Link to={hrefFor(page - 1)}>이전</Link> : <span className="hint">이전</span>}
      <span aria-current="page">
        {page} / {pages}쪽
      </span>
      {page < pages ? <Link to={hrefFor(page + 1)}>다음</Link> : <span className="hint">다음</span>}
    </nav>
  );
}
