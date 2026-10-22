// web/apps/web/src/pages/trpg/browse/BrowseFilters.tsx
// 탐색(B1)의 거르기. 장르 하나, 함께 할 인원 하나, 태그 하나. 태그는 소개(B2)의 태그를 눌러 걸리고 여기서는 풀기만 한다.
// 조건을 바꾸면 onChange 로 새 조건 전체를 넘긴다. 주소에 두는 것은 쓰는 쪽(ScenarioBrowsePage)이다.

import { Button, ChipGroup } from '@ai-trpg/ui';
import type { ListingFilters } from '../../../api/listings';
import type { Genre } from '../../../api/types';
import { GENRE_VALUES, genreLabel, PLAYER_COUNTS } from '../labels';
import { hasFilters } from './filters';

const GENRE_CHIPS = GENRE_VALUES.map((genre) => ({ value: genre, label: genreLabel(genre) }));
const PLAYER_CHIPS = PLAYER_COUNTS.map((count) => ({ value: count, label: count === 1 ? '혼자' : `${count}명` }));

type Props = { filters: ListingFilters; onChange: (next: ListingFilters) => void };

export function BrowseFilters({ filters, onChange }: Props) {
  return (
    <div className="browse-filters">
      <ChipGroup<Genre>
        label="장르"
        chips={GENRE_CHIPS}
        selected={filters.genre}
        onChange={(genre) => onChange({ ...filters, genre })}
      />
      <ChipGroup<number>
        label="함께 할 인원"
        chips={PLAYER_CHIPS}
        selected={filters.players}
        onChange={(players) => onChange({ ...filters, players })}
      />
      {filters.tag ? (
        <p className="browse-filters__tag">
          태그 <strong>#{filters.tag}</strong>
          <Button variant="quiet" onClick={() => onChange({ ...filters, tag: undefined })}>
            태그 풀기
          </Button>
        </p>
      ) : null}
      {hasFilters(filters) ? (
        <Button variant="quiet" onClick={() => onChange({})}>
          조건 모두 풀기
        </Button>
      ) : null}
    </div>
  );
}
