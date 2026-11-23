package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"
)

// Image tool requests contain an image model, not the selected chat model.
// Keep only a short-lived credential-scoped turn binding. No history is needed.
type turnBinding struct {
	Model   string
	Version string
	Expires time.Time
}

func turnID(r *http.Request, fields modelRow) string {
	var meta struct {
		Turn string `json:"turn_id"`
	}
	_ = json.Unmarshal([]byte(r.Header.Get("X-Codex-Turn-Metadata")), &meta)
	if meta.Turn == "" {
		_ = json.Unmarshal(fields["client_metadata"], &meta)
	}
	return meta.Turn
}

func (g *gateway) bindTurn(r *http.Request, id, model, version string) bool {
	if id == "" {
		return true
	}
	if len(id) > 256 {
		return false
	}
	key := identity(r, "turn:"+id)
	g.mu.Lock()
	defer g.mu.Unlock()
	now := time.Now()
	if bound, ok := g.turns[key]; ok && now.Before(bound.Expires) && bound.Model != model {
		return false
	}
	if len(g.turns) >= 4096 {
		for key, entry := range g.turns {
			if !now.Before(entry.Expires) {
				delete(g.turns, key)
			}
		}
		if _, exists := g.turns[key]; !exists && len(g.turns) >= 4096 {
			return false
		}
	}
	g.turns[key] = turnBinding{Model: model, Version: version, Expires: now.Add(time.Hour)}
	return true
}

func (g *gateway) image(w http.ResponseWriter, r *http.Request) {
	id := r.Header.Get("X-Codex-Image-Turn-Id")
	g.mu.RLock()
	bound, ok := g.turns[identity(r, "turn:"+id)]
	g.mu.RUnlock()
	if !ok || id == "" || !time.Now().Before(bound.Expires) {
		reject(w, 409, "No billing account for this image turn")
		return
	}
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, inputLimit))
	if err != nil {
		reject(w, 413, "Image request too large")
		return
	}
	if !strings.HasPrefix(bound.Model, "route-") {
		g.proxy(w, r, raw, g.native, false)
		return
	}
	if !g.eligibleAlias(bound.Version, bound.Model) {
		reject(w, 403, "The Route model for this image turn is no longer eligible")
		return
	}
	if r.URL.Path != "/v1/images/generations" {
		reject(w, 422, "Route image editing has not been qualified")
		return
	}
	var request struct {
		Prompt, Background, Quality, Size, Model string
		OutputFormat                             string `json:"output_format"`
		N                                        *int
	}
	if json.Unmarshal(raw, &request) != nil || request.Prompt == "" || request.Model != "gpt-image-2" ||
		(request.N != nil && *request.N != 1) || (request.OutputFormat != "" && request.OutputFormat != "png") {
		reject(w, 422, "Unsupported Route image generation parameters")
		return
	}
	// Codex consumes the Images result shape. The Route upstream is a Responses
	// endpoint, so invoke its hosted image tool with the originating chat model.
	tool := map[string]string{"type": "image_generation", "model": request.Model, "output_format": "png"}
	for k, v := range map[string]string{"background": request.Background, "quality": request.Quality, "size": request.Size} {
		if v != "" {
			tool[k] = v
		}
	}
	body, err := json.Marshal(map[string]any{"model": strings.TrimPrefix(bound.Model, "route-"), "input": request.Prompt, "tools": []any{tool},
		"tool_choice": map[string]string{"type": "image_generation"}, "store": false})
	if err != nil {
		reject(w, 400, "Invalid image request")
		return
	}
	target := *g.route
	target.Path += "/responses"
	req, err := http.NewRequestWithContext(r.Context(), "POST", target.String(), bytes.NewReader(body))
	if err != nil {
		reject(w, 500, "Invalid image endpoint")
		return
	}
	req.Header.Set("Authorization", "Bearer "+g.config.RouteKey)
	req.Header.Set("Content-Type", "application/json")
	res, err := g.client.Do(req)
	if err != nil {
		reject(w, 502, "Image upstream connection failed")
		return
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		w.Header().Set("Content-Type", res.Header.Get("Content-Type"))
		w.WriteHeader(res.StatusCode)
		io.Copy(w, io.LimitReader(res.Body, 1<<20))
		return
	}
	data, err := io.ReadAll(io.LimitReader(res.Body, inputLimit+1))
	var doc struct {
		Status  string
		Created int64 `json:"created_at"`
		Output  []struct{ Type, Status, Result, Background, ID string }
	}
	if err != nil || len(data) > inputLimit || json.Unmarshal(data, &doc) != nil || doc.Status != "completed" {
		reject(w, 502, "Incomplete image response")
		return
	}
	for _, item := range doc.Output {
		if item.Type == "image_generation_call" && item.Status == "completed" && item.Result != "" {
			w.Header().Set("Content-Type", "application/json")
			response := map[string]any{"created": doc.Created, "data": []any{map[string]string{"b64_json": item.Result, "generation_id": item.ID}}}
			if item.Background != "" {
				response["background"] = item.Background
			}
			_ = json.NewEncoder(w).Encode(response)
			return
		}
	}
	reject(w, 502, "The Responses API returned no generated image")
}
