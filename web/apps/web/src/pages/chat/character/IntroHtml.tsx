// web/apps/web/src/pages/chat/character/IntroHtml.tsx
// 캐릭터의 소개 글을 그린다. 거른 HTML(introHtml.ts)을 넘치면 잘리는 상자(overflow: hidden, contain: content) 안에만 넣는다.
// 그린 뒤에 거른 인라인 CSS 를 CSSOM 으로 입힌다(CSP 가 HTML 의 style 속성을 막는다. introHtml.ts 의 머리말).
// 글 속의 그림은 토큰을 실어 받아(useImageUrl 과 같은 열쇠로 한 번만) blob: 주소를 넣고, 화면이 사라지면 주소를 놓는다.

import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef } from 'react';
import { fetchImage } from '../../../api/images';
import { imageKey } from '../../../hooks/useImageUrl';
import { sanitizeIntro } from './introHtml';

export function IntroHtml({ html }: { html: string }) {
  const clean = useMemo(() => sanitizeIntro(html), [html]);
  const box = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    const root = box.current;
    if (!root) return undefined;
    applyStyles(root);
    return fillImages(root, queryClient);
  }, [clean, queryClient]);

  if (!clean.trim()) return <p className="hint">소개글이 없습니다.</p>;
  return <div ref={box} className="intro-html" dangerouslySetInnerHTML={{ __html: clean }} />;
}

/** data-intro-style 의 CSS 를 그 요소의 style 로. 이미 거른 값이다 */
function applyStyles(root: HTMLElement): void {
  for (const element of root.querySelectorAll<HTMLElement>('[data-intro-style]')) {
    element.style.cssText = element.dataset.introStyle ?? '';
  }
}

/** 상자 안의 그림마다 바이트를 받아 주소를 넣는다. 돌려준 함수가 주소를 놓는다 */
function fillImages(root: HTMLElement, queryClient: QueryClient): () => void {
  const urls: string[] = [];
  let live = true;
  for (const image of root.querySelectorAll<HTMLImageElement>('img[data-image-id]')) {
    const id = image.dataset.imageId as string;
    queryClient
      .fetchQuery({ queryKey: imageKey(id), queryFn: ({ signal }) => fetchImage(id, signal), staleTime: Infinity })
      .then((blob) => {
        if (!live || blob.size === 0) return;
        const url = URL.createObjectURL(blob);
        urls.push(url);
        image.src = url;
      })
      .catch(() => image.classList.add('intro-html__missing'));
  }
  return () => {
    live = false;
    urls.forEach((url) => URL.revokeObjectURL(url));
  };
}
