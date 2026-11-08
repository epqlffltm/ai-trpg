// web/apps/web/src/pages/trpg/portraits/ScenarioCover.tsx
// 시나리오의 표지 그림(#1164). 공개 소개의 그림(GET /listings/{scenario_id}/portraits/{cover_image_id}/image)을 토큰을 실어 받는다
// (성인 등급의 표지는 img 의 주소만으로 받지 못한다). 표지가 없거나 받지 못하면 빈 칸이다(장식이라 읽는 프로그램에는 숨긴다).
//   - useCoverUrl: 받은 그림의 주소(없으면 null). 홍보 배너처럼 제 모양으로 그리는 곳이 쓴다
//   - ScenarioCover: 정해 준 class 의 img(없으면 같은 class 의 빈 칸)

import { useQuery } from '@tanstack/react-query';
import { listingPortraitImageQuery } from './portraitQueries';
import { useBlobUrl } from './useBlobUrl';

export function useCoverUrl(scenarioId: string, coverImageId: string | null | undefined): string | null {
  const image = useQuery({ ...listingPortraitImageQuery(scenarioId, coverImageId ?? ''), enabled: Boolean(coverImageId) });
  return useBlobUrl(coverImageId ? image.data : undefined);
}

type Props = { scenarioId: string; coverImageId: string | null | undefined; className: string };

export function ScenarioCover({ scenarioId, coverImageId, className }: Props) {
  const url = useCoverUrl(scenarioId, coverImageId);
  return url ? <img src={url} alt="" className={className} /> : <span className={`${className} ${className}--empty`} aria-hidden="true" />;
}
