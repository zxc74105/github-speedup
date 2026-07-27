package bindings

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"multi-proxy-downloader/core"
)

type ProxyAPI struct {
	ctx         context.Context
	mu          sync.Mutex
	proxies     []ProxyItem
	proxiesPath string
	silentList  []string
}

type ProxyItem struct {
	Domain  string `json:"domain"`  // raw domain, NO scheme prefix
	Scheme  string `json:"scheme"`  // "https", "http", or "" (untested)
	Enabled bool   `json:"enabled"`
	Status  string `json:"status"`
	Latency string `json:"latency"`
	Speed   string `json:"speed"`
}

type PreflightResult struct {
	Available     int      `json:"available"`
	Silent        int      `json:"silent"`
	Total         int      `json:"total"`
	SilentDomains []string `json:"silentDomains"`
}

type ProxyTestResult struct {
	Domain  string `json:"domain"`  // raw domain
	Scheme  string `json:"scheme"`  // detected scheme
	Latency string `json:"latency"`
	Speed   string `json:"speed"`
	Status  string `json:"status"`
}

func (p *ProxyAPI) SetCtx(ctx context.Context) {
	p.ctx = ctx
}

func NewProxyAPI(ctx context.Context) *ProxyAPI {
	dir := core.AppDir()
	proxiesPath := filepath.Join(dir, "proxies-active.json")

	api := &ProxyAPI{
		ctx:         ctx,
		proxiesPath: proxiesPath,
	}
	api.loadProxies()
	return api
}

func (p *ProxyAPI) loadProxies() {
	data, err := os.ReadFile(p.proxiesPath)
	if err != nil {
		p.proxies = p.loadDefaultProxies()
		p.saveProxies()
		return
	}
	var items []ProxyItem
	if json.Unmarshal(data, &items) == nil && len(items) > 0 {
		// Migrate: strip scheme from domain if present, set Scheme field
		for i := range items {
			if items[i].Scheme == "" && (strings.HasPrefix(items[i].Domain, "http://") || strings.HasPrefix(items[i].Domain, "https://")) {
				parts := strings.SplitN(items[i].Domain, "://", 2)
				items[i].Scheme = parts[0]
				items[i].Domain = parts[1]
			}
		}
		p.proxies = items
		return
	}
	p.proxies = p.loadDefaultProxies()
	p.saveProxies()
}

func (p *ProxyAPI) loadDefaultProxies() []ProxyItem {
	var domains []string
	srcPath := core.FindProxiesFile()
	data, err := os.ReadFile(srcPath)
	if err == nil {
		json.Unmarshal(data, &domains)
	}
	if len(domains) == 0 {
		domains = core.DefaultProxies
		if jsonData, e := json.MarshalIndent(domains, "", "  "); e == nil {
			os.WriteFile(srcPath, jsonData, 0644)
		}
	}

	seen := map[string]bool{}
	items := make([]ProxyItem, 0, len(domains))
	for _, d := range domains {
		d = strings.TrimSpace(d)
		d = core.StripScheme(d)
		if d == "" || seen[d] || !core.IsValidProxyDomain(d) {
			continue
		}
		seen[d] = true
		items = append(items, ProxyItem{
			Domain:  d,
			Scheme:  "https",
			Enabled: true,
			Status:  "active",
		})
	}
	return items
}

func (p *ProxyAPI) saveProxies() {
	data, _ := json.MarshalIndent(p.proxies, "", "  ")
	os.WriteFile(p.proxiesPath, data, 0644)
}

func (p *ProxyAPI) GetProxies() []ProxyItem {
	p.mu.Lock()
	defer p.mu.Unlock()
	result := make([]ProxyItem, len(p.proxies))
	copy(result, p.proxies)
	return result
}

func parseSpeedMbps(speed string) float64 {
	s := strings.TrimSuffix(speed, " Mbps")
	v, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return 0
	}
	return v
}

