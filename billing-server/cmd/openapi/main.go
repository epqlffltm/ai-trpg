// billing-server/cmd/openapi/main.go

// 결제 서버의 API 목록(api/openapi.yaml)을 JSON 으로 표준 출력에 낸다(#560). 서버를 띄우지 않고 DB 에도 닿지 않는다.
// 저장소 루트의 tools/export_openapi.py 가 이것을 불러 docs/api/billing.openapi.json 을 쓴다.
//
//	go run ./cmd/openapi
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/epqlffltm/ai-trpg/billing-server/api"
)

func main() {
	if err := run(context.Background(), os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// run 은 목록을 읽고 확인한 뒤 JSON 으로 out 에 쓴다. 키의 차례와 들여쓰기는 뽑는 도구가 다시 정한다.
func run(ctx context.Context, out io.Writer) error {
	doc, err := api.Load(ctx)
	if err != nil {
		return fmt.Errorf("api/openapi.yaml 을 읽지 못했다: %w", err)
	}
	return json.NewEncoder(out).Encode(doc)
}
