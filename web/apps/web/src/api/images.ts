// web/apps/web/src/api/images.ts
// asset 서버의 그림(#566). 올리기는 그림 파일의 바이트를 그대로 보낸다(multipart 가 아니다).
// 서버가 형식을 파일의 머리로 고르고, 따로 된 프로세스에서 열어 다시 인코딩한다(EXIF 같은 것이 지워진다).
// 받기는 토큰을 실어 바이트로 받는다. 초안의 그림은 주인만 볼 수 있고, img 는 Authorization 을 싣지 못한다.

import { apiBlob, apiRequest } from './http';
import type { AssetImage } from './types';

const IMAGES = '/api/v1/asset/images';

export function uploadImage(file: Blob): Promise<AssetImage> {
  return apiRequest<AssetImage>(IMAGES, { method: 'POST', file });
}

/** 그림의 바이트. 볼 수 없으면 404. 프록시 없이 부르면 빈 본문이다 */
export function fetchImage(imageId: string, signal?: AbortSignal): Promise<Blob> {
  return apiBlob(`${IMAGES}/${imageId}`, signal ? { signal } : {});
}
