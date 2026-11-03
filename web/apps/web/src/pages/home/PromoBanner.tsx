// web/apps/web/src/pages/home/PromoBanner.tsx
// 첫 화면 위쪽의 넘기는 홍보 배너(#994). 운영자가 건 작품을 한 장씩 보인다. 작품의 소개로 간다.
// 두 서버(게임, asset)를 따로 부른다. 한 서버가 답하지 않으면 그 서버의 배너만 빠진다. 걸린 것이 없으면 아무것도 보이지 않는다.
// 저절로 넘기지 않는다. 이전·다음 단추로 넘긴다.

import { Button } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { useImageUrl } from '../../hooks/useImageUrl';
import { bannerSlides, turned, type BannerSlide } from './bannerView';
import { assetBannersQuery, scenarioBannersQuery } from './queries';

export function PromoBanner({ signedIn }: { signedIn: boolean }) {
  const scenarios = useQuery(scenarioBannersQuery(signedIn));
  const assets = useQuery(assetBannersQuery(signedIn));
  const slides = bannerSlides(scenarios.data ?? [], assets.data ?? []);
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
  return (
    <Link to={slide.to} className="promo-banner__slide">
      {image.url ? <img src={image.url} alt="" className="promo-banner__image" /> : null}
      <span className="promo-banner__body">
        <span className="promo-banner__service">{slide.service}</span>
        <span className="promo-banner__title">{slide.title}</span>
        {slide.line ? <span className="promo-banner__line">{slide.line}</span> : null}
      </span>
    </Link>
  );
}
