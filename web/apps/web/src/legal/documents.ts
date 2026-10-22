// web/apps/web/src/legal/documents.ts
// 문서의 글을 필요할 때만 불러온다. 문서마다 따로 나뉘어 빌드되므로 첫 화면이 문서를 함께 받지 않는다.

const LOADERS = import.meta.glob<string>('./documents/*.md', { query: '?raw', import: 'default' });

/** 문서의 글(마크다운). 화면이 갖지 않은 문서면 오류다 */
export async function loadLegalDocument(name: string): Promise<string> {
  const load = LOADERS[`./documents/${name}.md`];
  if (!load) throw new Error(`화면에 없는 문서: ${name}`);
  return load();
}
