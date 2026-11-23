package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func testRow(slug string) modelRow {
	value, _ := json.Marshal(slug)
	return modelRow{"slug": value}
}

func call(g http.Handler, method, path, body, token, primary string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	r.Header.Set("X-Route-Token", "Bearer "+token)
	if primary != "" {
		r.Header.Set("Authorization", "Bearer "+primary)
		r.Header.Set("ChatGPT-Account-ID", "native-workspace")
	}
	w := httptest.NewRecorder()
	g.ServeHTTP(w, r)
	return w
}

func TestCredentialsDestinationsAndReferences(t *testing.T) {
	var mu sync.Mutex
	var catalogHits, nativeHits, routeHits int
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		if r.Header.Get("X-Route-Token") != "" || r.Header.Get("Authorization") != "Bearer native" || r.Header.Get("ChatGPT-Account-ID") != "native-workspace" {
			t.Error("wrong native credential boundary")
		}
		if r.URL.Path == "/models" {
			catalogHits++
			io.WriteString(w, `{"models":[{"slug":"gpt-6.2-sol","display_name":"Native","priority":30,"test_extension":123}]}`)
			return
		}
		nativeHits++
		if r.URL.Path != "/responses" {
			t.Error("wrong native endpoint")
		}
		io.WriteString(w, "ok")
	}))
	defer native.Close()
	route := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		routeHits++
		if r.Header.Get("X-Route-Token") != "" || r.Header.Get("Authorization") != "Bearer project" || r.Header.Get("ChatGPT-Account-ID") != "" {
			t.Error("wrong Route credential boundary")
		}
		var doc modelRow
		if err := json.NewDecoder(r.Body).Decode(&doc); err != nil || field(doc, "model") != "gpt-6.2-sol" {
			t.Error("incorrect outgoing model")
		}
		if r.URL.Path != "/responses/compact" || !strings.Contains(string(doc["input"]), "opaque-fixture") {
			t.Error("lost compaction path or opaque input")
		}
		w.WriteHeader(403)
		io.WriteString(w, "project refused")
	}))
	defer route.Close()
	g, err := newGateway(config{GatewayToken: "local", RouteKey: "project", NativeURL: native.URL, RouteURL: route.URL, Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	p := "/v1/models?client_version=1"
	if call(g, "GET", p, "", "invalid", "native").Code != 401 || call(g, "POST", "/v1/responses", `{"model":"route-gpt-6.2-sol"}`, "invalid", "native").Code != 401 {
		t.Fatal("invalid token was accepted")
	}
	only := call(g, "GET", p, "", "local", "")
	if only.Code != 200 || strings.Contains(only.Body.String(), "Native") || !strings.Contains(only.Body.String(), "route-gpt-6.2-sol") {
		t.Fatal("key-only catalog incorrect")
	}
	if catalogHits != 0 || nativeHits != 0 || routeHits != 0 {
		t.Fatal("contacted an upstream before authentication")
	}
	w := call(g, "GET", p, "", "local", "native")
	if w.Code != 200 || !strings.Contains(w.Body.String(), `"test_extension":123`) || !strings.Contains(w.Body.String(), `"priority":31`) {
		t.Fatal("catalog metadata/order lost")
	}
	for _, body := range []string{`{"model":"route-unknown"}`, `{"model":"route-gpt-6.2-sol","previous_response_id":"resp_other"}`, `{"model":"route-gpt-6.2-sol","input":[{"type":"item_reference","id":"item_other"}]}`, `{"model":"route-gpt-6.2-sol","conversation":"conv_other"}`} {
		if call(g, "POST", "/v1/responses", body, "local", "native").Code != 400 {
			t.Fatal("invalid alias or account-bound reference accepted")
		}
	}
	w = call(g, "POST", "/v1/responses/compact", `{"model":"route-gpt-6.2-sol","input":[{"type":"compaction","encrypted_content":"opaque-fixture"}]}`, "local", "native")
	if w.Code != 403 || w.Body.String() != "project refused" {
		t.Fatal("failed to propagate upstream refusal")
	}
	if catalogHits != 1 || nativeHits != 0 || routeHits != 1 {
		t.Fatal("cross-account fallback or incorrect request count")
	}
	if call(g, "POST", "/v1/responses", `{"model":"gpt-6.2-sol"}`, "local", "native").Code != 200 || nativeHits != 1 {
		t.Fatal("native dispatch failed")
	}
}

func TestConcurrentStreamCancellation(t *testing.T) {
	started := make(chan struct{})
	cancelled := make(chan struct{})
	route := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: {}\n\n")
		w.(http.Flusher).Flush()
		close(started)
		<-r.Context().Done()
		close(cancelled)
	}))
	defer route.Close()
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			io.WriteString(w, `{"models":[{"slug":"gpt-6.2-sol"}]}`)
			return
		}
		io.WriteString(w, "native completed")
	}))
	defer native.Close()
	g, err := newGateway(config{NativeURL: native.URL, RouteURL: route.URL, RouteKey: "project", GatewayToken: "local", Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	call(g, "GET", "/v1/models?client_version=1", "", "local", "native")
	server := httptest.NewServer(g)
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, "POST", server.URL+"/v1/responses", strings.NewReader(`{"model":"route-gpt-6.2-sol"}`))
	req.Header.Set("X-Route-Token", "Bearer local")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	<-started
	if w := call(g, "POST", "/v1/responses", `{"model":"gpt-6.2-sol"}`, "local", "native"); w.Code != 200 || w.Body.String() != "native completed" {
		t.Fatal("concurrent native request failed")
	}
	cancel()
	select {
	case <-cancelled:
	case <-time.After(2 * time.Second):
		t.Fatal("Stop did not cancel upstream")
	}
}

