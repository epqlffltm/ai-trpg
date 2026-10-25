// web/apps/web/src/pages/notifications/notificationText.ts
// 알림 하나를 화면의 한 줄과 누르면 갈 곳으로 바꾼다. 순수한 함수다. 서버는 문구를 주지 않는다(screens.md 의 A10).
// source 와 kind 를 함께 보고 고른다. 표에 없는 짝은 일반 문구다. payload 의 칸이 빠져도 깨지지 않는다.
// 제재와 신고 처리의 알림에는 사유가 없다(서버가 싣지 않는다). 게시판의 댓글과 답글은 그 글(A11)로 간다.

import type { AppNotification } from '../../api/types';
import { formatDate } from '../../format/dateTime';
import { goldAmount, wonLabel } from '../charge/chargeView';
import { dayLabel } from '../trpg/models/modelChoice';

export type NotificationLine = { text: string; to: string | null };

export type NoticeContext = {
  /** 서술 모델의 이름표를 보이는 이름으로. 모르면 이름표 그대로 */
  modelName: (slug: string) => string;
};

type Payload = Record<string, unknown>;
type Describe = (payload: Payload, ctx: NoticeContext) => NotificationLine;

const FALLBACK: NotificationLine = { text: '새 알림입니다', to: null };

function text(payload: Payload, key: string): string | undefined {
  const value = payload[key];
  if (typeof value === 'string' && value !== '') return value;
  return typeof value === 'number' ? String(value) : undefined;
}

function quoted(payload: Payload, key: string): string {
  const value = text(payload, key);
  return value ? `"${value}"` : '';
}

function path(prefix: string, payload: Payload, key: string): string | null {
  const id = text(payload, key);
  return id ? `${prefix}/${encodeURIComponent(id)}` : null;
}

function model(payload: Payload, ctx: NoticeContext, key = 'narration_model'): string {
  const slug = text(payload, key);
  return slug ? ctx.modelName(slug) : '서버의 기본 모델';
}

function tableTo(payload: Payload): string | null {
  return path('/trpg/tables', payload, 'table_id');
}

function tableName(payload: Payload): string {
  return quoted(payload, 'title') || '내';
}

function money(payload: Payload): string {
  const price = payload.price;
  const won = typeof price === 'number' ? wonLabel(price) : '';
  const credits = text(payload, 'credits');
  return [won, credits ? `골드 ${goldAmount(credits)}` : ''].filter(Boolean).join(' · ');
}

function retiring(payload: Payload, ctx: NoticeContext): NotificationLine {
  const day = text(payload, 'retires_on');
  const left = text(payload, 'days_left');
  const when = day ? `${dayLabel(day)}에 ` : '';
  return { text: `${tableName(payload)} 테이블의 서술 모델 ${model(payload, ctx)}: ${when}끝납니다${left ? `(${left}일 남음)` : ''}. 다른 모델을 고를 수 있습니다`, to: tableTo(payload) };
}

function sanctioned(payload: Payload): NotificationLine {
  const version = text(payload, 'version_number');
  const banned = payload.publishing_banned === true ? '. 지금은 시나리오를 공개할 수 없습니다' : '';
  return { text: `운영자가 시나리오 ${quoted(payload, 'title')}${version ? `(판 ${version})` : ''}에 조치했습니다${banned}`, to: path('/trpg/studio/scenarios', payload, 'scenario_id') };
}

function creditShort(payload: Payload): NotificationLine {
  const amount = text(payload, 'amount');
  const gold = payload.gold_required === true ? '. 프리미엄 모델은 골드로만 냅니다' : '';
  return { text: `크레딧이 모자라 서술 값을 걸지 못했습니다${amount ? `(${goldAmount(amount)})` : ''}${gold}`, to: '/wallet/charge' };
}

