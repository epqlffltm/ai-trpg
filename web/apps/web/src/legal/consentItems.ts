// web/apps/web/src/legal/consentItems.ts
// 동의 항목마다 화면이 보일 이름, 한 줄 요약, 그 판의 문서(#450).
// 서버(GET /consents)는 항목과 판 번호만 준다. 문서의 글은 화면이 갖는다(documents/, npm run sync:legal).
// 선택 항목(마케팅, AI 학습)은 따로의 문서가 없어 개인정보 처리방침의 그 판을 보인다(처리하는 목적의 6, 7).
// 판을 올리면 DOCUMENTS 에 새 판을 더한다. 화면이 갖지 않은 판이면 가입을 막는다(옛 문서로 동의를 받지 않는다).

export type ConsentItemInfo = { label: string; summary: string };

const ITEMS: Record<string, ConsentItemInfo> = {
  terms: { label: '이용약관', summary: '서비스를 쓰는 규칙, 크레딧과 결제, 금지 행위와 이용 제한' },
  privacy: { label: '개인정보 수집·이용', summary: '가입과 결제, 서비스에 필요한 개인정보와 보관하는 기간' },
  marketing: { label: '마케팅 정보 수신', summary: '이벤트와 혜택을 메일로 받습니다' },
  ai_training: { label: '대화 기록의 AI 학습 이용', summary: '대화 기록을 AI 학습에 쓰는 것에 동의합니다' },
};

// 항목과 판 → 문서 파일의 이름(documents/<이름>.md)
const DOCUMENTS: Record<string, Record<number, string>> = {
  terms: { 1: 'terms-v1' },
  privacy: { 1: 'privacy-v1' },
  marketing: { 1: 'privacy-v1' },
  ai_training: { 1: 'privacy-v1' },
};

export function consentItemInfo(item: string): ConsentItemInfo {
  return ITEMS[item] ?? { label: item, summary: '' };
}

/** 그 항목의 그 판을 보일 문서의 이름. 화면이 갖지 않은 판이면 null */
export function consentDocumentName(item: string, version: number): string | null {
  return DOCUMENTS[item]?.[version] ?? null;
}

/** 화면이 그 판의 문서를 갖지 않은 항목. 있으면 가입을 막는다 */
export function itemsWithoutDocument(documents: { item: string; version: number }[]): string[] {
  return documents.filter((document) => consentDocumentName(document.item, document.version) === null).map((d) => d.item);
}
