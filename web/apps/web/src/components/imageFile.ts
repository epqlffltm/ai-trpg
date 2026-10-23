// web/apps/web/src/components/imageFile.ts
// 올릴 그림 파일을 보내기 전에 보고, 올리기의 실패를 글로 바꾼다. 순수한 함수다.
// 상한과 형식은 asset 서버와 같다(IMAGE_MAX_BYTES 의 기본 10MB, PNG·JPEG·WebP). 서버가 다시 본다.

import { ApiError } from '../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../auth/problem';

export const IMAGE_MAX_BYTES = 10 * 1024 * 1024;
export const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
/** 파일을 고르는 칸의 accept */
export const IMAGE_ACCEPT = IMAGE_TYPES.join(',');

const TOO_BIG = `그림은 ${IMAGE_MAX_BYTES / 1024 / 1024}MB 까지입니다.`;
const FORMAT = 'PNG, JPEG, WebP 그림만 올릴 수 있습니다.';

/** 보내기 전에 알 것. 괜찮으면 null. 형식은 브라우저가 알려 준 것만 본다(진짜 형식은 서버가 파일의 머리로 본다) */
export function imageFileProblem(file: { size: number; type: string }): string | null {
  if (file.size > IMAGE_MAX_BYTES) return TOO_BIG;
  if (file.type !== '' && !IMAGE_TYPES.includes(file.type)) return FORMAT;
  return null;
}

/** 올리기의 실패 */
export function describeUploadProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: '올리지 못했습니다.' };
  if (error.status === 413) return { message: TOO_BIG };
  if (error.status === 415) return { message: FORMAT };
  if (error.status === 422) return { message: '그림을 열 수 없습니다. 망가졌거나 너무 큰 그림입니다.' };
  if (error.status === 503) return { message: '그림 저장소를 쓸 수 없습니다. 잠시 뒤 다시 시도하세요.' };
  return unknownProblem(error, '올리지 못했습니다.');
}
