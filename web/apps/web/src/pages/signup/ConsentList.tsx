// web/apps/web/src/pages/signup/ConsentList.tsx
// 동의 항목(#450). 필수와 선택을 나눠 보이고, 항목마다 한 줄 요약과 "보기"(그 판의 문서)를 둔다. 미리 체크하지 않는다.
// 문서는 처음 열 때 받는다(ConsentDocumentDialog).

import { Button, Checkbox } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { ConsentDocument } from '../../api/signup';
import { ConsentDocumentDialog, type ViewingDocument } from '../../legal/ConsentDocumentDialog';
import { consentDocumentName, consentItemInfo } from '../../legal/consentItems';

type Props = {
  documents: ConsentDocument[];
  agreed: Record<string, boolean>;
  onChange: (item: string, agreed: boolean) => void;
};

export function ConsentList({ documents, agreed, onChange }: Props) {
  const [viewing, setViewing] = useState<ViewingDocument | null>(null);
  const close = useCallback(() => setViewing(null), []);
  const required = documents.filter((document) => document.required);
  const optional = documents.filter((document) => !document.required);

  function row(document: ConsentDocument) {
    const info = consentItemInfo(document.item);
    const name = consentDocumentName(document.item, document.version);
    return (
      <div key={document.item} className="consent-row">
        <Checkbox
          label={`${document.required ? '[필수]' : '[선택]'} ${info.label}`}
          description={`${info.summary} (${document.version}판, ${document.effective_on} 시행)`}
          checked={Boolean(agreed[document.item])}
          onChange={(event) => onChange(document.item, event.target.checked)}
        />
        {name ? (
          <Button variant="quiet" onClick={() => setViewing({ label: info.label, name })}>
            보기
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <fieldset className="consents">
      <legend>동의</legend>
      {required.map(row)}
      {optional.length > 0 ? <p className="consents__group">선택 항목은 동의하지 않아도 가입할 수 있습니다.</p> : null}
      {optional.map(row)}
      <ConsentDocumentDialog viewing={viewing} onClose={close} />
    </fieldset>
  );
}

