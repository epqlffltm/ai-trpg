// web/apps/web/src/layout/ServiceScreens.tsx
// 점검과 장애의 화면(Stitch 8번의 둘째, 셋째). 사이트의 틀 없이 로고만 위에 두고 가운데에 알린다(설계서: "점검·장애는 틀 없이 로고만").
//   - 점검: 프록시가 점검의 503 을 답했을 때. 제목 "점검 중입니다", 점검 시간(알면), 프록시가 준 글, 안심의 한 줄, "다시 시도"(새로 고침)
//   - 장애: 처음 열 때 로그인을 되살리지 못했을 때(서버에 닿지 못함, 5xx). 제목 "잠시 연결할 수 없습니다", 안심의 한 줄, "다시 시도", 요청 번호
// 점검 중에는 게시판도 닫혀 있어 시안의 "공지 보기"는 두지 않는다. 점검의 글은 점검 파일의 detail 에 적는다.

import { Button } from '@ai-trpg/ui';
import type { ReactNode } from 'react';
import type { Maintenance } from '../api/maintenance';
import { maintenanceWindow, requestIdOf } from './maintenanceView';
import { SiteBrand } from './SiteBrand';

export function MaintenanceScreen({ maintenance }: { maintenance: Maintenance }) {
  const when = maintenanceWindow(maintenance);
  return (
    <ServiceFrame>
      <h1>점검 중입니다</h1>
      {when ? <p className="service-screen__window">{when}</p> : null}
      <p>{maintenance.detail}</p>
      <p className="hint">남은 크레딧과 진행 중인 판은 안전하게 보관됩니다.</p>
      <Button variant="secondary" onClick={() => location.reload()}>
        다시 시도
      </Button>
    </ServiceFrame>
  );
}

export function OutageScreen({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const requestId = requestIdOf(error);
  return (
    <ServiceFrame>
      <h1>잠시 연결할 수 없습니다</h1>
      <p>서버가 잠시 답하지 않습니다. 크레딧과 진행 중인 판은 안전합니다.</p>
      <Button onClick={onRetry}>다시 시도</Button>
      {requestId ? <p className="hint">계속되면 고객센터에 요청 번호를 알려 주세요: {requestId}</p> : null}
    </ServiceFrame>
  );
}

function ServiceFrame({ children }: { children: ReactNode }) {
  return (
    <div className="service-screen">
      <header className="service-screen__head">
        <SiteBrand />
      </header>
      <main className="page page--narrow service-screen__body">{children}</main>
    </div>
  );
}
