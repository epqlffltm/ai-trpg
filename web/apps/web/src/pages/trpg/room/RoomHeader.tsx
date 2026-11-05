// web/apps/web/src/pages/trpg/room/RoomHeader.tsx
// 테이블 방의 머리(Stitch 20번의 테이블 줄). 제목, 상태, 사람 수, 지금 장(장이 있는 판, #481), 시나리오(소개로), 서술 모델,
// 스트림의 상태, 기록 받기(시작한 뒤), 방장에게만 "테이블 관리"(누르면 그 아래에 방장의 운영을 펼친다), 나가기.
// 장은 엔진이 넘긴다. 넘어가면 이벤트(chapter_changed)가 오고 테이블을 다시 읽어 바뀐다. 다음 장의 이름은 서버가 주지 않는다.

import { Button } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { ChapterOut, TableDetail } from '../../../api/types';
import { tableStatusLabel } from '../../home/labels';
import { narrationModelsQuery } from '../queries';
import { HOST_PANEL_ID } from './host/HostPanel';
import { LeaveButton } from './LeaveButton';
import { TranscriptButton } from './transcript/TranscriptButton';
import type { StreamStatus } from './useTableStream';

type Props = {
  table: TableDetail;
  stream: StreamStatus;
  /** 테이블 관리를 펼칠 수 있으면 그 상태와 바꾸는 함수. 방장이 아니면 null */
  manage: { open: boolean; toggle: () => void } | null;
};

export function RoomHeader({ table, stream, manage }: Props) {
  return (
    <header className="page-head room__head">
      <div>
        <h1>{table.title}</h1>
        <p className="hint">
          {tableStatusLabel(table.status)} · {table.member_count}/{table.capacity}명 ·{' '}
          {table.chapter ? <span className="room__chapter">{chapterLabel(table.chapter)} · </span> : null}
          <Link to={`/trpg/scenarios/${table.scenario_id}`}>시나리오 소개</Link>
          {table.status === 'recruiting' ? null : <NarrationModelName table={table} />}
        </p>
      </div>
      <div className="room__head-actions">
        <StreamBadge stream={stream} />
        {table.status === 'recruiting' ? null : <TranscriptButton tableId={table.id} title={table.title} />}
        {manage ? (
          <Button variant="secondary" aria-expanded={manage.open} aria-controls={HOST_PANEL_ID} onClick={manage.toggle}>
            테이블 관리
          </Button>
        ) : null}
        {table.status === 'ended' ? null : <LeaveButton tableId={table.id} />}
      </div>
    </header>
  );
}

/** 테이블 줄의 서술 모델 이름. 모델 목록을 읽지 못하면 슬러그, 고르지 않았으면 서버의 기본 모델이다 */
function NarrationModelName({ table }: { table: TableDetail }) {
  const models = useQuery(narrationModelsQuery());
  const name = models.data?.models.find((model) => model.slug === table.narration_model)?.display_name;
  return <> · 서술 {name ?? table.narration_model ?? '서버의 기본 모델'}</>;
}

/** 지금 장. "2장: 숲 (2/3)" */
export function chapterLabel(chapter: ChapterOut): string {
  return `${chapter.number}장: ${chapter.name} (${chapter.number}/${chapter.total})`;
}

/** 실시간으로 받고 있는지. 끊겨 다시 붙는 중이면 알린다(그동안의 것은 다시 붙으면 온다) */
function StreamBadge({ stream }: { stream: StreamStatus }) {
  const label = streamLabel(stream);
  if (!label) return null;
  return (
    <span className="stream-badge" role="status">
      {label}
    </span>
  );
}

export function streamLabel(stream: StreamStatus): string | null {
  switch (stream.state) {
    case 'connecting':
      return '연결하는 중';
    case 'open':
      return null;
    case 'reconnecting':
      return `연결이 끊겨 ${Math.ceil(stream.inMs / 1000)}초 뒤에 다시 붙습니다`;
    case 'stopped':
      return stream.reason === 'table_ended' ? null : '실시간 연결이 끝났습니다';
  }
}
