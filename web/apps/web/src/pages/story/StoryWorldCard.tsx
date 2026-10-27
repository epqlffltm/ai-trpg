// web/apps/web/src/pages/story/StoryWorldCard.tsx
// 공개 세계관 한 칸. 대표 그림, 이름, 등급·기한·태그. 누르면 세계관 소개(D1)로 간다. 내 이야기와 첫 화면이 함께 쓴다.
// 그림은 토큰을 실어 받는다(성인 등급의 그림은 img 로 받지 못한다). 그림이 없거나 받지 못하면 빈 칸이다.

import { Link } from 'react-router';
import type { PublicWorldSummary } from '../../api/storyWorlds';
import { useImageUrl } from '../../hooks/useImageUrl';
import { worldTags } from './storyWorldView';

export function StoryWorldCard({ world }: { world: PublicWorldSummary }) {
  const image = useImageUrl(world.image_id);
  const tags = worldTags(world);
  return (
    <li className="item-card character-card">
      <Link to={`/story/worlds/${encodeURIComponent(world.id)}`} className="item-card__link">
        {image.url ? <img src={image.url} alt="" className="character-card__image" /> : <span className="character-card__image" aria-hidden="true" />}
        <span className="item-card__title">{world.name}</span>
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
