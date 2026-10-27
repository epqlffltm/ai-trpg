// web/apps/web/src/test/storyFixtures.ts
// story 시험이 함께 쓰는 세션의 세계관 칸(view) 만들기. 칸을 빼먹으면 빈 목록과 기본값으로 채운다.

import type { StoryView, StoryViewCast } from '../api/story';

export function castOut(id: string, name: string | null, extra: Partial<StoryViewCast> = {}): StoryViewCast {
  return {
    id,
    name,
    reveal: name === null ? 'silhouette' : 'shown',
    met: true,
    confessable: false,
    image_id: null,
    sprites: [],
    intro_html: null,
    age: null,
    gender: null,
    affection: null,
    events: [],
    ...extra,
  } as StoryViewCast;
}

export function storyView(extra: Partial<StoryView> = {}): StoryView {
  return {
    name: '여름 학교',
    image_id: null,
    intro_html: '',
    tags: [],
    deadline_days: null,
    after_ending: 'end',
    slots: [],
    places: [],
    paths: [],
    items: [],
    cast: [],
    events: [],
    endings: [],
    map: [],
    ...extra,
  } as StoryView;
}
