// web/apps/web/src/components/ShareAddress.tsx
// 링크 공개(#993)한 작품의 주소와 복사 단추. 목록에 나오지 않으니 이 주소를 나눠 연다.
// 복사가 막힌 브라우저면 글이 바뀌지 않는다(주소를 직접 고른다).

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import { shareAddress } from '../format/visibility';

export function ShareAddress({ path }: { path: string }) {
  const address = shareAddress(window.location.origin, path);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <p className="hint">
      링크 공개 주소 <code>{address}</code>{' '}
      <Button variant="quiet" onClick={() => void copy()}>
        {copied ? '복사했습니다' : '주소 복사'}
      </Button>
    </p>
  );
}
