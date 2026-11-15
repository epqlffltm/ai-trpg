// web/apps/web/src/layout/SidebarRecent.tsx
// 왼쪽 메뉴 열의 "최근 대화". TRPG 테이블, 캐릭터 대화, 스토리를 한 목록으로 섞어 최근 것부터 보인다(서비스로 묶지 않는다).
// 줄마다 둥근 표식(이름의 첫 글자), 이름, 둘째 줄(상대나 상태), 오른쪽 위에 때, 오른쪽 아래에 종류 칩.
// 읽기는 첫 화면(pages/home/queries.ts)과 같은 열쇠라 한 번 읽은 것을 함께 쓴다.
// 로그인 전에는 안내와 로그인 단추만 둔다(부르지 않는다). 다시 동의나 탈퇴 유예 중(토큰이 인증 서버에만 통한다)에도 부르지 않는다.
// 셋 가운데 하나를 읽지 못하면 읽은 것만 보이고 아래에 한 줄로 알린다.
// 내 채팅 화면(pages/conversations)도 같은 줄(useRecentRows, RecentList)을 쓴다.

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { isLimited } from '../api/session';
import { useSession } from '../auth/useSession';
import { useNow } from '../hooks/useNow';
import { tableStatusLabel } from '../pages/home/labels';
import { myConversationsQuery, myStorySessionsQuery, myTablesQuery } from '../pages/home/queries';
import { mergeRecent, RECENT_KIND_LABELS, RECENT_ROWS, relativeTime, type RecentRow } from './sidebarRecentView';

export function SidebarRecent() {
  const session = useSession();
  return (
    <section className="sidebar-recent" aria-labelledby="sidebar-recent-heading">
      <h2 id="sidebar-recent-heading" className="sidebar-recent__title">
        최근 대화
      </h2>
      {session && isLimited(session) ? null : session ? <SidebarRecentRows /> : <SignedOutRecent />}
    </section>
  );
}

function SignedOutRecent() {
  return (
    <div className="sidebar-recent__signed-out">
      <p className="hint">로그인하고 이어서 하기</p>
      <Link to="/login" className="sidebar-recent__login">
        로그인
      </Link>
    </div>
  );
}

function SidebarRecentRows() {
  const recent = useRecentRows(RECENT_ROWS);
  return <RecentList recent={recent} label="최근 대화 목록" empty="아직 대화가 없어요." />;
}

export type RecentState = { rows: RecentRow[]; pending: boolean; failed: boolean };

/** 셋을 읽어 한 목록으로 섞는다. 하나라도 읽는 중이면 pending, 하나라도 읽지 못했으면 failed(읽은 것은 rows 에 있다) */
export function useRecentRows(limit: number): RecentState {
  const tables = useQuery(myTablesQuery());
  const conversations = useQuery(myConversationsQuery());
  const sessions = useQuery(myStorySessionsQuery());
  const tableRows: RecentRow[] = (tables.data?.items ?? []).map((table) => ({
    id: `trpg-${table.id}`,
    kind: 'trpg',
    to: `/trpg/tables/${table.id}`,
    name: table.title,
    detail: `${tableStatusLabel(table.status)} · ${table.member_count}/${table.capacity}명`,
    at: table.created_at ?? '',
  }));
  const conversationRows: RecentRow[] = (conversations.data?.items ?? []).map((conversation) => ({
    id: `character-${conversation.id}`,
    kind: 'character',
    to: `/chat/conversations/${conversation.id}`,
    name: conversation.title,
    detail: conversation.character.name,
    at: conversation.updated_at,
  }));
  const sessionRows: RecentRow[] = (sessions.data?.items ?? []).map((session) => ({
    id: `story-${session.id}`,
    kind: 'story',
    to: `/story/sessions/${session.id}`,
    name: session.title,
    detail: session.world.name,
    at: session.updated_at,
  }));
  return {
    rows: mergeRecent([tableRows, conversationRows, sessionRows], limit),
    pending: tables.isPending || conversations.isPending || sessions.isPending,
    failed: tables.isError || conversations.isError || sessions.isError,
  };
}

type ListProps = { recent: RecentState; label: string; empty: string };

/** 섞은 줄의 목록. 읽는 중, 비었음, 일부를 읽지 못함을 한 줄로 알린다 */
export function RecentList({ recent, label, empty }: ListProps) {
  const now = useNow(60_000);
  const { rows, pending, failed } = recent;
  if (pending && rows.length === 0) return <p className="hint">불러오는 중</p>;
  return (
    <>
      {rows.length === 0 && !failed ? <p className="hint">{empty}</p> : null}
      {rows.length > 0 ? (
        <ul className="plain-list sidebar-recent__list" aria-label={label}>
          {rows.map((row) => (
            <li key={row.id}>
              <Link to={row.to} className="sidebar-recent__row" aria-label={rowLabel(row, now)}>
                <span className="sidebar-recent__mark" aria-hidden="true">
                  {row.name.slice(0, 1)}
                </span>
                <span className="sidebar-recent__name">{row.name}</span>
                <span className="sidebar-recent__time">{row.at ? relativeTime(row.at, now) : ''}</span>
                <span className="sidebar-recent__detail">{row.detail}</span>
                <span className={`sidebar-recent__kind sidebar-recent__kind--${row.kind}`}>{RECENT_KIND_LABELS[row.kind]}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {failed ? <p className="hint">일부를 불러오지 못했어요.</p> : null}
    </>
  );
}

/** 화면 읽기 프로그램이 읽는 줄의 이름: "이름, 둘째 줄, 종류, 때" */
function rowLabel(row: RecentRow, now: number): string {
  return [row.name, row.detail, RECENT_KIND_LABELS[row.kind], row.at ? relativeTime(row.at, now) : ''].filter(Boolean).join(', ');
}
