// web/apps/web/src/settings/settings.ts
// 화면 쪽 설정(A12)의 모양과 기본값. 서버는 모른다. 순수한 함수다.
//   - theme: 밝기. system 이면 기기의 설정을 따른다
//   - textSize: 글자 크기. 문서의 기본 크기를 바꾼다(모든 rem, em 이 함께 커진다)
//   - shortcuts: 테이블 방의 단축키(C, I, J, L). 끄면 문서 전체에서 듣지 않는다

export const THEMES = ['system', 'light', 'dark'] as const;
export const TEXT_SIZES = ['normal', 'large', 'larger'] as const;

export type Theme = (typeof THEMES)[number];
export type TextSize = (typeof TEXT_SIZES)[number];
export type Settings = { theme: Theme; textSize: TextSize; shortcuts: boolean };

export const DEFAULT_SETTINGS: Settings = { theme: 'system', textSize: 'normal', shortcuts: true };

function oneOf<T extends string>(values: readonly T[], value: unknown, fallback: T): T {
  return typeof value === 'string' && (values as readonly string[]).includes(value) ? (value as T) : fallback;
}

/** 저장해 둔 값을 읽는다. 모르는 칸이나 틀린 값은 기본값으로(옛 판이나 손으로 고친 값이 화면을 깨지 않게) */
export function parseSettings(raw: unknown): Settings {
  const value = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    theme: oneOf(THEMES, value.theme, DEFAULT_SETTINGS.theme),
    textSize: oneOf(TEXT_SIZES, value.textSize, DEFAULT_SETTINGS.textSize),
    shortcuts: typeof value.shortcuts === 'boolean' ? value.shortcuts : DEFAULT_SETTINGS.shortcuts,
  };
}

const THEME_LABELS: Record<Theme, string> = { system: '기기 설정을 따름', light: '밝게', dark: '어둡게' };
const TEXT_SIZE_LABELS: Record<TextSize, string> = { normal: '보통', large: '크게', larger: '아주 크게' };

export function themeLabel(theme: Theme): string {
  return THEME_LABELS[theme];
}

export function textSizeLabel(size: TextSize): string {
  return TEXT_SIZE_LABELS[size];
}
