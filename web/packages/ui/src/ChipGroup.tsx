// web/packages/ui/src/ChipGroup.tsx
// 하나만 고르는 칩의 줄(장르, 인원 같은 거르기). 고른 칩은 aria-pressed 다. 이미 고른 것을 다시 누르면 고르지 않은 것이 된다.
// 무엇이 있고 무엇을 골랐는지는 쓰는 쪽이 정한다.

export type Chip<T extends string | number> = { value: T; label: string };

export type ChipGroupProps<T extends string | number> = {
  /** 화면 읽기 프로그램이 읽는 줄의 이름(장르, 인원) */
  label: string;
  chips: Chip<T>[];
  selected: T | undefined;
  /** 고른 값. 다시 눌러 풀었으면 undefined */
  onChange: (value: T | undefined) => void;
};

export function ChipGroup<T extends string | number>({ label, chips, selected, onChange }: ChipGroupProps<T>) {
  return (
    <div role="group" aria-label={label} className="ui-chip-group">
      {chips.map((chip) => {
        const pressed = chip.value === selected;
        return (
          <button
            key={chip.value}
            type="button"
            className="ui-chip"
            aria-pressed={pressed}
            onClick={() => onChange(pressed ? undefined : chip.value)}
          >
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}