func TestImageToolUsesOriginatingTurn(t *testing.T) {
	var routeCount, nativeCount int
	project := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		routeCount++
		if r.URL.Path != "/responses" || r.Header.Get("Authorization") != "Bearer project" || r.Header.Get("ChatGPT-Account-ID") != "" {
			t.Error("incorrect Route image destination")
		}
		var req struct {
			Model string
			Tools []struct{ Type, Model string }
		}
		if json.NewDecoder(r.Body).Decode(&req) != nil || req.Model != "gpt-6.2-sol" || len(req.Tools) != 1 || req.Tools[0].Type != "image_generation" || req.Tools[0].Model != "gpt-image-2" {
			t.Error("incorrect Responses image tool request")
		}
		io.WriteString(w, `{"status":"completed","created_at":1,"output":[{"type":"image_generation_call","status":"completed","id":"result","result":"aGVsbG8="}]}`)
	}))
	defer project.Close()
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		nativeCount++
		if r.URL.Path != "/images/generations" || r.Header.Get("Authorization") != "Bearer native" || r.Header.Get("X-Route-Token") != "" {
			t.Error("incorrect native image destination")
		}
		io.WriteString(w, "native")
	}))
	defer native.Close()
	g, err := newGateway(config{NativeURL: native.URL, RouteURL: project.URL, RouteKey: "project", GatewayToken: "local", Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	req := func(turn, account string) *http.Request {
		r := httptest.NewRequest("POST", "/v1/images/generations", strings.NewReader(`{"model":"gpt-image-2","prompt":"a test drawing"}`))
		r.Header.Set("X-Route-Token", "Bearer local")
		r.Header.Set("X-Codex-Image-Turn-Id", turn)
		r.Header.Set("Authorization", "Bearer "+account)
		return r
	}
	for id, model := range map[string]string{"turn-a": "route-gpt-6.2-sol", "turn-b": "gpt-6.2-sol"} {
		if !g.bindTurn(req(id, "native"), id, model, "1") {
			t.Fatal("turn binding failed")
		}
	}
	if g.bindTurn(req("turn-a", "native"), "turn-a", "gpt-6.2-sol", "1") {
		t.Fatal("rebound a live turn to a different billing account")
	}
	for _, sample := range []struct {
		turn, account string
		status        int
		replies       string
	}{
		{"turn-a", "native", 200, `"b64_json":"aGVsbG8="`}, {"turn-b", "native", 200, "native"},
		{"turn-a", "other", 409, "No billing account"}, {"missing", "native", 409, "No billing account"}} {
		w := httptest.NewRecorder()
		g.ServeHTTP(w, req(sample.turn, sample.account))
		if w.Code != sample.status || !strings.Contains(w.Body.String(), sample.replies) {
			t.Errorf("incorrect image result for %s", sample.turn)
		}
	}
	if routeCount != 1 || nativeCount != 1 {
		t.Fatal("unexpected image upstream call count")
	}
}

func TestPrivateRotationPinsStreamAndRevokesAliases(t *testing.T) {
	started, release := make(chan struct{}), make(chan struct{})
	var once sync.Once
	finish := func() { once.Do(func() { close(release) }) }
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("unexpected native fallback") }))
	defer native.Close()
	var mu sync.Mutex
	var keys []string
	project := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get("Authorization")
		mu.Lock()
		keys = append(keys, key)
		mu.Unlock()
		if key == "Bearer original" {
			w.Header().Set("Content-Type", "text/event-stream")
			io.WriteString(w, "data: started\n\n")
			w.(http.Flusher).Flush()
			close(started)
			<-release
			io.WriteString(w, "data: finished\n\n")
			return
		}
		io.WriteString(w, "replacement")
	}))
	defer project.Close()
	g, err := newGateway(config{NativeURL: native.URL, RouteURL: project.URL, RouteKey: "original", GatewayToken: "local", Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol"), testRow("route-gpt-6.2-astra")}}})
	if err != nil {
		t.Fatal(err)
	}
	d := &dispatcher{}
	d.active.Store(g)
	server := httptest.NewServer(d)
	defer server.Close()
	defer finish()
	body := `{"model":"route-gpt-6.2-sol"}`
	req, _ := http.NewRequest("POST", server.URL+"/v1/responses", strings.NewReader(body))
	req.Header.Set("X-Route-Token", "Bearer local")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	resp, err := http.DefaultClient.Do(req.WithContext(ctx))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	<-started
	update := `{"RouteKey":"new","Catalogs":{"1":[{"slug":"route-gpt-6.2-sol"}]}}`
	if call(d, "POST", "/replace", update, "local", "").Code != 404 {
		t.Fatal("control path exposed on data socket")
	}
	w := httptest.NewRecorder()
	d.control(w, httptest.NewRequest("POST", "/replace", strings.NewReader(update)))
	if w.Code != 204 {
		t.Fatal("private control rejected rotation")
	}
	if call(d, "POST", "/v1/responses", `{"model":"route-gpt-6.2-astra"}`, "local", "").Code != 400 {
		t.Fatal("revoked alias still accepted")
	}
	if got := call(d, "POST", "/v1/responses", body, "local", ""); got.Code != 200 || got.Body.String() != "replacement" {
		t.Fatal("new request did not use replacement key")
	}
	finish()
	all, err := io.ReadAll(resp.Body)
	if err != nil || !strings.Contains(string(all), "finished") {
		t.Fatal("rotation broke active stream")
	}
	mu.Lock()
	defer mu.Unlock()
	if len(keys) != 2 || keys[0] != "Bearer original" || keys[1] != "Bearer new" {
		t.Fatal("unexpected billed requests")
	}
}
