// web/packages/ui/src/Notice.tsx
// 화면 위의 안내 한 줄. 오류는 화면 읽기 프로그램이 바로 읽고(alert), 그 밖에는 차례가 오면 읽는다(status).

import type { ReactNode } from 'react';

export type NoticeTone = 'info' | 'error';

export function Notice({ tone = 'info', children }: { tone?: NoticeTone; children: ReactNode }) {
  return (
    <div className={`ui-notice ui-notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}
