# web/Dockerfile
# 프록시(nginx)의 이미지. 화면을 빌드해 nginx 에 담는다. docker-compose.yml 의 proxy 가 이것으로 뜬다(#290).
#
# 단계 둘로 나눈다.
#   build   : 잠금 파일 그대로 깔고 화면을 빌드한다(apps/web/dist)
#   runtime : 지금까지 쓰던 nginx-unprivileged 에 빌드한 정적 파일만 담는다. Node 는 담지 않는다
#
# nginx 의 설정은 담지 않는다. compose 가 docker/nginx/templates 를 붙이고(로컬), staging 이 그 위에 staging 의 것을 붙인다.
# 설정을 고치면 이미지를 다시 만들지 않아도 된다. 화면을 고치면 다시 만든다(docker compose up -d --build).

FROM node:24-trixie-slim AS build
WORKDIR /web
# 의존성부터 깐다. package.json 과 잠금 파일이 그대로면 이 층을 다시 쓴다
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY packages/ui/package.json packages/ui/
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY . .
# 충전의 결제창(A7). 결제 서버에 꽂힌 결제 대행사(PAYMENT_PROVIDER)에 맞춘다. 지금은 fake(시험용 결제창)뿐이다.
# 토스페이먼츠를 꽂은 결제 서버 앞에 둘 화면은 toss 결제창을 더한 뒤 빌드할 때 바꾼다(apps/web/src/pages/charge/paymentGateway.ts)
ARG VITE_PAYMENT_GATEWAY=fake
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30-alpine3.24 AS runtime
# 이미지에 든 기본 쪽(/usr/share/nginx/html 의 index.html, 50x.html)과 섞이지 않게 따로 둔다. api.inc 의 root 가 이곳이다.
# 파일의 주인은 root 로 둔다. nginx(101)는 읽기만 한다. 뚫려도 화면을 고쳐 쓰지 못한다
COPY --from=build /web/apps/web/dist /usr/share/nginx/web
