// web/apps/web/src/pages/trpg/portraits/useBlobUrl.ts
// 받은 그림의 바이트를 화면에 띄울 주소(blob:)로 바꾼다. 바이트가 바뀌거나 화면이 사라지면 주소를 놓는다.
// 프록시 없이 띄운 개발 환경처럼 본문이 비어 있으면 주소가 없다(null).

import { useEffect, useMemo } from 'react';

export function useBlobUrl(blob: Blob | undefined): string | null {
  const url = useMemo(() => (blob && blob.size > 0 ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);
  return url;
}
