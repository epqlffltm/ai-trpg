// web/apps/web/src/pages/settings/ListingFilterSection.tsx
// 설정(A12)의 "목록 거르기"(#986, #987). 로그인했을 때만 보인다. 값은 인증 서버의 내 정보에 있어 기기를 바꿔도 같다.
//   - 성인 작품 표시: 성인 확인을 한 사람만 바꾼다. 끄면 공개 목록에서 성인용이 빠진다. 머리의 "19"와 같은 값이다.
//   - 성향: 전체, 남성향, 여성향. 고르면 그 태그가 붙은 작품만 보인다.
// 고르면 바로 저장하고 답을 내 정보에 넣는다. 그러면 공개 목록이 다시 읽힌다(ListingPreferencesSync).

import { Checkbox, Notice, SelectField } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateContentSettings, type ContentSettings } from '../../api/account';
import type { Me } from '../../api/types';
import { meQuery } from '../../auth/queries';
import { putQueryData } from '../../queryClient';

const ORIENTATION_OPTIONS = [
  ['all', '전체'],
  ['male', '남성향'],
  ['female', '여성향'],
] as const;

export function ListingFilterSection() {
  const me = useQuery(meQuery());
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!me.data) return null;
  const settings = me.data.content_settings ?? {};

  async function save(changes: Partial<ContentSettings>) {
    setSaving(true);
    setFailed(false);
    try {
      const next = await updateContentSettings(changes);
      await putQueryData<Me>(queryClient, meQuery().queryKey, (current) => (current ? { ...current, content_settings: next } : current));
    } catch {
      setFailed(true);
    }
    setSaving(false);
  }

  return (
    <section className="page-section" aria-labelledby="listing-filter-heading">
      <h2 id="listing-filter-heading">목록 거르기</h2>
      <p className="hint">내 정보에 저장되어 다른 기기에서도 같습니다.</p>
      {failed ? <Notice>저장하지 못했습니다. 잠시 뒤에 다시 해 보세요.</Notice> : null}
      {me.data.identity?.adult_content ? (
        <Checkbox
          label="성인 작품 표시"
          description="끄면 공개 목록과 검색에서 성인용 작품이 빠집니다."
          checked={settings.show_adult_content !== false}
          disabled={saving}
          onChange={(event) => void save({ show_adult_content: event.target.checked })}
        />
      ) : (
        <p className="hint">성인 작품은 본인인증으로 성인 확인을 마치면 보입니다.</p>
      )}
      <SelectField
        label="성향"
        hint="고르면 그 태그가 붙은 작품만 보입니다."
        value={settings.orientation ?? 'all'}
        disabled={saving}
        onChange={(event) => void save({ orientation: event.target.value as ContentSettings['orientation'] })}
      >
        {ORIENTATION_OPTIONS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </SelectField>
    </section>
  );
}
