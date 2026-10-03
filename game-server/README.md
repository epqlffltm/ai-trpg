# 게임 서버

[![game-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml)

[ai-trpg](../README.md)의 게임 서버. 방, 자산(세계관, 시나리오, 규칙 등), 판정, AI GM을 맡는다. FastAPI로 만든다.
회원가입과 로그인은 하지 않는다. [인증 서버](../auth-server/README.md)가 발급한 토큰을 공개키로 검증만 한다.

지금은 뼈대만 있다. 서버가 뜨고, 살아 있는지 확인하는 주소가 응답한다.

## 목차

- [실행](#실행)
- [API](#api)
- [CI](#ci)
- [설계 메모](#설계-메모)

## 실행

명령은 저장소 루트에서 시작한다고 보고 적었다.

### 설치와 실행

```
cd game-server
cp .env.example .env
uv sync
uv run uvicorn app.main:app --port 8001 --reload
```

인증 서버가 8000번을 쓰므로 8001번으로 띄운다. `http://127.0.0.1:8001/health`가 `{"status":"ok"}`를 돌려주면 정상이다.

`.env`의 `DEBUG=true`는 API 문서 화면을 켠다. `http://127.0.0.1:8001/api/v1/game/docs`에서 본다.

### 테스트와 검사

```
cd game-server
uv run pytest
uv run ruff check .
uv run ruff format .
```

`ruff check`는 쓰지 않는 import나 정의되지 않은 이름 같은 문제를 실행하지 않고 찾는다.
`ruff format`은 코드의 모양을 정해진 규칙으로 맞춘다. 커밋하기 전에 둘 다 돌린다.

## API

게임 서버의 API는 `/api/v1/game/` 아래에 놓는다. 아직 없다.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| GET | `/health` | 서버가 살아 있는지 확인 | 불필요 |

`/health`는 API 주소 밖에 둔다. 프록시와 컨테이너 관리 도구가 부르는 주소라 버전이 없다.

## CI

PR과 `main` 푸시마다 GitHub Actions가 게임 서버를 검사한다. `game-server/`나 워크플로 파일이 바뀐 경우에만 돈다.

1. 의존성 설치 (`uv sync --locked`): `uv.lock`과 `pyproject.toml`이 어긋나면 실패한다
2. 린트 (`ruff check`)
3. 모양 검사 (`ruff format --check`): 고치지 않고 검사만 한다
4. 테스트 (`pytest`)

## 설계 메모

**앱을 함수로 만든다(`create_app`).** 모듈을 불러올 때 바로 만들면 설정이 그 순간에 고정된다.
함수로 두면 테스트가 설정을 바꿔 가며 앱을 여러 개 만들 수 있다.

**설정은 `pydantic-settings`로 읽는다.** 값의 형식을 검사해서, 잘못된 설정이면 서버가 뜨기 전에 오류가 난다.
`.env`는 인증 서버와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
테스트는 `.env`를 읽지 않는다. 개발자의 `.env`에 무엇이 적혀 있든 결과가 같아야 한다.

**API 문서 화면은 기본이 꺼짐이다.** 켜는 것을 잊으면 불편할 뿐이지만, 끄는 것을 잊으면 운영 서버의 API 구조가 드러난다.
문서 화면의 주소도 `/api/v1/game/` 아래에 둔다. 프록시가 주소 앞부분으로 서버를 가르기 때문이다.

**`/health`는 프로세스가 살아 있는지만 본다.** DB까지 확인하면, DB가 잠깐 느려졌을 때 관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.

**린트와 모양 검사를 처음부터 CI에 넣는다.** 코드가 쌓인 뒤에 넣으면 지적이 한꺼번에 나와 고치는 일이 따로 생긴다.
따옴표는 인증 서버와 같이 작은따옴표로 맞춘다.

**테스트는 서버를 띄우지 않고 앱에 요청을 바로 넘긴다.** 네트워크를 거치지 않아 빠르고, 포트가 겹칠 일이 없다.
