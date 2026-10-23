// web/apps/web/src/routing/chunkError.ts
// 나눠 빌드한 조각(/assets/*.js)을 받지 못한 오류인가. 순수한 함수다.
//
// 새로 올리면 예전 조각은 이미지에서 사라지고 /assets/ 는 없는 파일에 404 를 준다(docker/nginx/templates/web.inc.template).
// 예전 index.html 로 열어 둔 탭이 다른 화면으로 가면 이 오류가 난다. 새로 고치면 새 index.html 과 새 조각을 받는다.
// 브라우저마다 글이 다르다. Chrome·Edge, Safari, Firefox 의 것과, Vite 가 미리 받기(preload)에 실패했을 때의 것을 본다.

const CHUNK_ERRORS = [
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i,
  /error loading dynamically imported module/i,
  /Unable to preload CSS/i,
];

/** 조각을 받지 못한 오류면 true */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : '';
  return CHUNK_ERRORS.some((pattern) => pattern.test(message));
}
