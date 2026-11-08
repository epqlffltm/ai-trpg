// billing-server/internal/attendance/attendance.go

// Package attendance 는 출석의 실버에 붙이는 지급의 이름이다.
//
// 출석과 보물 상자는 인증 서버로 옮겼다(2026-11-08 결정, auth-server/accounts/attendance.py). 누가 언제 출석했는지,
// 주기의 며칠째인지, 하루 양과 상자의 실버는 인증 서버가 정한다. 이 서버는 지갑에 넣기만 한다
// (POST /service/grants/attendance, httpapi/attendance_grant.go).
// 이 서버가 지키는 것은 "한 사용자, 한 날짜에 하루 양 한 번, 상자 한 번"이다. 지갑이 같은 이름을 두 번 주지 않는다.
// 이름은 이 서버가 출석을 맡던 때(#339)와 같다. 그때 받은 날을 다시 받지 못한다.
package attendance

import "time"

// GrantKey 는 그날의 하루 양에 붙이는 지급의 이름이다. day 는 한국 날짜다(0시 UTC 의 시각).
func GrantKey(day time.Time) string { return "attendance-" + day.Format("20060102") }

// ChestGrantKey 는 그날 연 보물 상자의 실버에 붙이는 지급의 이름이다.
func ChestGrantKey(day time.Time) string { return "chest-" + day.Format("20060102") }
