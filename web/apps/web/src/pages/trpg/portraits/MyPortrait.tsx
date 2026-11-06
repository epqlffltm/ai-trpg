// web/apps/web/src/pages/trpg/portraits/MyPortrait.tsx
// 내가 올린 캐릭터 그림 하나의 작은 칸. 토큰을 실어 받은 바이트를 띄운다. 받지 못하면 빈 칸에 까닭을 적는다.

import { useQuery } from '@tanstack/react-query';
import { portraitImageQuery } from './portraitQueries';
import { useBlobUrl } from './useBlobUrl';

type Props = { portraitId: string; alt: string; className?: string };

export function MyPortrait({ portraitId, alt, className = 'portrait-thumb' }: Props) {
  const image = useQuery(portraitImageQuery(portraitId));
  const url = useBlobUrl(image.data);
  if (url) return <img className={className} src={url} alt={alt} />;
  return (
    <span className={`${className} portrait-thumb--empty`} role="img" aria-label={alt}>
      {image.isError ? '그림을 받지 못했습니다' : ''}
    </span>
  );
}
