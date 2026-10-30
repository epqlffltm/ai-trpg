// web/apps/web/src/layout/HeaderTheme.tsx
// 머리의 밝기 고르기. 기기 설정을 따름(시스템), 밝게(라이트), 어둡게(다크) 셋을 나란히 두고 누르면 바로 바꾼다.
// 설정 화면(A12)의 밝기와 같은 값이다(settingsStore). 이 브라우저에만 두고 서버는 모른다. 로그인하지 않아도 보인다.

import { THEMES, themeLabel, type Theme } from '../settings/settings';
import { updateSettings } from '../settings/settingsStore';
import { useSettings } from '../settings/useSettings';

/** 단추에 보일 작은 그림 글자. 이름은 aria-label 과 title 이 맡는다 */
const THEME_MARKS: Record<Theme, string> = { system: '◐', light: '☀', dark: '☾' };

export function HeaderTheme() {
  const { settings } = useSettings();
  return (
    <div className="theme-switch" role="group" aria-label="밝기">
      {THEMES.map((theme) => (
        <button
          key={theme}
          type="button"
          className="theme-switch__option"
          aria-pressed={settings.theme === theme}
          aria-label={`밝기: ${themeLabel(theme)}`}
          title={themeLabel(theme)}
          onClick={() => updateSettings({ theme })}
        >
          <span aria-hidden="true">{THEME_MARKS[theme]}</span>
        </button>
      ))}
    </div>
  );
}
