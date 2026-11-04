// web/apps/web/src/api/follows.ts
// 제작자 팔로우(#989). 알림 서버가 가진다. 제작자는 인증 서버의 공개 ID 다.
//   - GET, PUT, DELETE /me/follows/{creator_id}: 내가 팔로우하는지와 팔로워 수({following, follower_count}). 두 번 해도 같다
//     자기 자신이면 422(follow_self), 1,000명을 넘으면 409(follow_limit)
//   - GET /me/follows: 내 팔로잉. 최근에 한 것부터(limit, offset)
//   - GET /creators/{creator_id}/followers: 팔로워 수. 로그인하지 않아도 된다

import type { components } from './generated/notification';
import { apiRequest } from './http';

export type FollowState = components['schemas']['FollowState'];
export type FollowingPage = components['schemas']['FollowingPage'];
export type FollowerCount = components['schemas']['FollowerCount'];

const MINE = '/api/v1/notification/me/follows';

/** 내 팔로잉의 한 쪽에 싣는 수(서버는 1~100) */
export const FOLLOWING_PAGE_SIZE = 20;

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

function followPath(creatorId: string): string {
  return `${MINE}/${encodeURIComponent(creatorId)}`;
}

export function fetchFollow(creatorId: string, signal?: AbortSignal): Promise<FollowState> {
  return apiRequest<FollowState>(followPath(creatorId), withSignal(signal));
}

/** following 이 참이면 팔로우하고, 거짓이면 끊는다 */
export function setFollow(creatorId: string, following: boolean): Promise<FollowState> {
  return apiRequest<FollowState>(followPath(creatorId), { method: following ? 'PUT' : 'DELETE' });
}

/** 내 팔로잉의 한 쪽. offset 은 앞에서 받은 수다 */
export function fetchFollowing(offset: number, signal?: AbortSignal): Promise<FollowingPage> {
  return apiRequest<FollowingPage>(MINE, { query: { limit: FOLLOWING_PAGE_SIZE, offset }, ...withSignal(signal) });
}

export function fetchFollowerCount(creatorId: string, signal?: AbortSignal): Promise<FollowerCount> {
  return apiRequest<FollowerCount>(`/api/v1/notification/creators/${encodeURIComponent(creatorId)}/followers`, withSignal(signal));
}
