package main

import (
	"encoding/json"
	"net/http"
	"sync"
	"sync/atomic"
)

// Data requests take one immutable snapshot. Only the owner of the separate private
// control socket can publish a replacement key and its eligible catalogs.
type dispatcher struct {
	active atomic.Pointer[gateway]
	update sync.Mutex
}

func (d *dispatcher) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	d.active.Load().ServeHTTP(w, r)
}

func (d *dispatcher) control(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" || r.URL.Path != "/replace" {
		reject(w, 404, "Unsupported control operation")
		return
	}
	var update struct {
		RouteKey string
		Catalogs map[string][]modelRow
	}
	body := http.MaxBytesReader(w, r.Body, catalogLimit)
	dec := json.NewDecoder(body)
	dec.DisallowUnknownFields()
	if dec.Decode(&update) != nil || update.RouteKey == "" || len(update.Catalogs) == 0 {
		reject(w, 400, "Invalid replacement credential or catalogs")
		return
	}
	d.update.Lock()
	defer d.update.Unlock()
	current := d.active.Load()
	cfg := current.config
	cfg.RouteKey = update.RouteKey
	cfg.Catalogs = update.Catalogs
	next, err := newGateway(cfg)
	if err != nil {
		reject(w, 400, "Invalid replacement configuration")
		return
	}
	next.routingState = current.routingState
	d.active.Store(next)
	w.WriteHeader(204)
}
