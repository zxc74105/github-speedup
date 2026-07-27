package bindings

import (
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"multi-proxy-downloader/core"
)

type HTTPService struct {
	mu          sync.Mutex
	server      *http.Server
	running     bool
	addr        string
	proxyAPI    *ProxyAPI
	downloadAPI *DownloadAPI
}

func NewHTTPService(proxyAPI *ProxyAPI, downloadAPI *DownloadAPI) *HTTPService {
	return &HTTPService{proxyAPI: proxyAPI, downloadAPI: downloadAPI}
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

	// Use a raw HandlerFunc to avoid ServeMux's double-slash redirect
	s.server = &http.Server{
		Addr:    s.addr,
		Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			switch r.URL.Path {
			case "/health":
				s.handleHealth(w, r)
			case "/api/status":
				s.handleStatus(w, r)
			default:
				s.handleProxy(w, r)
			}
		}),
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
	if r.URL.RawQuery != "" {
		targetURL += "?" + r.URL.RawQuery
	}
	if targetURL == "" {
		http.Error(w, "Usage: http://127.0.0.1:9090/<url-to-download>", http.StatusBadRequest)
		return
	}

	// Fix browser path normalization: "https:/xxx" -> "https://xxx"
	if strings.HasPrefix(targetURL, "https:/") && !strings.HasPrefix(targetURL, "https://") {
		targetURL = "https://" + targetURL[len("https:/"):]
	} else if strings.HasPrefix(targetURL, "http:/") && !strings.HasPrefix(targetURL, "http://") {
		targetURL = "http://" + targetURL[len("http:/"):]
	}

	// Ensure it has a scheme
	if !strings.HasPrefix(targetURL, "http://") && !strings.HasPrefix(targetURL, "https://") {
		targetURL = "https://" + targetURL
	}

	log := GetLogger()
	log.Log("REQUEST %s from %s", targetURL, r.RemoteAddr)

	proxies := s.proxyAPI.GetProxies()
	var lastErr error
	for _, p := range proxies {
		if p.Status != "active" || !p.Enabled || p.Scheme == "" {
			continue
		}
		proxyURL := core.BuildProxyURL(p.Scheme, p.Domain, targetURL)
		log.Log("TRY %s", p.Domain)

		start := time.Now()
		bytesWritten, err := proxyRequest(w, r, targetURL, proxyURL)
		elapsed := time.Since(start).Seconds()
		if err == nil && elapsed > 0 && bytesWritten > 0 {
			speed := float64(bytesWritten) / elapsed * 8 / 1000000
			log.Log("SUCCESS %s - %d bytes, %.1f Mbps", p.Domain, bytesWritten, speed)
			if s.downloadAPI != nil {
				s.downloadAPI.RecordProxySuccess(p.Domain, bytesWritten, speed)
			}
			return
		}
		log.Log("FAIL %s: %v", p.Domain, err)
		lastErr = err
	}

	log.Log("ALL FAILED: %v", lastErr)
	http.Error(w, fmt.Sprintf("all proxies failed: %v", lastErr), http.StatusBadGateway)
}

func proxyRequest(w http.ResponseWriter, r *http.Request, targetURL, proxyURL string) (int64, error) {
	transport := &http.Transport{
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
		Timeout:   0,
	}

	proxyReq, err := http.NewRequestWithContext(r.Context(), r.Method, proxyURL, r.Body)
	if err != nil {
		return 0, fmt.Errorf("create request: %w", err)
	}

	for key, values := range r.Header {
		for _, v := range values {
			proxyReq.Header.Add(key, v)
		}
	}

	// Set browser-like defaults for any missing headers
	core.ApplyBrowserHeaders(proxyReq)

	proxyReq.Header.Set("X-Forwarded-For", r.RemoteAddr)

	resp, err := client.Do(proxyReq)
	if err != nil {
		return 0, fmt.Errorf("proxy request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return 0, fmt.Errorf("proxy returned %d", resp.StatusCode)
	}

	contentType := resp.Header.Get("Content-Type")
	if strings.Contains(strings.ToLower(contentType), "text/html") {
		return 0, fmt.Errorf("proxy returned text/html (landing page)")
	}

	for key, values := range resp.Header {
		for _, v := range values {
			w.Header().Add(key, v)
		}
	}
	w.Header().Set("X-Proxy", proxyURL)
	w.WriteHeader(resp.StatusCode)

	written, err := io.Copy(w, resp.Body)
	return written, err
}
