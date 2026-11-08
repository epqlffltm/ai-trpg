// web/apps/web/src/pages/home/PromoBanner.tsx
// 첫 화면 위쪽의 넘기는 홍보 배너(#994). 운영자가 건 작품을 한 장씩 보인다. 작품의 소개로 간다.
// 두 서버(게임, asset)를 따로 부른다. 한 서버가 답하지 않으면 그 서버의 배너만 빠진다. 걸린 것이 없으면 아무것도 보이지 않는다.
// 저절로 넘기지 않는다. 이전·다음 단추로 넘긴다.
// 탐색 화면(Stitch 12·16·17번)은 service 로 그 서비스의 배너만 보인다. 그때는 필요 없는 서버를 부르지 않는다.
// 시나리오의 그림은 표지(#1164)다. 게임 서버의 공개 소개 그림으로 받는다(useCoverUrl).

import { Button } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { useImageUrl } from '../../hooks/useImageUrl';
import { useCoverUrl } from '../trpg/portraits/ScenarioCover';
import { bannerSlides, slidesOf, turned, type BannerService, type BannerSlide } from './bannerView';
import { assetBannersQuery, scenarioBannersQuery } from './queries';

export function PromoBanner({ signedIn, service }: { signedIn: boolean; service?: BannerService }) {
  const scenarios = useQuery({ ...scenarioBannersQuery(signedIn), enabled: service === undefined || service === 'TRPG' });
  const assets = useQuery({ ...assetBannersQuery(signedIn), enabled: service !== 'TRPG' });
  const slides = slidesOf(bannerSlides(scenarios.data ?? [], assets.data ?? []), service);
  const [index, setIndex] = useState(0);
  if (slides.length === 0) return null;
  const current = slides[Math.min(index, slides.length - 1)] as BannerSlide;

  return (
    <section className="promo-banner" aria-roledescription="넘기는 배너" aria-label="홍보">
      <Slide slide={current} />
      {slides.length > 1 ? (
        <div className="promo-banner__controls">
          <Button variant="quiet" onClick={() => setIndex(turned(index, -1, slides.length))}>
            이전
          </Button>
          <span aria-live="polite">
            {Math.min(index, slides.length - 1) + 1} / {slides.length}
          </span>
          <Button variant="quiet" onClick={() => setIndex(turned(index, 1, slides.length))}>
            다음
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function Slide({ slide }: { slide: BannerSlide }) {
  const image = useImageUrl(slide.imageId);
  const cover = useCoverUrl(slide.scenarioCover?.scenarioId ?? '', slide.scenarioCover?.imageId);
  const url = image.url ?? cover;
  return (
    <Link to={slide.to} className="promo-banner__slide">
      {url ? <img src={url} alt="" className="promo-banner__image" /> : null}
      <span className="promo-banner__body">
        <span className="promo-banner__service">{slide.service}</span>
        <span className="promo-banner__title">{slide.title}</span>
        {slide.line ? <span className="promo-banner__line">{slide.line}</span> : null}
      </span>
    </Link>
  );
}
