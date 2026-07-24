package core

import (
	"bufio"
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type FilePart struct {
	Number     int
	Start      int64
	End        int64
	Downloaded bool
}

func PrepareOutputPath(userPath string) (absPath string, workDir string, err error) {
	absPath, err = filepath.Abs(userPath)
	if err != nil {
		return "", "", fmt.Errorf("failed to get absolute path: %w", err)
	}
	workDir = filepath.Dir(absPath)
	if err := os.MkdirAll(workDir, 0755); err != nil {
		return "", "", fmt.Errorf("failed to create directory %s: %w", workDir, err)
	}
	return absPath, workDir, nil
}

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

func GetFileInfo(fileURL, proxyURL string) (int64, string, error) {
	transport := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}
	if proxyURL != "" {
		proxy, err := url.Parse(proxyURL)
		if err != nil {
			return 0, "", err
		}
		transport.Proxy = http.ProxyURL(proxy)
	}
	client := &http.Client{Transport: transport}
	var contentLength int64
	fileName := ""

	resp, err := client.Head(fileURL)
	if err == nil {
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return 0, "", fmt.Errorf("server returned non-200 status: %v", resp.Status)
		}
		contentDisposition := resp.Header.Get("Content-Disposition")
		if contentDisposition != "" {
			parts := strings.SplitSeq(contentDisposition, ";")
			for part := range parts {
				part = strings.TrimSpace(part)
				if value, ok := strings.CutPrefix(part, "filename="); ok {
					fileName = strings.Trim(value, `"`)
					break
				}
			}
		}
		contentLengthStr := resp.Header.Get("Content-Length")
		if contentLengthStr != "" {
			contentLength, err = strconv.ParseInt(contentLengthStr, 10, 64)
		}
	}
	if fileName == "" {
		parsedURL, err := url.Parse(fileURL)
		if err == nil {
			fileName = filepath.Base(parsedURL.Path)
		} else {
			fileName = "downloaded_file"
		}
	}
	if contentLength != 0 {
		return contentLength, fileName, nil
	}

	req, err := http.NewRequest("GET", fileURL, nil)
	if err != nil {
		return 0, "", fmt.Errorf("failed to create probe request: %w", err)
	}
	req.Header.Set("Range", "bytes=999999999999-")
	probeResp, err := client.Do(req)
	if err != nil {
		return 0, "", fmt.Errorf("probe request failed: %w", err)
	}
	defer probeResp.Body.Close()
	if probeResp.StatusCode != http.StatusRequestedRangeNotSatisfiable {
		return 0, "", fmt.Errorf("probe failed: server returned unexpected status %s", probeResp.Status)
	}
	contentRange := probeResp.Header.Get("Content-Range")
	if contentRange == "" {
		return 0, "", fmt.Errorf("probe failed: no Content-Range header")
	}
	parts := strings.Split(contentRange, "/")
	if len(parts) != 2 {
		return 0, "", fmt.Errorf("probe failed: invalid Content-Range format: %s", contentRange)
	}
	contentLength, err = strconv.ParseInt(parts[1], 10, 64)
	if err != nil {
		return 0, "", fmt.Errorf("probe failed: could not parse file size: %s", contentRange)
	}
	return contentLength, fileName, nil
}

func DivideFileIntoParts(totalLength int64, partSizeBytes int64) []FilePart {
	var parts []FilePart
	start := int64(0)
	counter := 0
	for start < totalLength {
		end := start + partSizeBytes - 1
		if end >= totalLength {
			end = totalLength - 1
		}
		parts = append(parts, FilePart{Number: counter, Start: start, End: end})
		counter++
		start = end + 1
	}
	return parts
}

type progressReader struct {
	io.Reader
	OnRead func()
}

func (pr *progressReader) Read(p []byte) (n int, err error) {
	n, err = pr.Reader.Read(p)
	if n > 0 && pr.OnRead != nil {
		pr.OnRead()
	}
	return
}

type trackReader struct {
	io.Reader
	OnRead func(int)
}

func (tr *trackReader) Read(p []byte) (n int, err error) {
	n, err = tr.Reader.Read(p)
	if n > 0 && tr.OnRead != nil {
		tr.OnRead(n)
	}
	return
}

func DownloadPartialFile(fileURL, proxyURL, outputPath string, startByte, endByte int64, timeout time.Duration, onProgress func(int64)) (int64, error) {
	transport := &http.Transport{
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout:   5 * time.Second,
		ResponseHeaderTimeout: 5 * time.Second,
		TLSClientConfig:       &tls.Config{InsecureSkipVerify: true},
	}
	if proxyURL != "" {
		proxy, err := url.Parse(proxyURL)
		if err != nil {
			return 0, err
		}
		transport.Proxy = http.ProxyURL(proxy)
	}
	client := &http.Client{Transport: transport}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, "GET", fileURL, nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", startByte, endByte))

	resp, err := client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusPartialContent {
		return 0, fmt.Errorf("server returned unexpected status: %v", resp.Status)
	}

	file, err := os.Create(outputPath)
	if err != nil {
		return 0, err
	}
	defer file.Close()

	var timer *time.Timer
	if timeout > 0 {
		timer = time.AfterFunc(timeout, func() { cancel() })
		defer timer.Stop()
	}

	reader := io.Reader(resp.Body)
	if timeout > 0 {
		reader = &progressReader{Reader: reader, OnRead: func() { timer.Reset(timeout) }}
	}
	reader = &trackReader{Reader: reader, OnRead: func(n int) {
		if onProgress != nil {
			onProgress(int64(n))
		}
	}}

	return io.Copy(file, reader)
}

func ConcatenateFiles(outputPath, workDir string) error {
	outFile, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer outFile.Close()

	baseFileName := filepath.Base(outputPath)
	partNum := 0
	var partFileNames []string
	for {
		partFileName := fmt.Sprintf("%s.%d.part", baseFileName, partNum)
		partAbsPath := filepath.Join(workDir, partFileName)
		_, err := os.Stat(partAbsPath)
		if os.IsNotExist(err) {
			break
		} else if err != nil {
			return err
		}
		partFile, err := os.Open(partAbsPath)
		if err != nil {
			return err
		}
		defer partFile.Close()
		_, err = io.Copy(outFile, partFile)
		if err != nil {
			return err
		}
		partFileNames = append(partFileNames, partAbsPath)
		partNum++
	}
	for _, f := range partFileNames {
		os.Remove(f)
	}
	return nil
}

func SaveContentLengthToFile(workDir, outputFileName string, contentLength int64) (string, error) {
	infoFilePath := filepath.Join(workDir, outputFileName+".info.txt")
	if _, err := os.Stat(infoFilePath); err == nil {
		file, err := os.Open(infoFilePath)
		if err != nil {
			return infoFilePath, fmt.Errorf("failed to open info file: %w", err)
		}
		defer file.Close()
		scanner := bufio.NewScanner(file)
		scanner.Scan()
		stored, _ := strconv.ParseInt(scanner.Text(), 10, 64)
		if stored != contentLength {
			return infoFilePath, fmt.Errorf("file size changed: stored %d, current %d", stored, contentLength)
		}
		return infoFilePath, nil
	} else if !os.IsNotExist(err) {
		return infoFilePath, fmt.Errorf("failed to stat info file: %w", err)
	}
	file, err := os.Create(infoFilePath)
	if err != nil {
		return infoFilePath, fmt.Errorf("failed to create info file: %w", err)
	}
	defer file.Close()
	file.WriteString(strconv.FormatInt(contentLength, 10))
	return infoFilePath, nil
}
