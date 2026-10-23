// web/apps/web/src/pages/chat/studio/lorebooks/lorebookPaths.ts
// chat 의 로어북 만들기의 주소. /chat/studio/lorebooks(내 로어북), /new(만들기), /:lorebookId(고치기).

export const LOREBOOKS_PATH = '/chat/studio/lorebooks';
export const NEW_LOREBOOK_PATH = `${LOREBOOKS_PATH}/new`;

export function lorebookPath(lorebookId: string): string {
  return `${LOREBOOKS_PATH}/${lorebookId}`;
}
