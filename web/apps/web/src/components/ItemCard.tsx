// web/apps/web/src/components/ItemCard.tsx
// 목록 한 칸. 제목, 한 줄 설명, 만든 사람, 작은 표시들. 누르면 그 화면으로 간다. 첫 화면과 서비스의 목록이 함께 쓴다.
// 그림(image)을 주면 맨 위에 둔다(시나리오의 표지, #1164).

import type { ReactNode } from 'react';
import { Link } from 'react-router';

type Props = {
  to: string;
  title: string;
  description?: string | undefined;
  /** 만든 사람 같은 한 줄. 아직 모르면 비운다 */
  byline?: string | undefined;
  meta?: (string | null | undefined)[];
  /** 맨 위의 그림. 없으면 글만의 칸이다 */
  image?: ReactNode;
};

export function ItemCard({ to, title, description, byline, meta = [], image }: Props) {
  const tags = [...new Set(meta.filter((value): value is string => Boolean(value)))];
  return (
    <li className={image ? 'item-card item-card--pictured' : 'item-card'}>
      <Link to={to} className="item-card__link">
        {image}
        <span className="item-card__title">{title}</span>
        {description ? <span className="item-card__description">{description}</span> : null}
        {byline ? <span className="item-card__byline">{byline}</span> : null}
        {tags.length > 0 ? (
          <span className="item-card__meta">
            {tags.map((tag) => (
              <span key={tag} className="item-card__tag">
                {tag}
              </span>
            ))}
          </span>
        ) : null}
      </Link>
    </li>
  );
}
