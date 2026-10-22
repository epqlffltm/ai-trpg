// web/apps/web/src/components/ItemCard.tsx
// 목록 한 칸. 제목, 한 줄 설명, 만든 사람, 작은 표시들. 누르면 그 화면으로 간다. 첫 화면과 서비스의 목록이 함께 쓴다.

import { Link } from 'react-router';

type Props = {
  to: string;
  title: string;
  description?: string | undefined;
  /** 만든 사람 같은 한 줄. 아직 모르면 비운다 */
  byline?: string | undefined;
  meta?: (string | null | undefined)[];
};

export function ItemCard({ to, title, description, byline, meta = [] }: Props) {
  const tags = [...new Set(meta.filter((value): value is string => Boolean(value)))];
  return (
    <li className="item-card">
      <Link to={to} className="item-card__link">
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
