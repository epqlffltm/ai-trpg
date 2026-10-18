# 문서 안내

서버마다의 설명서는 각 서버 폴더의 README 에 있다. 이 폴더에는 **여러 서버가 함께 지키는 규격**과 **저장소 전체의 구조와 방향**을 둔다.

| 문서 | 내용 |
| --- | --- |
| [observability.md](observability.md) | 서버들이 함께 지키는 관측 규격. 로그의 모양, 요청·추적·작업 식별자, 민감정보, health 와 readiness, 메트릭의 이름, 관리 서버의 경계 |
| [architecture/services.md](architecture/services.md) | 서비스 구조 명세. 서버 목록과 계획, 나누는 기준, 서비스 사이의 길, 토큰, 데이터, 이름 규칙, 서비스를 더할 때 고칠 곳, 열린 질문 |
| [architecture/shared-code.md](architecture/shared-code.md) | 공용 코드 규칙. 형식과 코드는 공유하고 데이터는 공유하지 않는다. 공유 후보, 언제 뽑는지, 버전과 CI |
| [product/platform.md](product/platform.md) | 플랫폼과 제품 방향. 제품 셋(TRPG, chat, story), 원칙, 화면과 모바일의 방향, 정하지 않은 것 |
| [product/screens.md](product/screens.md) | 화면 명세의 목차 초안. 흐름, 화면 목록, 화면마다 채울 칸, 공통 상태, 첫 출시의 범위 |
| [product/market-research.md](product/market-research.md) | 다른 AI 캐릭터 챗 서비스를 본 조사. 만드는 구조, 돈을 받는 방식, 반복되는 문제 |

## 쓰는 법

- **구현된 것**과 **계획인 것**, 정한 것과 정하지 않은 것을 나눠 적는다. 계획은 확정이 아니다.
- 규격의 원본은 한 곳에 둔다. 다른 문서는 원본을 가리키기만 하고 같은 내용을 다시 적지 않는다. 둘이 다르면 원본이 맞다.
- 서버를 더하거나 서버 사이의 길을 바꾸면 [서비스 구조 명세](architecture/services.md)를 먼저 고친다.
- 칸의 이름이나 뜻을 바꾸는 변경은 해당 규격 문서부터 고치고, 영향받는 서버를 함께 고친다.
