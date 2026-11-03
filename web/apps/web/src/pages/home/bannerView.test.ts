// web/apps/web/src/pages/home/bannerView.test.ts
// 홍보 배너(#994)의 한 장씩: 서버 사이에 섞어 정렬하지 않고 TRPG, chat, story 차례로 잇는다. 넘기기는 끝에서 돈다.

import { describe, expect, it } from 'vitest';
import type { AssetBanner, ScenarioBanner } from '../../api/banners';
import { bannerSlides, turned } from './bannerView';

const SCENARIO = {
  id: 'b-1',
  listing: { scenario_id: 's-1', creator_id: 'c-1', title: '잿빛 수도원', tagline: '종이 울리지 않는 밤', description: '', genre: 'horror', tags: [], rating: 'all', recommended_players: { min: 2, max: 4 }, version: 1, version_note: '', published_at: '2026-10-20T00:00:00Z' },
} as unknown as ScenarioBanner;
const WORLD = { id: 'b-2', kind: 'world', character: null, world: { id: 'w-1', version: 1, name: '여름 학교', image_id: 'i-1', rating: 'all', tags: ['학원'], deadline_days: 30, published_at: '2026-10-26T00:00:00Z' } } as unknown as AssetBanner;
const CHARACTER = { id: 'b-3', kind: 'character', world: null, character: { id: 'c-9', version: 1, name: '세라', tags: ['사서', '조용함'], genre: 'romance', rating: 'all', image_id: null, published_at: '2026-10-26T00:00:00Z' } } as unknown as AssetBanner;

describe('bannerSlides', () => {
  it('TRPG, chat, story 차례로 잇고 소개 화면으로 간다', () => {
    const slides = bannerSlides([SCENARIO], [WORLD, CHARACTER]);

    expect(slides.map((slide) => [slide.service, slide.title, slide.to])).toEqual([
      ['TRPG', '잿빛 수도원', '/trpg/scenarios/s-1'],
      ['chat', '세라', '/chat/characters/c-9'],
      ['story', '여름 학교', '/story/worlds/w-1'],
    ]);
    expect(slides[1]?.line).toBe('#사서 #조용함');
    expect(slides[2]?.imageId).toBe('i-1');
  });

  it('넘기기는 끝에서 처음으로, 처음에서 끝으로 돈다', () => {
    expect([turned(2, 1, 3), turned(0, -1, 3), turned(0, 1, 0)]).toEqual([0, 2, 0]);
  });
});
