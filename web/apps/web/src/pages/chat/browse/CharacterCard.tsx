// web/apps/web/src/pages/chat/browse/CharacterCard.tsx
// 탐색(C1)의 캐릭터 한 칸. 대표 그림, 이름, 등급과 장르와 태그(랭킹이면 그 앞에 순위와 수). 대화를 시작한 수와 관심의 수(#985, #989)도 붙인다. 누르면 소개(C2)로 간다.
// 그림은 토큰을 실어 받는다(성인 등급의 그림은 img 로 받지 못한다). 그림이 없거나 받지 못하면 빈 칸이다.

import { Link } from 'react-router';
import type { PublicCharacterSummary } from '../../../api/types';
import { useImageUrl } from '../../../hooks/useImageUrl';
import { usageTags } from '../../../format/usage';
import { genreName } from '../../../genres/genres';
import { ratingBadge } from '../../home/labels';

/** badges 는 태그 앞에 붙는 표시다(랭킹의 "1위", "이번 주 12회", #985) */
export function CharacterCard({ character, badges = [] }: { character: PublicCharacterSummary; badges?: string[] }) {
  const image = useImageUrl(character.image_id);
  const tags = [
    ...badges,
    ratingBadge(character.rating),
    genreName(character.genre),
    ...usageTags('대화', character.start_count, character.heart_count),
    ...character.tags,
  ].filter((tag): tag is string => Boolean(tag));
  return (
    <li className="item-card character-card">
      <Link to={`/chat/characters/${character.id}`} className="item-card__link">
        {image.url ? <img src={image.url} alt="" className="character-card__image" /> : <span className="character-card__image" aria-hidden="true" />}
        <span className="item-card__title">{character.name}</span>
        {tags.length > 0 ? (
          <span className="item-card__meta">
            {[...new Set(tags)].map((tag) => (
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
