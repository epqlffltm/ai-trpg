# 문서 안내

서버마다의 설명서는 각 서버 폴더의 README 에 있다. 이 폴더에는 **여러 서버가 함께 지키는 규격**과 **저장소 전체의 구조와 방향**을 둔다.

| 문서 | 내용 |
| --- | --- |
| [observability.md](observability.md) | 서버들이 함께 지키는 관측 규격. 로그의 모양, 요청·추적·작업 식별자, 민감정보, health 와 readiness, 메트릭의 이름, 관리 서버의 경계 |
| [architecture/services.md](architecture/services.md) | 서비스 구조 명세. 서버 목록과 계획, 나누는 기준, 서비스 사이의 길, 토큰, 데이터, 이름 규칙, 서비스를 더할 때 고칠 곳, 열린 질문 |
| [architecture/operators.md](architecture/operators.md) | 운영자 권한. 누가 운영자인가(토큰의 `roles`), 서비스마다 운영자가 더 할 수 있는 것, 감사 기록, 사용자에게 알릴 것, 순서 |
| [architecture/deployment.md](architecture/deployment.md) | 배포 설계. 첫 배포(운영자 혼자 쓰는 서버)의 클라우드, 막는 법, 환경 이름, TLS 와 인증서, 모델, 올리는 방식, 비밀, 백업(age 로 잠가 S3 에, 주마다 풀어 보기), 지켜보기, VM 준비 순서 |
| [operations/staging-vm.md](operations/staging-vm.md) | staging VM 준비. 배포 설계의 "VM 준비 순서"를 실제 명령으로. AWS, VM 의 기본, Docker, Tailscale, 열쇠, `.env`(`tools/staging_env.py`), 첫 인증서, 띄우기, 확인 |
| [architecture/chat-server.md](architecture/chat-server.md) | chat 서버 설계. chat(1:1), story-server 와 나눈 선과 함께 쓰는 코드, 권한의 선, 자산 가져오기, 데이터의 모양, 장소와 소지품, 그림, 과금, 기억, 성인 콘텐츠, 만드는 순서 |
| [architecture/asset-server.md](architecture/asset-server.md) | asset 서버 설계. 맡는 것, 계정 페르소나(TRPG 의 시트와 나누기), 게시와 판, 그림(올리기의 격리, 권한을 보고 nginx 가 내주기), 쓰는 서비스에 내주기, 만드는 순서 |
| [architecture/story.md](architecture/story.md) | story 서버 설계. 열린 세계와 기한, 시각, 인물의 위치와 여러 인물의 말, 이벤트와 선택지, 조건과 효과, 호감도, 고백과 엔딩, 세션과 기록 |
| [architecture/shared-code.md](architecture/shared-code.md) | 공용 코드 규칙. 형식과 코드는 공유하고 데이터는 공유하지 않는다. `shared/` 의 패키지(`server-core`, `ai-core`, `conversation-core`), 재정의하는 법, 언제 누가 뽑는지, 버전과 CI, `app/ai` 를 뽑는 방식의 결정(#380) |
| [api/README.md](api/README.md) | 서버마다의 API 목록(OpenAPI). 파일, 뽑는 법, 누가 부르는가(`x-audience`), CI |
| [product/platform.md](product/platform.md) | 플랫폼과 제품 방향. 제품 셋(TRPG, chat, story), 원칙, 화면과 모바일의 방향, 정하지 않은 것 |
| [product/screens.md](product/screens.md) | 화면 명세. 흐름, 화면 목록, 화면별 명세(A1~A12, B1~B10, C1~C7, D1~D7), 공통 상태, 프런트 구조, 첫 출시의 범위(세 단계) |
| [legal/terms.md](legal/terms.md), [legal/privacy.md](legal/privacy.md) | 이용약관과 개인정보 처리방침의 초안(#450). 변호사 검토 전이다. 정할 것과 검토할 것, 본문의 근거(저장소의 어디인지) |
| [product/market-research.md](product/market-research.md) | 다른 AI 캐릭터 챗 서비스를 본 조사. 만드는 구조, 돈을 받는 방식, 반복되는 문제 |

## 쓰는 법

- **구현된 것**과 **계획인 것**, 정한 것과 정하지 않은 것을 나눠 적는다. 계획은 확정이 아니다.
- 규격의 원본은 한 곳에 둔다. 다른 문서는 원본을 가리키기만 하고 같은 내용을 다시 적지 않는다. 둘이 다르면 원본이 맞다.
- 서버를 더하거나 서버 사이의 길을 바꾸면 [서비스 구조 명세](architecture/services.md)를 먼저 고친다.
- 칸의 이름이나 뜻을 바꾸는 변경은 해당 규격 문서부터 고치고, 영향받는 서버를 함께 고친다.
