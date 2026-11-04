// web/apps/web/src/pages/wallet/tossCard.test.ts
// 토스페이먼츠의 카드 등록 창에 넘기는 것과 돌아온 주소를 읽는 것. 순수한 함수다(SDK 는 부르지 않는다).

import { describe, expect, it } from "vitest";
import {
  CARD_RETURN_PATH,
  cardRegistrationRequest,
  cardReturnFailureText,
  readCardReturn,
} from "./tossCard";

const CUSTOMER_KEY = "6b1c7c2e-2b0b-4d7e-9a1d-1f5f0c8a9b11";

describe("카드 등록 창", () => {
  it("카드, 같은 화면으로 돌아오기, 현재 창", () => {
    expect(cardRegistrationRequest("https://trpg.example")).toEqual({
      method: "CARD",
      successUrl: `https://trpg.example${CARD_RETURN_PATH}`,
      failUrl: `https://trpg.example${CARD_RETURN_PATH}`,
      windowTarget: "self",
    });
  });
});

describe("돌아온 주소", () => {
  const read = (query: string) => readCardReturn(new URLSearchParams(query));

  it("성공이면 인증 키와 고객 키를 읽는다", () => {
    expect(read(`customerKey=${CUSTOMER_KEY}&authKey=bln_a1B2-c3`)).toEqual({
      kind: "registered",
      authKey: "bln_a1B2-c3",
      customerKey: CUSTOMER_KEY,
    });
  });

  it("모양이 틀리면 읽지 않는다", () => {
    expect(read("authKey=bln_a1").kind).toBe("unreadable");
    expect(read("customerKey=me&authKey=bln_a1").kind).toBe("unreadable");
    expect(
      read(
        `customerKey=${CUSTOMER_KEY}&authKey=${encodeURIComponent("bln a1")}`,
      ).kind,
    ).toBe("unreadable");
    expect(
      read(`customerKey=${CUSTOMER_KEY}&authKey=${"a".repeat(301)}`).kind,
    ).toBe("unreadable");
    expect(read("").kind).toBe("unreadable");
  });

  it("실패면 코드만 읽는다", () => {
    expect(
      read(
        `code=PAY_PROCESS_CANCELED&message=${encodeURIComponent("아무 글")}`,
      ),
    ).toEqual({ kind: "failed", code: "PAY_PROCESS_CANCELED" });
    expect(read(`code=${encodeURIComponent("<i>")}`)).toEqual({
      kind: "failed",
      code: null,
    });
  });

  it("실패의 글은 화면의 말이다", () => {
    expect(cardReturnFailureText("PAY_PROCESS_CANCELED")).toBe(
      "카드 등록을 그만두었습니다.",
    );
    expect(cardReturnFailureText("REJECT_CARD_COMPANY")).toMatch(/카드사가/);
    expect(cardReturnFailureText(null)).toMatch(/등록하지 못했습니다/);
  });
});
