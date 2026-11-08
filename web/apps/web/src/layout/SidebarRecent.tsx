// web/apps/web/src/layout/SidebarRecent.tsx
// 왼쪽 메뉴 열의 "최근 대화"(Stitch 설계서의 [모든 화면의 틀]). 서비스마다 묶음 셋(TRPG 테이블, chat 대화, story 세션)이고
// 서비스끼리 섞어 정렬하지 않는다. 묶음마다 최근 것 세 줄(이름, 둘째 줄, 때)과 "전체 보기".
// 읽기는 첫 화면의 이어하기(pages/home/queries.ts)와 같은 열쇠라 한 번 읽은 것을 함께 쓴다.
// 로그인 전에는 안내 한 줄만 둔다(부르지 않는다). 다시 동의나 탈퇴 유예 중(토큰이 인증 서버에만 통한다)에도 부르지 않는다.
// 묶음 하나를 읽지 못하면 그 묶음에만 한 줄로 알린다.
// 서버의 목록에 마지막 말과 그림이 없어, 줄은 이름과 상대(캐릭터, 세계관) 또는 상태와 인원이다.
// 묶음 셋(RecentGroups)은 모바일 탭 바의 "대화"가 여는 최근 대화 화면(pages/conversations)도 줄 수만 달리해 함께 쓴다.

import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { isLimited } from '../api/session';
import { useSession } from '../auth/useSession';
import { useNow } from '../hooks/useNow';
import { tableStatusLabel } from '../pages/home/labels';
import { myConversationsQuery, myStorySessionsQuery, myTablesQuery } from '../pages/home/queries';
import { RECENT_ROWS, relativeTime } from './sidebarRecentView';

export function SidebarRecent() {
  const session = useSession();
  return (
    <section className="sidebar-recent" aria-labelledby="sidebar-recent-heading">
      <h2 id="sidebar-recent-heading" className="sidebar-recent__title">
        최근 대화
      </h2>
      {session && isLimited(session) ? null : session ? (
        <RecentGroups rowCount={RECENT_ROWS} />
      ) : (
        <p className="hint">로그인하면 최근 대화가 여기 보입니다.</p>
      )}
    </section>
  );
}

/** 서비스마다의 묶음 셋. 묶음마다 최근 것부터 rowCount 줄 */
export function RecentGroups({ rowCount }: { rowCount: number }) {
  return (
    <>
      <RecentTables rowCount={rowCount} />
      <RecentConversations rowCount={rowCount} />
      <RecentSessions rowCount={rowCount} />
    </>
  );
}

type Row = { id: string; to: string; name: string; detail: string; at?: string };

function RecentTables({ rowCount }: { rowCount: number }) {
  const query = useQuery(myTablesQuery());
  const rows: Row[] = (query.data?.items ?? []).slice(0, rowCount).map((table) => ({
    id: table.id,
    to: `/trpg/tables/${table.id}`,
    name: table.title,
    detail: `${tableStatusLabel(table.status)} · ${table.member_count}/${table.capacity}명`,
  }));
  return <RecentGroup label="TRPG 테이블" allTo="/trpg" rows={rows} pending={query.isPending} failed={query.isError} empty="앉아 있는 테이블이 없습니다." />;
}

function RecentConversations({ rowCount }: { rowCount: number }) {
  const query = useQuery(myConversationsQuery());
  const rows: Row[] = (query.data?.items ?? []).slice(0, rowCount).map((conversation) => ({
    id: conversation.id,
    to: `/chat/conversations/${conversation.id}`,
    name: conversation.title,
    detail: conversation.character.name,
    at: conversation.updated_at,
  }));
  return <RecentGroup label="chat 대화" allTo="/chat" rows={rows} pending={query.isPending} failed={query.isError} empty="아직 대화가 없습니다." />;
}

function RecentSessions({ rowCount }: { rowCount: number }) {
  const query = useQuery(myStorySessionsQuery());
  const rows: Row[] = (query.data?.items ?? []).slice(0, rowCount).map((session) => ({
    id: session.id,
    to: `/story/sessions/${session.id}`,
    name: session.title,
    detail: session.world.name,
    at: session.updated_at,
  }));
  return <RecentGroup label="story 세션" allTo="/story" rows={rows} pending={query.isPending} failed={query.isError} empty="아직 세션이 없습니다." />;
}

type GroupProps = { label: string; allTo: string; rows: Row[]; pending: boolean; failed: boolean; empty: string };

/** 서비스 하나의 묶음. 제목과 "전체 보기", 그 아래 줄들 */
function RecentGroup({ label, allTo, rows, pending, failed, empty }: GroupProps) {
  const now = useNow(60_000);
  let body: ReactNode;
  if (pending) body = <p className="hint">불러오는 중</p>;
  else if (failed) body = <p className="hint">불러오지 못했습니다.</p>;
  else if (rows.length === 0) body = <p className="hint">{empty}</p>;
  else
    body = (
      <ul className="plain-list sidebar-recent__list" aria-label={`최근 ${label}`}>
        {rows.map((row) => (
          <li key={row.id}>
            <Link to={row.to} className="sidebar-recent__row">
              <span className="sidebar-recent__name">{row.name}</span>
              <span className="sidebar-recent__detail">
                {row.detail}
                {row.at ? ` · ${relativeTime(row.at, now)}` : ''}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    );
  return (
    <div className="sidebar-recent__group">
      <p className="sidebar-recent__head">
        <span>{label}</span>
        <Link to={allTo}>전체 보기</Link>
      </p>
      {body}
    </div>
  );
}