func parseLatencyMs(latency string) int {
	s := strings.TrimSuffix(latency, " ms")
	v, err := strconv.Atoi(s)
	if err != nil {
		return 999999
	}
	return v
}

func sortProxiesBySpeed(proxies []ProxyItem) {
	sort.SliceStable(proxies, func(i, j int) bool {
		statusOrder := map[string]int{"active": 0, "silent": 1, "offline": 2, "checking": 3}
		oi := statusOrder[proxies[i].Status]
		oj := statusOrder[proxies[j].Status]
		if oi != oj {
			return oi < oj
		}
		if oi == 0 {
			return parseSpeedMbps(proxies[i].Speed) > parseSpeedMbps(proxies[j].Speed)
		}
		if oi == 1 {
			return parseLatencyMs(proxies[i].Latency) < parseLatencyMs(proxies[j].Latency)
		}
		return false
	})
}

func (p *ProxyAPI) TestAllProxies() error {
	p.mu.Lock()
	proxies := make([]ProxyItem, len(p.proxies))
	copy(proxies, p.proxies)
	p.mu.Unlock()

	var wg sync.WaitGroup
	for i := range proxies {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			result := testSingleProxy(proxies[idx].Domain)
			p.mu.Lock()
			proxies[idx].Scheme = result.Scheme
			proxies[idx].Domain = result.Domain
			proxies[idx].Latency = result.Latency
			proxies[idx].Speed = result.Speed
			proxies[idx].Status = result.Status
			p.mu.Unlock()
		}(i)
	}
	wg.Wait()

	p.mu.Lock()
	p.proxies = proxies
	p.saveProxies()
	p.mu.Unlock()
	return nil
}

func (p *ProxyAPI) TestProxy(domain string) ProxyTestResult {
	result := testSingleProxy(core.StripScheme(domain))
	p.mu.Lock()
	for i, pr := range p.proxies {
		if pr.Domain == core.StripScheme(domain) {
			p.proxies[i].Scheme = result.Scheme
			p.proxies[i].Domain = result.Domain
			p.proxies[i].Latency = result.Latency
			p.proxies[i].Speed = result.Speed
			p.proxies[i].Status = result.Status
			break
		}
	}
	p.saveProxies()
	p.mu.Unlock()
	return result
}

func (p *ProxyAPI) ToggleProxy(domain string, enabled bool) {
	p.mu.Lock()
	defer p.mu.Unlock()
	rawDomain := core.StripScheme(domain)
	for i, pr := range p.proxies {
		if pr.Domain == rawDomain {
			p.proxies[i].Enabled = enabled
			break
		}
	}
	p.saveProxies()
}

func (p *ProxyAPI) ImportProxies(filePath string) (int, error) {
	lines, err := core.ReadLines(filePath)
	if err != nil {
		return 0, err
	}
	count := 0
	p.mu.Lock()
	defer p.mu.Unlock()
	existing := map[string]bool{}
	for _, pr := range p.proxies {
		existing[pr.Domain] = true
	}
	for _, line := range lines {
		line = strings.TrimSpace(line)
		line = core.StripScheme(line)
		if line == "" || existing[line] {
			continue
		}
		p.proxies = append(p.proxies, ProxyItem{Domain: line, Enabled: true, Status: "active"})
		existing[line] = true
		count++
	}
	p.saveProxies()
	return count, nil
}

func (p *ProxyAPI) ExportProxies(filePath string) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	lines := make([]string, 0, len(p.proxies))
	for _, pr := range p.proxies {
		lines = append(lines, pr.Domain)
	}
	return os.WriteFile(filePath, []byte(strings.Join(lines, "\n")), 0644)
}

