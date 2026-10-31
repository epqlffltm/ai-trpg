// web/apps/web/src/pages/trpg/studio/scenarios/listingForm.ts
// 시나리오의 소개 탭(B9). 순수한 함수다(서버의 ListingUpdate 와 listings/service.py 의 find_problems 를 따른다).
//
// - 한줄소개 100 자, 소개글 5,000 자, 장르 하나, 태그 10 개(하나에 20 자, 대소문자만 다른 것도 겹침)
// - 공개하려면 한줄소개와 장르가 있어야 한다. 공개 중에는 한줄소개를 비울 수 없다(서버가 409). 먼저 공개를 내린다
// - 장르는 반드시 하나다. 플레이 화면과 소개 화면의 테마를 정한다. 고르기 전에는 저장하지 않는다(서버도 409 genre_missing)
// - 태그는 쉼표로 나눈 한 칸이다(로어북 항목의 키워드와 같다)

import type { Genre, ListingDetail, ListingUpdate } from '../../../../api/types';
import { splitWords, wordsHint } from '../collection/collectionForm';

export const TAGLINE_MAX = 100;
export const LISTING_DESCRIPTION_MAX = 5000;
export const TAGS_MAX = 10;
export const TAG_MAX = 20;

export type ListingDraft = {
  tagline: string;
  description: string;
  /** 아직 쓰지 않은 소개 페이지면 null. 고르기 전에는 저장하지 않고, 한 번 고르면 다른 것으로 바꿀 수만 있다 */
  genre: Genre | null;
  /** 쉼표로 나눈 태그 */
  tags: string;
};

/** 공개하지 못하는 까닭(서버의 Problem) */
export type ListingProblem = 'tagline_empty' | 'genre_missing';

const PROBLEM_TEXTS: Record<ListingProblem, string> = {
  tagline_empty: '한줄소개가 비어 있습니다.',
  genre_missing: '장르를 고르지 않았습니다.',
};

export function listingDraft(listing: ListingDetail): ListingDraft {
  return { tagline: listing.tagline, description: listing.description, genre: listing.genre, tags: listing.tags.join(', ') };
}

/** 소개 페이지가 공개할 조건을 갖추지 못한 까닭 전부. 비면 공개할 수 있다 */
export function listingProblems(listing: Pick<ListingDetail, 'tagline' | 'genre'>): ListingProblem[] {
  const problems: ListingProblem[] = [];
  if (listing.tagline.trim() === '') problems.push('tagline_empty');
  if (listing.genre === null) problems.push('genre_missing');
  return problems;
}

export function listingProblemText(problem: ListingProblem): string {
  return PROBLEM_TEXTS[problem];
}

/** 서버가 준 problems 가운데 아는 것만 */
export function knownListingProblems(values: unknown): ListingProblem[] {
  if (!Array.isArray(values)) return [];
  return values.filter((value): value is ListingProblem => value === 'tagline_empty' || value === 'genre_missing');
}

/** 칸마다 고칠 것. 장르는 늘 있어야 한다. published 면 공개 중이라 한줄소개도 비울 수 없다 */
export function listingHints(draft: ListingDraft, published: boolean): Record<string, string> {
  const hints: Record<string, string> = {};
  if (draft.tagline.trim().length > TAGLINE_MAX) hints.tagline = `${TAGLINE_MAX}자까지입니다.`;
  if (draft.description.length > LISTING_DESCRIPTION_MAX) hints.description = `${LISTING_DESCRIPTION_MAX.toLocaleString('ko-KR')}자까지입니다.`;
  const tags = wordsHint(splitWords(draft.tags), TAGS_MAX, TAG_MAX, '태그');
  if (tags) hints.tags = tags;
  if (draft.genre === null) hints.genre = '장르를 골라 주세요. 장르는 반드시 하나입니다.';
  if (published) addPublishedHints(hints, draft);
  return hints;
}

/** 공개 중에 비우면 막는다. 서버도 409 로 막는다 */
function addPublishedHints(hints: Record<string, string>, draft: ListingDraft): void {
  const emptied = ' 공개 중에는 비울 수 없습니다. 비우려면 게시 탭에서 공개를 먼저 내리세요.';
  if (draft.tagline.trim() === '') hints.tagline = `한줄소개가 비어 있습니다.${emptied}`;
}

/** 보낼 본문. 칸 넷을 모두 보낸다(빈 태그 목록은 "모두 없앤다", 장르 null 은 "보내지 않았다") */
export function toListingBody(draft: ListingDraft): ListingUpdate {
  return { tagline: draft.tagline.trim(), description: draft.description, genre: draft.genre, tags: splitWords(draft.tags) };
}