const LINES: Record<string, Describe> = {
  'game narration_model.retiring': retiring,
  'game narration_model.replaced': (p, ctx) => ({ text: `${tableName(p)} 테이블의 서술 모델을 바꿨습니다: ${model(p, ctx, 'from')} → ${model(p, ctx)}(앞의 모델이 끝남)`, to: tableTo(p) }),
  'game narration_model.unavailable': (p, ctx) => ({ text: `${tableName(p)} 테이블의 서술 모델 ${model(p, ctx)}: 쓸 수 없습니다. 모델을 골라야 서술합니다`, to: tableTo(p) }),
  'game scenario.sanctioned': sanctioned,
  'game publishing.banned': (p) => ({ text: `시나리오를 공개할 수 없게 되었습니다${p.automatic === true ? '(조치가 쌓여 저절로)' : ''}`, to: '/trpg/studio/scenarios' }),
  'game publishing.unbanned': () => ({ text: '시나리오를 다시 공개할 수 있습니다', to: '/trpg/studio/scenarios' }),
  'billing order.paid': (p) => ({ text: `충전했습니다: ${money(p)}`, to: path('/wallet/orders', p, 'order_id') }),
  'billing order.refunded': (p) => ({ text: `청약철회로 환불했습니다: ${money(p)}`, to: path('/wallet/orders', p, 'order_id') }),
  'billing credit.welcome': (p) => {
    const until = text(p, 'expires_at');
    return { text: `환영 실버를 받았습니다: 실버 ${goldAmount(text(p, 'amount') ?? '?')}${until ? ` · ${formatDate(until)}까지` : ''}`, to: '/wallet' };
  },
  'billing credit.expiring': (p) => {
    const from = text(p, 'first_expires_at');
    return { text: `실버가 곧 사라집니다: 실버 ${goldAmount(text(p, 'amount') ?? '?')}${from ? ` · ${formatDate(from)}부터` : ''}`, to: '/wallet' };
  },
  'billing credit.short': creditShort,
  'board post.commented': (p) => ({ text: `내 글 ${quoted(p, 'post_title')}에 댓글이 달렸습니다`, to: path('/board/posts', p, 'post_id') }),
  'board comment.replied': (p) => ({ text: `내 댓글에 답글이 달렸습니다: ${quoted(p, 'post_title')}`, to: path('/board/posts', p, 'post_id') }),
  'asset character.hidden': (p) => ({ text: `운영자가 캐릭터를 숨겼습니다: ${text(p, 'name') ?? '?'}. 공개 목록과 남의 새 대화에서 빠지고, 나는 계속 씁니다`, to: path('/chat/studio/characters', p, 'character_id') }),
  'asset character.unhidden': (p) => ({ text: `운영자가 캐릭터의 숨김을 풀었습니다: ${text(p, 'name') ?? '?'}`, to: path('/chat/studio/characters', p, 'character_id') }),
  'asset character_report.handled': (p) => ({ text: `신고한 캐릭터를 운영자가 처리했습니다: ${text(p, 'name') ?? '?'}`, to: null }),
  'chat message_report.handled': (p) => ({ text: `신고한 대화 속 답을 운영자가 처리했습니다: ${text(p, 'name') ?? '?'}`, to: null }),
};

export function describeNotification(notification: Pick<AppNotification, 'source' | 'kind' | 'payload'>, ctx: NoticeContext): NotificationLine {
  const describe = LINES[`${notification.source} ${notification.kind}`];
  return describe ? describe(notification.payload, ctx) : FALLBACK;
}

/** 서술 모델의 이름이 있어야 하는 알림인가(그때만 모델 목록을 읽는다) */
export function needsModelNames(notifications: Pick<AppNotification, 'source' | 'kind'>[]): boolean {
  return notifications.some((notification) => notification.source === 'game' && notification.kind.startsWith('narration_model.'));
}

/** 머리의 표시. 0 이면 비우고, 100 부터는 99+ */
export function badgeText(unread: number): string {
  if (unread <= 0) return '';
  return unread > 99 ? '99+' : String(unread);
}

const MUTE_LABELS: Record<string, string> = {
  'narration_model.retiring': '내 테이블의 서술 모델이 곧 끝남',
  'credit.expiring': '실버가 곧 사라짐',
  'credit.short': '크레딧이 모자라 서술 값을 걸지 못함',
  'post.commented': '내 글에 달린 댓글',
  'comment.replied': '내 댓글에 달린 답글',
};

/** 끌 수 있는 종류의 이름. 모르는 종류는 받은 그대로 */
export function muteLabel(kind: string): string {
  return MUTE_LABELS[kind] ?? kind;
}

/** 모두 읽음에 보낼 번호. 받은 것 가운데 가장 큰 번호(목록은 최근 것부터). 없으면 null */
export function newestId(notifications: Pick<AppNotification, 'id'>[]): number | null {
  return notifications.reduce<number | null>((max, notification) => (max === null || notification.id > max ? notification.id : max), null);
}
