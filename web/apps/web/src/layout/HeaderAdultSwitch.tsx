// web/apps/web/src/layout/HeaderAdultSwitch.tsx
// 머리의 "19" 스위치(#986). 성인 확인을 한 사람에게만 보인다. 누르면 공개 목록에 성인 작품을 보일지 바꾼다.
// 설정은 인증 서버의 내 정보에 있어 기기를 바꿔도 같다. 설정 화면(A12)의 "성인 작품 표시"와 같은 값이다.
// 바꾸지 못하면 그대로 둔다(다음에 내 정보를 읽을 때 서버의 값이다). 모양은 밝기 고르기의 단추를 그대로 쓴다.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateContentSettings } from '../api/account';
import type { Me } from '../api/types';
import { meQuery } from '../auth/queries';
import { putQueryData } from '../queryClient';

export function HeaderAdultSwitch() {
  const me = useQuery(meQuery());
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  if (!me.data?.identity?.adult_content) return null;
  const shown = me.data.content_settings?.show_adult_content !== false;

  async function toggle() {
    setBusy(true);
    try {
      const settings = await updateContentSettings({ show_adult_content: !shown });
      await putQueryData<Me>(queryClient, meQuery().queryKey, (current) => (current ? { ...current, content_settings: settings } : current));
    } catch {
      // 서버의 값이 그대로다. 단추도 그대로 둔다
    }
    setBusy(false);
  }

  return (
    <div className="theme-switch">
      <button
        type="button"
        className="theme-switch__option"
        aria-pressed={shown}
        aria-label="성인 작품 표시"
        title={shown ? '성인 작품을 보이는 중' : '성인 작품을 숨기는 중'}
        disabled={busy}
        onClick={() => void toggle()}
      >
        19
      </button>
    </div>
  );
}
