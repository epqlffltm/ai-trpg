// web/apps/web/src/pages/board/Pager.tsx
// 쪽 넘기기(Stitch 11번). "이전", 쪽 번호 다섯까지(지금 쪽이 가운데), "다음". 쪽은 주소의 page 값이라 뒤로 가기와 링크 공유가 된다.
// 쪽 번호는 읽는 프로그램에 "3쪽"처럼 읽힌다. 지금 쪽은 길이 아니고 aria-current 다.

import { Link } from 'react-router';
import { pageWindow } from './boardView';

type Props = { page: number; pages: number; hrefFor: (page: number) => string };

export function Pager({ page, pages, hrefFor }: Props) {
  if (pages <= 1) return null;
  return (
    <nav className="pager" aria-label="쪽">
      {page > 1 ? <Link to={hrefFor(page - 1)}>이전</Link> : <span className="hint">이전</span>}
      {pageWindow(page, pages).map((number) =>
        number === page ? (
          <span key={number} className="pager__page" aria-current="page">
            {number}
            <span className="visually-hidden">쪽</span>
          </span>
        ) : (
          <Link key={number} className="pager__page" to={hrefFor(number)}>
            {number}
            <span className="visually-hidden">쪽</span>
          </Link>
        ),
      )}
      {page < pages ? <Link to={hrefFor(page + 1)}>다음</Link> : <span className="hint">다음</span>}
    </nav>
  );
}
