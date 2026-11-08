// web/apps/web/src/pages/home/bannerView.ts
// 첫 화면의 홍보 배너(#994)를 한 장씩 넘길 모양으로 바꾼다. 화면을 그리지 않는 순수한 함수다.
// 서버 사이에 섞어 정렬하지 않는다(#593). TRPG, chat, story 차례로 잇고, 서버 안의 차례는 서버가 정한 대로다.

import type { AssetBanner, ScenarioBanner } from '../../api/banners';

/** 배너가 걸린 서비스 */
export type BannerService = 'TRPG' | 'chat' | 'story';

export type BannerSlide = {
  id: string;
  /** 서비스의 이름(TRPG, chat, story) */
  service: string;
  title: string;
  /** 한 줄 소개. 시나리오는 한줄소개, 캐릭터와 세계관은 태그 */
  line: string;
  /** 소개 화면의 주소 */
  to: string;
  /** 캐릭터와 세계관의 대표 그림(asset 의 그림). 시나리오는 null 이다 */
  imageId: string | null;
  /** 시나리오의 표지(#1164). 게임 서버가 공개 소개의 그림으로 내준다. 캐릭터와 세계관, 표지 없는 시나리오는 null 이다 */
  scenarioCover: { scenarioId: string; imageId: string } | null;
};

export function scenarioSlide(banner: ScenarioBanner): BannerSlide {
  const listing = banner.listing;
  return {
    id: banner.id,
    service: 'TRPG',
    title: listing.title,
    line: listing.tagline,
    to: `/trpg/scenarios/${listing.scenario_id}`,
    imageId: null,
    scenarioCover: listing.cover_image_id ? { scenarioId: listing.scenario_id, imageId: listing.cover_image_id } : null,
  };
}

/** 캐릭터나 세계관의 배너 한 장. 둘 다 비어 있으면(서버가 고친 모양) 빼려고 null 이다 */
export function assetSlide(banner: AssetBanner): BannerSlide | null {
  if (banner.character) {
    const character = banner.character;
    return { id: banner.id, service: 'chat', title: character.name, line: tagLine(character.tags), to: `/chat/characters/${character.id}`, imageId: character.image_id ?? null, scenarioCover: null };
  }
  if (banner.world) {
    const world = banner.world;
    return { id: banner.id, service: 'story', title: world.name, line: tagLine(world.tags), to: `/story/worlds/${world.id}`, imageId: world.image_id ?? null, scenarioCover: null };
  }
  return null;
}

/** 시나리오, 캐릭터, 세계관의 차례로 잇는다. asset 서버의 배너는 캐릭터를 먼저, 그다음 세계관이다 */
export function bannerSlides(scenarios: ScenarioBanner[], assets: AssetBanner[]): BannerSlide[] {
  const slides = assets.map(assetSlide).filter((slide): slide is BannerSlide => slide !== null);
  return [...scenarios.map(scenarioSlide), ...slides.filter((slide) => slide.service === 'chat'), ...slides.filter((slide) => slide.service === 'story')];
}

/** 서비스 하나의 배너만(탐색 화면의 배너, Stitch 12·16·17번). service 가 없으면 모두 */
export function slidesOf(slides: BannerSlide[], service: BannerService | undefined): BannerSlide[] {
  return service ? slides.filter((slide) => slide.service === service) : slides;
}

/** 넘겼을 때의 자리. 끝에서 넘기면 처음으로, 처음에서 앞으로 가면 끝으로 돈다 */
export function turned(index: number, step: number, count: number): number {
  if (count === 0) return 0;
  return (((index + step) % count) + count) % count;
}

function tagLine(tags: string[]): string {
  return tags.map((tag) => `#${tag}`).join(' ');
}
