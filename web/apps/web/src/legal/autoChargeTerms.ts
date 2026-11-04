// web/apps/web/src/legal/autoChargeTerms.ts
// 자동 충전 이용 동의(#980)의 판마다 문서. 판은 결제 서버가 준다(GET /auto-charge 의 terms.version).
// 문서의 글은 화면이 갖는다(documents/, npm run sync:legal). 판을 올리면 여기에 새 판을 더한다.
// 화면이 갖지 않은 판이면 켜지 못한다(옛 문서로 동의를 받지 않는다).

const DOCUMENTS: Record<number, string> = { 1: 'auto-charge-v1' };

/** 그 판을 보일 문서의 이름. 화면이 갖지 않은 판이면 null */
export function autoChargeDocumentName(version: number): string | null {
  return DOCUMENTS[version] ?? null;
}
