# 점검 파일

이 폴더에 `maintenance.json` 이 있으면 프록시(nginx)가 `/api/` 의 모든 요청에 `503` 과 그 파일을 답한다.
화면(SPA)은 그대로 열리고, 화면이 그 503 을 받아 점검 화면(Stitch 8번)을 띄운다. 서버들은 건드리지 않는다.

- 프록시는 요청마다 파일이 있는지 본다. 만들거나 지우면 바로 적용된다. 프록시를 다시 띄우거나 다시 읽힐 필요가 없다.
- 폴더는 컨테이너에 읽기 전용으로 붙는다(`docker-compose.yml` 의 proxy). 파일은 저장소에 올리지 않는다(`.gitignore`).
- 점검 중에도 컨테이너끼리의 요청(서버 → 서버)과 상태 확인은 프록시를 거치지 않으므로 그대로다.

## 켜고 끄기(VM, 저장소 폴더에서)

```
cp docker/nginx/maintenance/maintenance.json.example docker/nginx/maintenance/maintenance.json
# 글과 시간을 고친다(시간은 한국 시각 +09:00 을 붙인 ISO 8601, 모르면 그 칸을 지운다)
nano docker/nginx/maintenance/maintenance.json
# 끄기
rm docker/nginx/maintenance/maintenance.json
```

## 파일의 모양

```json
{"detail": "화면에 보일 글", "code": "maintenance", "starts_at": "2026-11-04T02:00:00+09:00", "ends_at": "2026-11-04T04:00:00+09:00"}
```

- `code` 는 반드시 `"maintenance"` 다. 화면은 이 값으로 점검과 서버의 다른 503 을 가른다.
- `starts_at`, `ends_at` 는 없어도 된다. 있으면 화면에 "언제부터 언제까지"가 보인다.
- JSON 이 깨지면 화면이 점검으로 알아보지 못한다(그래도 요청은 모두 503 이다). 만든 뒤 `python3 -m json.tool docker/nginx/maintenance/maintenance.json` 으로 확인한다.
