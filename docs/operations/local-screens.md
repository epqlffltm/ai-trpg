# 화면을 실제 서버로 보기

화면(`web/`)의 시험은 서버를 부르지 않는다(가짜 `fetch`). 실제 서버에 붙여 끝까지 보는 것은 PC 의 compose 로 손으로 한다.
끝에서 끝까지의 자동 시험(Playwright)은 라운드의 화면(B6 ③)이 생긴 뒤 CI 의 stack 에 붙인다(`docs/product/screens.md` 의 "시작할 때 정한 것").

공개된 시나리오와 계정 둘이 있어야 탐색, 로비, 테이블 방, 스트림을 볼 수 있다. 시나리오를 만드는 화면(B9)이 아직 없으므로
`tools/dev_seed.py` 가 시험 계정 둘, 공개된 견본 시나리오, 로비에 보이는 견본 테이블을 한 번에 채운다.

## 띄우고 채우기

저장소 루트에서. `.env` 는 [루트 README 의 실행](../../README.md#실행)대로 만들어 둔다.

```powershell
docker compose --profile app up -d --build
docker compose --profile app exec trpg-server python -m scripts.models sync
docker compose --profile app exec trpg-server python -m scripts.models list
docker compose --profile app exec trpg-server python -m scripts.models enable <list 에서 고른 이름표>
uv run --no-project python tools/dev_seed.py
```

- 서술 모델은 하나 이상 켜 둔다. 시나리오를 만들려면 추천 서술 모델이 있어야 한다. 모델이 없으면 `dev_seed.py` 가 위의 명령을 알린다.
  모델을 부르는 것(서술)은 라운드의 화면에서 본다. 지금 화면에서는 이름만 보인다.
- `dev_seed.py` 는 몇 번 돌려도 같다. 시나리오와 테이블은 이미 있으면 만들지 않고, 계정은 비밀번호만 다시 정한다.
  개발 환경(`APP_ENVIRONMENT=development`)이 아니면 계정을 만들지 않고 멈춘다. 이 PC 의 주소(127.0.0.1, localhost)만 받는다.
- 화면은 `http://127.0.0.1:8080` 이다(프록시의 이미지에 담긴 것). 화면을 고쳤으면 `docker compose --profile app up -d --build proxy`.
  개발 서버(`npm run dev`, 5173)로 볼 때는 [web/README.md 의 실행](../../web/README.md#실행)의 출처 설정을 한다.

## 로그인

- 계정은 `seed_host`(방장)와 `seed_guest`(손님)이다. 비밀번호는 `dev_seed.py` 가 찍는다(기본 `seed-pass-2026`).
- 로그인은 두 단계다. 메일 서버를 적지 않았으면 코드가 메일 대신 로그에 찍힌다: `docker compose --profile app logs -f auth-mail`
- 두 계정을 함께 보려면 다른 브라우저나 시크릿 창을 쓴다. 같은 브라우저의 창은 refresh 쿠키를 나눠 한 사람으로 보인다.

## 볼 것

화면마다 만든 PR 의 "알아 둘 것"에서 실제 서버로 보지 못한 것을 모았다.

| 화면 | 볼 것 |
| --- | --- |
| 로그인, 첫 화면(A1, A2) | 로그인 두 단계, 새로 고침 뒤에도 로그인이 남는가(refresh), 첫 화면의 이어하기와 공개 목록 |
| 가입, 비밀번호(A2) | 가입 세 단계와 동의, 비밀번호 재설정 메일의 링크(`PASSWORD_RESET_URL` 을 `http://localhost:8080/reset-password` 로) |
| 마이페이지(A5) | 계정, 비밀번호 바꾸기(다른 창이 로그아웃되는가), 모든 기기 로그아웃, 선택 동의 켜고 끄기 |
| 탐색, 소개(B1, B2) | 견본이 보이는가, 장르·인원·태그로 거르기, 만든 사람의 이름, 로그인 전후(추천 모델의 이름) |
| 테이블 만들기, 로비(B3, B4) | 만들기의 자세한 설정과 모델의 값, 손님이 로비에서 들어가기, 비밀번호 테이블, 초대 코드 |
| 테이블 방(B6 ①) | 두 창의 채팅이 서로 바로 오는가(스트림), 입력 중, 나가기, 방장의 시작(캐릭터를 정하는 화면은 다음이다) |
| 스트림이 끊길 때 | `docker compose --profile app restart trpg-server` 뒤에 몇 초 안에 다시 붙고, 그동안의 채팅이 빠지지 않는가 |

## 지우기

견본은 보통의 데이터다. 처음부터 다시 하려면 볼륨째 지운다(모든 로컬 데이터가 지워진다).

```powershell
docker compose --profile app down -v
```
