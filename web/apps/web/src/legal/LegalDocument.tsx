// web/apps/web/src/legal/LegalDocument.tsx
// 동의 문서 하나를 그린다. 마크다운을 React 의 요소로 바꾼다(react-markdown). HTML 을 그대로 넣지 않는다.
// 문서 안의 링크(다른 문서, 작성자용의 절)는 화면에서 갈 곳이 없어 글로만 둔다.
// 변호사 검토 전의 초안이라 맨 위에 그렇게 알린다. 확정되면 판을 올리며 이 줄을 뺀다.
// 이 파일은 나뉘어 빌드되어(lazy) 문서를 처음 열 때 받는다. react-markdown 도 그때 받는다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { loadLegalDocument } from './documents';

const DRAFT_NOTICE = '검토 중인 초안입니다. 서비스를 열기 전에 확정합니다.';

export default function LegalDocument({ name }: { name: string }) {
  const document = useQuery({ queryKey: ['legal', name], queryFn: () => loadLegalDocument(name), staleTime: Infinity });
  if (document.isPending) return <p>불러오는 중</p>;
  if (document.isError) return <Notice tone="error">문서를 불러오지 못했습니다. 새로 고쳐 주세요.</Notice>;
  return (
    <article className="legal-document">
      <Notice>{DRAFT_NOTICE}</Notice>
      <Markdown remarkPlugins={[remarkGfm]} components={{ a: ({ children }) => <span>{children}</span> }}>
        {document.data}
      </Markdown>
    </article>
  );
}
