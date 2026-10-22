// web/apps/web/src/pages/trpg/tables/useEnterTable.ts
// 테이블에 들어갔거나 만들었을 때의 뒤처리. 읽어 둔 테이블 목록(로비, 내 테이블, 첫 화면의 이어하기)을 버리고 테이블 방(B6)으로 간다.
// 뒤로 가기로 만들기나 들어가기의 화면에 돌아오지 않게 주소를 바꾼다(replace).

import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useNavigate } from 'react-router';

export function tablePath(tableId: string): string {
  return `/trpg/tables/${tableId}`;
}

export function useEnterTable(): (tableId: string) => void {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useCallback(
    (tableId: string) => {
      void queryClient.invalidateQueries({ queryKey: ['trpg', 'tables'] });
      navigate(tablePath(tableId), { replace: true });
    },
    [queryClient, navigate],
  );
}
