// web/apps/web/src/components/imageFile.test.ts
// 올릴 그림 파일을 보내기 전에 보는 것과 올리기의 실패의 글.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../api/errors';
import { describeUploadProblem, IMAGE_MAX_BYTES, imageFileProblem } from './imageFile';

function apiError(status: number) {
  return new ApiError({ status, detail: '실패' });
}

describe('그림 파일', () => {
  it('10MB 와 PNG·JPEG·WebP. 형식을 모르면 서버에 맡긴다', () => {
    expect(imageFileProblem({ size: IMAGE_MAX_BYTES, type: 'image/png' })).toBeNull();
    expect(imageFileProblem({ size: IMAGE_MAX_BYTES + 1, type: 'image/png' })).toMatch(/10MB/);
    expect(imageFileProblem({ size: 10, type: 'image/gif' })).toMatch(/PNG, JPEG, WebP/);
    expect(imageFileProblem({ size: 10, type: '' })).toBeNull();
  });

  it('올리기의 실패', () => {
    expect(describeUploadProblem(apiError(413)).message).toMatch(/10MB/);
    expect(describeUploadProblem(apiError(415)).message).toMatch(/PNG/);
    expect(describeUploadProblem(apiError(422)).message).toMatch(/열 수 없습니다/);
    expect(describeUploadProblem(apiError(503)).message).toMatch(/저장소/);
    expect(describeUploadProblem(apiError(500)).message).toMatch(/올리지 못했습니다/);
    expect(describeUploadProblem(new NetworkError(new Error('x'))).message).toMatch(/닿지 못했습니다/);
    expect(describeUploadProblem('boom').message).toMatch(/처리하지 못했습니다|올리지 못했습니다/);
  });
});
