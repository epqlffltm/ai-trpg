// web/apps/web/src/pages/chat/studio/characters/GenreSelect.tsx
// 장르 고르기 칸. 캐릭터(C6)와 세계관(D7)의 기본 탭이 함께 쓴다. 하나를 고르거나 비워 둔다(비우면 기본 테마).

import { SelectField } from '@ai-trpg/ui';
import type { AssetGenre } from '../../../../api/types';
import { GENRE_VALUES, genreName, isGenreValue } from '../../../../genres/genres';

type Props = {
  value: AssetGenre | '';
  error: string | undefined;
  onChange: (genre: AssetGenre | '') => void;
  /** 테마가 바뀌는 화면의 이름("대화", "장면") */
  where: string;
};

export function GenreSelect({ value, error, onChange, where }: Props) {
  return (
    <SelectField
      label="장르(선택)"
      name="genre"
      value={value}
      onChange={(event) => onChange(isGenreValue(event.target.value) ? event.target.value : '')}
      error={error}
      hint={`하나를 고릅니다. ${where} 화면과 소개 화면의 분위기를 정하고, 고르지 않으면 기본 모양입니다. 남성향·여성향은 태그로 적으세요.`}
    >
      <option value="">고르지 않음</option>
      {GENRE_VALUES.map((genre) => (
        <option key={genre} value={genre}>
          {genreName(genre)}
        </option>
      ))}
    </SelectField>
  );
}
