// web/apps/web/src/hooks/useBlocks.ts
// 막은 제작자와 태그(#988)를 읽고 바꾼다. 막은 것은 내 정보(/me 의 blocks)에 있다.
// 바꾸면 답(바뀐 뒤의 전체)을 내 정보에 넣는다. 그러면 ListingPreferencesSync 가 목록에 실을 값을 고치고 공개 목록을 다시 읽는다.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { setCreatorBlock, setTagBlock, type Blocks } from '../api/blocks';
import { ApiError } from '../api/errors';
import type { Me } from '../api/types';
import { meQuery } from '../auth/queries';
import { putQueryData } from '../queryClient';

const EMPTY: Blocks = { creators: [], tags: [] };

export type BlockActions = {
  blocks: Blocks;
  busy: boolean;
  failure: string | null;
  setCreator: (publicId: string, blocked: boolean) => Promise<void>;
  setTag: (tag: string, blocked: boolean) => Promise<void>;
};

/** 실패의 글. 상한(409), 모양(400)은 그 까닭을 알린다 */
export function blockFailureText(error: unknown): string {
  if (error instanceof ApiError && error.code === 'block_limit') return '제작자는 100명, 태그는 30개까지 막을 수 있습니다.';
  if (error instanceof ApiError && error.code === 'invalid_tag') return '태그는 1~20자여야 합니다.';
  if (error instanceof ApiError && error.code === 'block_self') return '자기 자신은 막을 수 없습니다.';
  return '바꾸지 못했습니다. 잠시 뒤에 다시 해 보세요.';
}

export function useBlocks(): BlockActions {
  const queryClient = useQueryClient();
  const me = useQuery(meQuery());
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function run(change: () => Promise<Blocks>) {
    setBusy(true);
    setFailure(null);
    try {
      const blocks = await change();
      await putQueryData<Me>(queryClient, meQuery().queryKey, (current) => (current ? { ...current, blocks } : current));
    } catch (error) {
      setFailure(blockFailureText(error));
    }
    setBusy(false);
  }

  return {
    blocks: me.data?.blocks ?? EMPTY,
    busy,
    failure,
    setCreator: (publicId, blocked) => run(() => setCreatorBlock(publicId, blocked)),
    setTag: (tag, blocked) => run(() => setTagBlock(tag, blocked)),
  };
}
