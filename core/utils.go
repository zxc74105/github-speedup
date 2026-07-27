package core

import (
	"bufio"
	"crypto/tls"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

var SharedTransport = &http.Transport{
	DialContext: (&net.Dialer{
		Timeout:   5 * time.Second,
		KeepAlive: 30 * time.Second,
	}).DialContext,
	TLSHandshakeTimeout:   5 * time.Second,
	ResponseHeaderTimeout: 5 * time.Second,
	TLSClientConfig:       &tls.Config{InsecureSkipVerify: true},
	MaxIdleConns:          100,
	MaxIdleConnsPerHost:   10,
	IdleConnTimeout:       90 * time.Second,
}

// SharedClient wraps SharedTransport with redirect following enabled.
var SharedClient = &http.Client{Transport: SharedTransport}

func ReadLines(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var lines []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	return lines, scanner.Err()
}

func IsValidProxyDomain(domain string) bool {
	if domain == "" {
		return false
	}
	if strings.ContainsAny(domain, " \t\n\r") {
		return false
	}
	// Strip optional scheme prefix for validation
	cleanDomain := domain
	if strings.HasPrefix(cleanDomain, "http://") || strings.HasPrefix(cleanDomain, "https://") {
		cleanDomain = domain[strings.Index(domain, "://")+3:]
	}
	if cleanDomain == "" {
		return false
	}
	if !strings.Contains(cleanDomain, ".") {
		return false
	}
	if strings.ContainsAny(cleanDomain, "=/\\#@!~`\"'<>{}[]|") {
		return false
	}
	for _, r := range cleanDomain {
		if r > 127 {
			return false
		}
	}
	return true
}

func StripScheme(domain string) string {
	if strings.Contains(domain, "://") {
		parts := strings.SplitN(domain, "://", 2)
		return parts[1]
	}
	return domain
}

func BuildProxyURL(scheme, domain, targetURL string) string {
	if scheme == "" {
		scheme = "https"
	}
	if targetURL == "" {
		return fmt.Sprintf("%s://%s", scheme, domain)
	}
	return fmt.Sprintf("%s://%s/%s", scheme, domain, targetURL)
}

func AppDir() string {
	dir := "."
	if exe, err := os.Executable(); err == nil {
		dir = filepath.Dir(exe)
	}
	return dir
}

func FindProxiesFile() string {
	paths := []string{
		"proxies.json",
		filepath.Join(AppDir(), "proxies.json"),
	}
	for _, p := range paths {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return filepath.Join(AppDir(), "proxies.json")
}

func FindActiveProxiesFile() string {
	return filepath.Join(AppDir(), "proxies-active.json")
}

// ApplyBrowserHeaders sets a complete set of Chrome 126 browser headers
// on the given HTTP request, to avoid proxy detection/blocking.
func ApplyBrowserHeaders(req *http.Request) {
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7")
	req.Header.Set("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
	req.Header.Set("Accept-Encoding", "gzip, deflate, br")
	req.Header.Set("Sec-Ch-Ua", `"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"`)
	req.Header.Set("Sec-Ch-Ua-Mobile", "?0")
	req.Header.Set("Sec-Ch-Ua-Platform", `"Windows"`)
	req.Header.Set("Sec-Fetch-Dest", "document")
	req.Header.Set("Sec-Fetch-Mode", "navigate")
	req.Header.Set("Sec-Fetch-Site", "none")
	req.Header.Set("Sec-Fetch-User", "?1")
	req.Header.Set("Upgrade-Insecure-Requests", "1")
	req.Header.Set("DNT", "1")
	req.Header.Set("Connection", "keep-alive")
}


