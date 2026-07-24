package bindings

import (
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

type HTTPService struct {
	mu       sync.Mutex
	server   *http.Server
	running  bool
	addr     string
	proxyAPI *ProxyAPI
}

func NewHTTPService(proxyAPI *ProxyAPI) *HTTPService {
	return &HTTPService{proxyAPI: proxyAPI}
}

func (s *HTTPService) Start(port int, allowRemote bool) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.running {
		return nil
	}

	host := "127.0.0.1"
	if allowRemote {
		host = "0.0.0.0"
	}
	s.addr = fmt.Sprintf("%s:%d", host, port)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/api/status", s.handleStatus)
	mux.HandleFunc("/", s.handleProxy)

	s.server = &http.Server{
		Addr:    s.addr,
		Handler: mux,
	}

	go func() {
		if err := s.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			s.mu.Lock()
			s.running = false
			s.mu.Unlock()
		}
	}()

	s.running = true
	return nil
}

func (s *HTTPService) Stop() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	err := s.server.Shutdown(ctx)
	s.running = false
	return err
}

func (s *HTTPService) IsRunning() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.running
}

func (s *HTTPService) GetAddress() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return fmt.Sprintf("http://127.0.0.1%s", s.addr[strings.LastIndex(s.addr, ":"):])
}

func (s *HTTPService) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"status":"ok"}`))
}

func (s *HTTPService) handleStatus(w http.ResponseWriter, r *http.Request) {
	proxies := s.proxyAPI.GetProxies()
	available := 0
	for _, p := range proxies {
		if p.Status == "active" && p.Enabled {
			available++
		}
	}
	body := fmt.Sprintf(`{"running":true,"availableProxies":%d,"totalProxies":%d}`, available, len(proxies))
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(body))
}

func (s *HTTPService) handleProxy(w http.ResponseWriter, r *http.Request) {
	targetURL := strings.TrimPrefix(r.URL.Path, "/")
	if targetURL == "" {
		http.Error(w, "Usage: http://127.0.0.1:9090/<url-to-download>", http.StatusBadRequest)
		return
	}

	// Ensure it has a scheme
	if !strings.HasPrefix(targetURL, "http://") && !strings.HasPrefix(targetURL, "https://") {
		targetURL = "https://" + targetURL
	}

	proxies := s.proxyAPI.GetProxies()
	var activeDomains []string
	for _, p := range proxies {
		if p.Status == "active" && p.Enabled {
			activeDomains = append(activeDomains, p.Domain)
		}
	}

	if len(activeDomains) == 0 {
		http.Error(w, "no available proxies", http.StatusServiceUnavailable)
		return
	}

	// Rotate through proxies
	var lastErr error
	for _, domain := range activeDomains {
		proxyURL := fmt.Sprintf("https://%s", domain)
		err := proxyRequest(w, r, targetURL, proxyURL)
		if err == nil {
			return
		}
		lastErr = err
	}

	http.Error(w, fmt.Sprintf("all proxies failed: %v", lastErr), http.StatusBadGateway)
}

func proxyRequest(w http.ResponseWriter, r *http.Request, targetURL, proxyURL string) error {
	target, err := url.Parse(targetURL)
	if err != nil {
		return fmt.Errorf("invalid target URL: %w", err)
	}

	proxy, err := url.Parse(proxyURL)
	if err != nil {
		return fmt.Errorf("invalid proxy URL: %w", err)
	}

	transport := &http.Transport{
		Proxy: http.ProxyURL(proxy),
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: true,
		},
		DialContext: (&net.Dialer{
			Timeout:   10 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout:   10 * time.Second,
		ResponseHeaderTimeout: 15 * time.Second,
	}

	client := &http.Client{
		Transport: transport,
		Timeout:   0, // no timeout - let the stream flow
	}

	proxyReq, err := http.NewRequestWithContext(r.Context(), r.Method, target.String(), r.Body)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

	// Copy headers from original request
	for key, values := range r.Header {
		for _, v := range values {
			proxyReq.Header.Add(key, v)
		}
	}

	// Set X-Forwarded-For
	proxyReq.Header.Set("X-Forwarded-For", r.RemoteAddr)

	resp, err := client.Do(proxyReq)
	if err != nil {
		return fmt.Errorf("proxy request failed: %w", err)
	}
	defer resp.Body.Close()

	// Copy response headers
	for key, values := range resp.Header {
		for _, v := range values {
			w.Header().Add(key, v)
		}
	}
	w.Header().Set("X-Proxy", proxyURL)
	w.WriteHeader(resp.StatusCode)

	_, err = io.Copy(w, resp.Body)
	return err
}
