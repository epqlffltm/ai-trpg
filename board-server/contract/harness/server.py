# board-server/contract/harness/server.py

"""
시험할 게시판 서버를 바깥 프로세스로 띄운다. 어떤 구현이든 같은 환경 변수로 띄운다.

  BOARD_SERVER_COMMAND  서버를 띄우는 명령. 기본은 지금의 서버(빌드한 NestJS, "node dist/main.js")
  BOARD_SERVER_DIR      명령을 돌리는 폴더. 기본은 이 폴더의 위(board-server)

서버에는 서버가 원래 읽는 환경 변수만 준다(PORT, HOST, DATABASE_URL, DB_SCHEMA, AUTH_JWKS_URL, AUTH_SERVER_SECRET).
다시 쓸 서버도 같은 이름을 읽어야 이 시험이 돈다. 알림 서버는 부르지 않는다(주소를 주지 않는다).
"""

import os
import shlex
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_COMMAND = 'node dist/main.js'
DEFAULT_DIR = Path(__file__).resolve().parents[2]
# 서버가 뜰 때까지 기다리는 상한(초). 빌드한 앱이 DB 에 붙고 마이그레이션을 확인하는 데 걸린다
STARTUP_SECONDS = 60
# 뜬 것을 확인하는 주소. 서버가 요청을 받기 시작하면 200 이다
HEALTH_PATH = '/health'
# 서버가 지우는 환경 변수. 개발자의 환경에 남은 값이 시험을 바꾸지 않게 한다
CLEARED_VARIABLES = (
    'NOTIFICATION_URL',
    'NOTIFICATION_SECRET',
    'AUTH_SESSION_REVOCATIONS_URL',
    'JWT_ISSUER',
    'JWT_AUDIENCE',
    'OTEL_EXPORTER_OTLP_ENDPOINT',
    'APP_VERSION',
)


@dataclass
class RunningServer:
    """띄운 서버. base_url 로 부른다. 서버의 출력은 log_path 에 쌓인다."""

    process: subprocess.Popen[bytes]
    base_url: str
    log_path: Path

    def log(self) -> str:
        return self.log_path.read_text(encoding='utf-8', errors='replace')

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def free_port() -> int:
    """비어 있는 포트 하나."""
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def server_environment(port: int, database_url: str, schema: str, jwks_url: str, secret: str) -> dict[str, str]:
    """서버에 줄 환경 변수. 지금 환경에서 시험을 바꿀 값은 지운다."""
    environment = {key: value for key, value in os.environ.items() if key not in CLEARED_VARIABLES}
    environment.update(
        {
            'PORT': str(port),
            'HOST': '127.0.0.1',
            'DATABASE_URL': database_url,
            'DB_SCHEMA': schema,
            'AUTH_JWKS_URL': jwks_url,
            'AUTH_SERVER_SECRET': secret,
            'APP_ENVIRONMENT': 'development',
            'LOG_LEVEL': 'warning',
        }
    )
    return environment


def wait_until_up(server: RunningServer) -> None:
    """서버가 요청을 받을 때까지 기다린다. 먼저 끝나 버리면 출력과 함께 실패한다."""
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if server.process.poll() is not None:
            raise RuntimeError(f'게시판 서버가 뜨지 못하고 끝났다:\n{server.log()}')
        try:
            if httpx.get(f'{server.base_url}{HEALTH_PATH}', timeout=1).status_code == httpx.codes.OK:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.2)
    server.stop()
    raise RuntimeError(f'게시판 서버가 {STARTUP_SECONDS}초 안에 뜨지 않았다:\n{server.log()}')


def start_server(database_url: str, schema: str, jwks_url: str, secret: str) -> RunningServer:
    """서버를 띄우고 뜰 때까지 기다린다."""
    command = shlex.split(os.environ.get('BOARD_SERVER_COMMAND', DEFAULT_COMMAND))
    folder = Path(os.environ.get('BOARD_SERVER_DIR', DEFAULT_DIR))
    port = free_port()
    log_path = Path(tempfile.mkstemp(prefix='board-contract-', suffix='.log')[1])
    with log_path.open('wb') as log:
        process = subprocess.Popen(
            command,
            cwd=folder,
            env=server_environment(port, database_url, schema, jwks_url, secret),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    server = RunningServer(process=process, base_url=f'http://127.0.0.1:{port}', log_path=log_path)
    wait_until_up(server)
    return server
