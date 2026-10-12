// board-server/src/authors/recent-nicknames.ts

/**
 * 이 서버가 최근에 DB 에 적은 닉네임을 기억한다. 같은 이름을 요청마다 다시 적지 않으려는 것이다.
 *
 * 서버의 메모리에만 둔다. 서버를 다시 띄우면 비고, 서버가 여러 대면 저마다 따로 기억한다.
 * 그래도 틀리지 않는다. 기억에 없으면 DB 에 한 번 더 적을 뿐이고, DB 는 이름이 같으면 고치지 않는다.
 * 기억하는 사람 수에 끝을 둔다. 끝에 닿으면 통째로 비운다. 메모리가 한없이 늘지 않게 하는 가장 단순한 방법이다.
 */

export class RecentNicknames {
  private readonly remembered = new Map<string, string>();

  constructor(private readonly maxSize: number) {}

  /** 이 사람의 이름을 이 값으로 이미 적었는가. */
  has(userId: string, nickname: string): boolean {
    return this.remembered.get(userId) === nickname;
  }

  /** 이 사람의 이름을 이 값으로 적었다고 기억한다. */
  remember(userId: string, nickname: string): void {
    if (!this.remembered.has(userId) && this.remembered.size >= this.maxSize) {
      this.remembered.clear();
    }
    this.remembered.set(userId, nickname);
  }

  /** 모두 잊는다. */
  clear(): void {
    this.remembered.clear();
  }

  /** 기억하는 사람의 수. */
  get size(): number {
    return this.remembered.size;
  }
}
