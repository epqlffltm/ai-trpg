// billing-server/internal/jobs/heartbeat.go

package jobs

import (
	"errors"
	"os"
	"time"
)

// Beat 는 심장박동 파일의 시각을 지금으로 바꾼다. 없으면 만든다. path 가 비어 있으면 아무것도 하지 않는다(#258).
//
// 계속 도는 작업(cmd/sweeper)이 한 바퀴를 DB 에 닿아 끝낼 때마다 부른다. compose 의 healthcheck 가 그 시각을 본다.
// 그래서 작업의 healthy 는 "DB 에 닿으며 돈다"는 뜻이다. 인증 서버의 워커와 같은 모양이다(docs/observability.md 의 "워커의 상태").
func Beat(path string) error {
	if path == "" {
		return nil
	}
	now := time.Now()
	err := os.Chtimes(path, now, now)
	if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	return file.Close()
}
