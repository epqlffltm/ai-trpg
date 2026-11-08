// web/apps/web/src/pages/trpg/room/round/checkDice.ts
// 판정의 숫자를 보일 글(#404). 판정의 결과, 판의 판정(넘기, 따기, 덫), 지난 테이블의 굴림이 함께 쓴다. 순수한 함수다.
//
//   - over: "눈 8, 보정 +1, 합 9 / 목표 15". 눈 + 보정이 목표 이상이면 성공이다
//   - under: "눈 34 ≤ 기량 45". 눈이 기량 이하이면 성공이다. 보정은 기량에 이미 들었다
//   - 주사위를 여럿 굴렸으면 눈 앞에 눈들을 붙인다("눈 3+4=7")
//   - 방식이 없는 옛 결과는 over 다(#404 전에는 over 뿐이었다)

export type RolledNumbers = {
  roll: number;
  modifier: number;
  total: number;
  target: number;
  success: boolean;
  style?: string | null;
  faces?: number[] | null;
};

function rollPart(check: Pick<RolledNumbers, 'roll' | 'faces'>): string {
  const faces = check.faces ?? [];
  return faces.length > 1 ? `${faces.join('+')}=${check.roll}` : String(check.roll);
}

function isUnder(check: Pick<RolledNumbers, 'style'>): boolean {
  return check.style === 'under';
}

/** 판정의 숫자 한 줄 */
export function checkDice(check: RolledNumbers): string {
  if (isUnder(check)) return `눈 ${rollPart(check)} ${check.success ? '≤' : '>'} 기량 ${check.target}`;
  const modifier = check.modifier >= 0 ? `+${check.modifier}` : String(check.modifier);
  return `눈 ${rollPart(check)}, 보정 ${modifier}, 합 ${check.total} / 목표 ${check.target}`;
}

/** 짧은 판정. over 는 "판정 20 / 20", under 는 "눈 34 ≤ 기량 45" */
export function checkShort(check: RolledNumbers): string {
  if (isUnder(check)) return checkDice(check);
  return `판정 ${check.total} / ${check.target}`;
}