func (p *ProxyAPI) PreflightCheck() PreflightResult {
	p.mu.Lock()
	proxies := make([]ProxyItem, len(p.proxies))
	copy(proxies, p.proxies)
	p.mu.Unlock()

	var mu sync.Mutex
	available := 0
	silent := 0
	var silentDomains []string

	var wg sync.WaitGroup
	for i := range proxies {
		if !proxies[i].Enabled {
			continue
		}
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			result := testSingleProxy(proxies[idx].Domain)
			p.mu.Lock()
			proxies[idx].Scheme = result.Scheme
			proxies[idx].Domain = result.Domain
			proxies[idx].Latency = result.Latency
			proxies[idx].Speed = result.Speed
			proxies[idx].Status = result.Status
			p.mu.Unlock()

			mu.Lock()
			if result.Status == "active" {
				available++
			} else {
				silent++
				silentDomains = append(silentDomains, proxies[idx].Domain)
			}
			mu.Unlock()
		}(i)
	}
	wg.Wait()

	sortProxiesBySpeed(proxies)
	p.mu.Lock()
	p.proxies = proxies
	p.silentList = silentDomains
	p.saveProxies()
	p.mu.Unlock()

	return PreflightResult{
		Available:     available,
		Silent:        silent,
		Total:         len(proxies),
		SilentDomains: silentDomains,
	}
}

func (p *ProxyAPI) GetSilentProxies() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	result := make([]string, len(p.silentList))
	copy(result, p.silentList)
	return result
}

func (p *ProxyAPI) UnsilenceProxy(domain string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	rawDomain := core.StripScheme(domain)
	for i, d := range p.silentList {
		if d == rawDomain {
			p.silentList = append(p.silentList[:i], p.silentList[i+1:]...)
			break
		}
	}
}

const proxyTestURL = "https://github.com/zxc74105/ceshi/blob/main/speedtest.txt"

func testSingleProxy(domain string) ProxyTestResult {
	rawDomain := core.StripScheme(domain)
	// These are URL-prefix-based reverse proxies, NOT CONNECT proxies.
	// Just make a direct GET request to the full URL.
	for _, scheme := range []string{"https", "http"} {
		proxyURL := core.BuildProxyURL(scheme, rawDomain, proxyTestURL)

		start := time.Now()
		client := &http.Client{
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{
					InsecureSkipVerify: true,
					Renegotiation:      tls.RenegotiateFreelyAsClient,
				},
				DialContext: (&net.Dialer{
					Timeout:   8 * time.Second,
					KeepAlive: 10 * time.Second,
				}).DialContext,
			},
			Timeout: 15 * time.Second,
		}

		req, err := http.NewRequest("GET", proxyURL, nil)
		if err != nil {
			continue
		}
		core.ApplyBrowserHeaders(req)
		resp, err := client.Do(req)
		if err != nil {
			continue
		}

		latency := time.Since(start)
		latencyStr := fmt.Sprintf("%d ms", latency.Milliseconds())

		ct := resp.Header.Get("Content-Type")
		if strings.Contains(ct, "text/html") {
			resp.Body.Close()
			continue
		}

		start = time.Now()
		var totalBytes int64
		buf := make([]byte, 32*1024)
		for {
			n, err := resp.Body.Read(buf)
			totalBytes += int64(n)
			if err != nil {
				break
			}
		}
		resp.Body.Close()
		elapsed := time.Since(start).Seconds()

		status := "active"
		speedStr := "N/A"
		if elapsed > 0 && totalBytes > 0 {
			speed := float64(totalBytes) / elapsed * 8 / 1000000
			speedStr = fmt.Sprintf("%.1f Mbps", speed)
			if speed < 0.1 {
				status = "silent"
			}
		}
		if latency > 2000*time.Millisecond {
			status = "silent"
		}

		return ProxyTestResult{Domain: rawDomain, Scheme: scheme, Latency: latencyStr, Speed: speedStr, Status: status}
	}
	return ProxyTestResult{Domain: rawDomain, Scheme: "", Latency: "N/A", Speed: "N/A", Status: "offline"}
}
