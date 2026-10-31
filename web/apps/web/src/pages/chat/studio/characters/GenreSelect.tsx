// web/apps/web/src/pages/chat/studio/characters/GenreSelect.tsx
// 장르 고르기 칸. 캐릭터와 세계관의 만들기와 기본 탭(C6, D7)이 함께 쓴다.
// 장르는 반드시 하나다. 아직 고르지 않은 것(만들기의 처음)은 빈 값이고, 그때는 "장르를 고르세요"만 보인다(고를 수 없는 줄).

import { SelectField } from '@ai-trpg/ui';
import type { AssetGenre } from '../../../../api/types';
import { GENRE_VALUES, genreName, isGenreValue } from '../../../../genres/genres';

type Props = {
  value: AssetGenre | '';
  error: string | undefined;
  onChange: (genre: AssetGenre) => void;
  /** 테마가 바뀌는 화면의 이름("대화", "장면") */
  where: string;
};

export function GenreSelect({ value, error, onChange, where }: Props) {
  return (
    <SelectField
      label="장르"
      name="genre"
      value={value}
      onChange={(event) => {
        if (isGenreValue(event.target.value)) onChange(event.target.value);
      }}
      error={error}
      hint={`반드시 하나를 고릅니다. 장르마다 ${where} 화면과 소개 화면의 모양이 다릅니다. 남성향·여성향은 태그로 적으세요.`}
    >
      {value === '' ? (
        <option value="" disabled>
          장르를 고르세요
        </option>
      ) : null}
      {GENRE_VALUES.map((genre) => (
        <option key={genre} value={genre}>
          {genreName(genre)}
        </option>
      ))}
    </SelectField>
  );
}
