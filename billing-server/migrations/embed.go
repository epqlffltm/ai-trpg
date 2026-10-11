// billing-server/migrations/embed.go

// Package migrations 는 마이그레이션 SQL 파일들을 실행 파일 안에 담는다.
//
// 파일을 실행 파일에 넣어 두면 어느 폴더에서 돌리든 같은 파일이 적용된다.
// 파일을 적용하는 일은 internal/migrate 가 한다.
package migrations

import "embed"

// Files 는 이 폴더의 SQL 파일 전부다. 이름의 앞 숫자 순서대로 적용된다.
//
//go:embed *.sql
var Files embed.FS
