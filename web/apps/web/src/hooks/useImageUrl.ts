// web/apps/web/src/hooks/useImageUrl.ts
// 그림 하나를 토큰을 실어 받아 화면에 띄울 주소(blob:)로 바꾼다. 화면이 사라지면 주소를 놓는다.
// 그림은 바뀌지 않으므로(고치면 새 id) 한 번 받은 것은 다시 받지 않는다.
// 프록시 없이 띄운 개발 환경에서는 본문이 비어 주소가 없다(null).

import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { fetchImage } from '../api/images';

export function imageKey(imageId: string) {
  return ['asset', 'image', imageId] as const;
}

export function useImageUrl(imageId: string | null): { url: string | null; failed: boolean } {
  const query = useQuery({
    queryKey: imageKey(imageId ?? ''),
    queryFn: ({ signal }) => fetchImage(imageId as string, signal),
    enabled: imageId !== null,
    staleTime: Infinity,
  });
  const blob = query.data;
  // 받은 바이트로 주소를 만들고, 바이트가 바뀌거나 화면이 사라지면 놓는다
  const url = useMemo(() => (blob && blob.size > 0 ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  return { url: imageId === null ? null : url, failed: query.isError };
}
