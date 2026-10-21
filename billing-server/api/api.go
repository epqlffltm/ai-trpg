// billing-server/api/api.go

// Package api 는 결제 서버의 API 목록(OpenAPI, openapi.yaml)을 프로그램 안에 싣고 읽는다(#560).
//
// 목록은 손으로 쓴다. 코드와 어긋나지 않게 HTTP 테스트(internal/httpapi)가 이것으로 응답을 검사하고,
// 라우터의 주소와 목록의 주소가 같은지 본다. 저장소의 docs/api/billing.openapi.json 은 cmd/openapi 가 이것을 JSON 으로 낸 것이다.
package api

import (
	"context"
	_ "embed"

	"github.com/getkin/kin-openapi/openapi3"
)

// Spec 은 openapi.yaml 의 글 그대로다.
//
//go:embed openapi.yaml
var Spec []byte

// Load 는 목록을 읽고 OpenAPI 의 규칙(참조가 닿는지, 모양이 맞는지)에 맞는지 본다.
func Load(ctx context.Context) (*openapi3.T, error) {
	loader := openapi3.NewLoader()
	doc, err := loader.LoadFromData(Spec)
	if err != nil {
		return nil, err
	}
	if err := doc.Validate(ctx); err != nil {
		return nil, err
	}
	return doc, nil
}
