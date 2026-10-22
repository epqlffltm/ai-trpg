// web/apps/web/src/pages/trpg/browse/filters.ts
// 탐색(B1)의 거르는 조건을 주소의 쿼리(?genre=&tag=&players=)와 오간다. 순수한 함수다.
// 조건을 주소에 두어 뒤로 가기, 새로 고침, 링크(B2 의 태그를 누르면 /trpg?tag=...)가 같은 목록을 연다.
// 모르는 값(없는 장르, 1~4 밖의 인원, 긴 태그)은 버린다. 서버에 보내면 422 다.

import type { ListingFilters } from '../../../api/listings';
import type { Genre } from '../../../api/types';
import { isGenre, PLAYER_COUNTS } from '../labels';

/** 태그 하나의 최대 길이(서버의 상한) */
const TAG_MAX = 20;

export function parseFilters(params: URLSearchParams): ListingFilters {
  return {
    genre: parseGenre(params.get('genre')),
    tag: parseTag(params.get('tag')),
    players: parsePlayers(params.get('players')),
  };
}

export function toSearchParams(filters: ListingFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.genre) params.set('genre', filters.genre);
  if (filters.tag) params.set('tag', filters.tag);
  if (filters.players) params.set('players', String(filters.players));
  return params;
}

export function hasFilters(filters: ListingFilters): boolean {
  return Boolean(filters.genre || filters.tag || filters.players);
}

/** 그 태그로 거른 탐색의 주소(B2 의 태그) */
export function tagSearchPath(tag: string): string {
  return `/trpg?${toSearchParams({ tag }).toString()}`;
}

function parseGenre(value: string | null): Genre | undefined {
  return value && isGenre(value) ? value : undefined;
}

function parseTag(value: string | null): string | undefined {
  const tag = value?.trim();
  return tag && tag.length <= TAG_MAX ? tag : undefined;
}

function parsePlayers(value: string | null): number | undefined {
  const count = Number(value);
  return (PLAYER_COUNTS as readonly number[]).includes(count) ? count : undefined;
}
