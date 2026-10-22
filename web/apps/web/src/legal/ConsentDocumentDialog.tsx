// web/apps/web/src/legal/ConsentDocumentDialog.tsx
// 동의 문서 하나를 창으로 보인다. 가입, 다시 동의, 마이페이지의 "보기"가 함께 쓴다.
// 문서는 처음 열 때 받는다(LegalDocument 를 나눠 빌드한다). 창의 아래에 동작(동의하기 같은 것)을 둘 수 있다.

import { Dialog } from '@ai-trpg/ui';
import { lazy, Suspense, type ReactNode } from 'react';

const LegalDocument = lazy(() => import('./LegalDocument'));

/** 보일 문서. label 은 창의 제목, name 은 documents/<name>.md */
export type ViewingDocument = { label: string; name: string };

type Props = {
  viewing: ViewingDocument | null;
  onClose: () => void;
  /** 문서 아래에 둘 것(동의 단추). 없으면 읽기만 한다 */
  footer?: ReactNode;
};

export function ConsentDocumentDialog({ viewing, onClose, footer }: Props) {
  return (
    <Dialog title={viewing?.label ?? ''} open={viewing !== null} onClose={onClose}>
      {viewing ? (
        <>
          <Suspense fallback={<p>불러오는 중</p>}>
            <LegalDocument name={viewing.name} />
          </Suspense>
          {footer ? <div className="actions dialog-footer">{footer}</div> : null}
        </>
      ) : null}
    </Dialog>
  );
}
