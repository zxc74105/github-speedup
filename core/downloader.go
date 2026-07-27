package core

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type DownloadTask struct {
	URL            string
	SaveDir        string
	FileName       string
	TotalBytes     int64
	Downloaded     int64
	PartSizeBytes  int64
	MaxConcurrent  int
	MaxRetry       int
	Timeout        int
	Status         string
	WorkerCount    int
	ProxySwitchCnt int
	Speed          float64
	ETA            string
	CreatedAt      time.Time
}

type DownloadProgress struct {
	TaskID         int
	FileName       string
	TotalBytes     int64
	Downloaded     int64
	Speed          float64
	ETA            string
	Status         string
	WorkerStatuses []WorkerStatus
}

type WorkerStatus struct {
	ID     int
	Proxy  string
	Speed  float64
	Status string
}

var (
	tasks  []*DownloadTask
	taskMu sync.Mutex
	nextID int = 1
)

type cancelEntry struct {
	id   int
	done func()
}

var cancels []cancelEntry

type ProgressData struct {
	TaskID      int
	Downloaded  int64
	TotalBytes  int64
	Speed       float64
	WorkerID    int
	WorkerProxy string
	WorkerSpeed float64
	PartDone    bool
	PartFailed  bool
	ProxyDomain string
}

func CancelDownload(id int) {
	taskMu.Lock()
	for _, c := range cancels {
		if c.id == id {
			c.done()
			taskMu.Unlock()
			return
		}
	}
	taskMu.Unlock()
}

type partJob struct {
	index int
	start int64
	end   int64
	proxy string
}

type activeEntry struct {
	Domain string `json:"domain"`
	Scheme string `json:"scheme"`
}

func loadActiveProxies() []string {
	var proxyList []string
	if data, err := os.ReadFile(FindActiveProxiesFile()); err == nil {
		var entries []activeEntry
		if json.Unmarshal(data, &entries) == nil {
			for _, e := range entries {
				scheme := e.Scheme
				if scheme == "" {
					scheme = "https"
				}
				proxyList = append(proxyList, fmt.Sprintf("%s://%s", scheme, e.Domain))
			}
		}
	}
	return proxyList
}

func getFileSizeViaAnyProxy(proxyList []string, rawURL string, timeout time.Duration) int64 {
	client := &http.Client{Transport: SharedTransport, Timeout: timeout}
	defer func() { client.CloseIdleConnections() }()
	for _, proxy := range proxyList {
		u := proxy + "/" + rawURL
		req, err := http.NewRequest("HEAD", u, nil)
		if err != nil {
			continue
		}
		ApplyBrowserHeaders(req)
		resp, err := client.Do(req)
		if err != nil {
			continue
		}
		cl := resp.ContentLength
		resp.Body.Close()
		if cl > 0 {
			return cl
		}
	}
	return 0
}

func StartBackgroundDownload(task *DownloadTask, recordSuccess func(string, int64, float64), recordFailure func(string), onProgress func(ProgressData)) (*DownloadTask, error) {
	if task.PartSizeBytes == 0 {
		task.PartSizeBytes = 4 * 1024 * 1024
	}
	if task.MaxConcurrent == 0 {
		task.MaxConcurrent = 20
	}
	if task.MaxRetry == 0 {
		task.MaxRetry = 3
	}
	if task.Timeout == 0 {
		task.Timeout = 30
	}

	task.Status = "preparing"
	task.CreatedAt = time.Now()

	taskMu.Lock()
	taskID := nextID
	nextID++
	taskMu.Unlock()

	ctx, cancel := context.WithCancel(context.Background())
	taskMu.Lock()
	cancels = append(cancels, cancelEntry{id: taskID, done: cancel})
	taskMu.Unlock()
	defer func() {
		cancel()
		taskMu.Lock()
		for i, c := range cancels {
			if c.id == taskID {
				cancels = append(cancels[:i], cancels[i+1:]...)
				break
			}
		}
		taskMu.Unlock()
	}()

	proxyList := loadActiveProxies()
	log := GetLogger()
	if len(proxyList) == 0 {
		task.Status = "failed"
		return task, fmt.Errorf("no active proxies available")
	}

	task.FileName = guessFileName(task.URL)
	outputPath := filepath.Join(task.SaveDir, task.FileName)



	totalBytes := getFileSizeViaAnyProxy(proxyList, task.URL, time.Duration(task.Timeout)*time.Second)
	if totalBytes == 0 {
		task.Status = "failed"
		return task, fmt.Errorf("unable to determine file size")
	}
	task.TotalBytes = totalBytes

	partSize := task.PartSizeBytes
	if totalBytes < partSize {
		partSize = totalBytes
	}
	numParts := int(totalBytes / partSize)
	if totalBytes%partSize != 0 {
		numParts++
	}

	log.Log("DOWNLOAD READY %s | %d bytes, %d parts @ %d MB, workers=%d proxies=%d", task.URL, totalBytes, numParts, partSize/1024/1024, task.MaxConcurrent, len(proxyList))

	jobs := make([]partJob, numParts)
	for i := range jobs {
		start := int64(i) * partSize
		end := start + partSize - 1
		if end >= totalBytes {
			end = totalBytes - 1
		}
		jobs[i] = partJob{
			index: i,
			start: start,
			end:   end,
			proxy: proxyList[i%len(proxyList)],
		}
	}

	type speedSample struct {
		t  time.Time
		bs int64
	}
	var speedHistory []speedSample
	var rawDownloaded int64
	var confirmedBytes int64
	var histMu sync.Mutex

	calcSpeed := func() float64 {
		now := time.Now()
		histMu.Lock()
		speedHistory = append(speedHistory, speedSample{t: now, bs: confirmedBytes})
		for len(speedHistory) > 0 && now.Sub(speedHistory[0].t) > 10*time.Second {
			speedHistory = speedHistory[1:]
		}
		histMu.Unlock()
		if len(speedHistory) > 1 {
			d := speedHistory[len(speedHistory)-1].t.Sub(speedHistory[0].t).Seconds()
			if d > 0 {
				return float64(speedHistory[len(speedHistory)-1].bs-speedHistory[0].bs) / d
			}
		}
		return 0
	}

	task.Status = "downloading"

	progressCtx, progressCancel := context.WithCancel(ctx)
	defer progressCancel()
	go func() {
		ticker := time.NewTicker(500 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				histMu.Lock()
				d := confirmedBytes
				histMu.Unlock()
				s := calcSpeed()
				if onProgress != nil {
					onProgress(ProgressData{
						Downloaded: d,
						TotalBytes: totalBytes,
						Speed:      s,
					})
				}
			case <-progressCtx.Done():
				return
			}
		}
	}()

	type result struct {
		index int
		err   error
		proxy string
		size  int64
	}

	results := make(chan result, numParts)
	jobCh := make(chan partJob)
	var workerWg sync.WaitGroup

	for w := 0; w < task.MaxConcurrent; w++ {
		workerWg.Add(1)
		go func(workerID int) {
			defer workerWg.Done()
			buf := make([]byte, 64*1024)
			for job := range jobCh {
				if ctx.Err() != nil {
					return
				}

				downloadURL := job.proxy + "/" + task.URL
				req, err := http.NewRequestWithContext(ctx, "GET", downloadURL, nil)
				if err != nil {
					results <- result{index: job.index, err: err, proxy: job.proxy}
					continue
				}
				req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", job.start, job.end))
				ApplyBrowserHeaders(req)

				resp, err := SharedClient.Do(req)
				if err != nil {
					results <- result{index: job.index, err: err, proxy: job.proxy}
					continue
				}

				if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
					resp.Body.Close()
					results <- result{index: job.index, err: fmt.Errorf("HTTP %d", resp.StatusCode), proxy: job.proxy}
					continue
				}

				partFile := fmt.Sprintf("%s.part.%d", outputPath, job.index)
				f, err := os.Create(partFile)
				if err != nil {
					resp.Body.Close()
					results <- result{index: job.index, err: err, proxy: job.proxy}
					continue
				}

				var written int64
				writeOk := true
				for {
					n, readErr := resp.Body.Read(buf)
					if n > 0 {
						if _, werr := f.Write(buf[:n]); werr != nil {
							writeOk = false
							break
						}
						written += int64(n)
						histMu.Lock()
						rawDownloaded += int64(n)
						histMu.Unlock()
					}
					if readErr == io.EOF {
						break
					}
					if readErr != nil {
						writeOk = false
						break
					}
				}
				f.Close()
				resp.Body.Close()

				if !writeOk {
					results <- result{index: job.index, err: fmt.Errorf("part write failed"), proxy: job.proxy}
					continue
				}

				results <- result{index: job.index, err: nil, proxy: job.proxy, size: written}
			}
		}(w)
	}

	go func() {
		for _, job := range jobs {
			jobCh <- job
		}
		close(jobCh)
	}()

	go func() {
		workerWg.Wait()
		close(results)
	}()

	type proxyAttempt struct {
		proxy  string
		bytes  int64
		ok     bool
	}
	var attempts []proxyAttempt
	var failedParts []struct {
		index int
		start int64
		end   int64
	}
	proxyUsed := map[string]int64{}
	allDone := false
	firstErr := fmt.Errorf("all proxies failed")

	for r := range results {
		if r.err != nil {
			domain := r.proxy
			if u, err := url.Parse(r.proxy); err == nil {
				domain = u.Host
			}
			log.Log("PARTFAIL %s part=%d err=%v", domain, r.index, r.err)
			failedParts = append(failedParts, struct {
				index int
				start int64
				end   int64
			}{index: r.index, start: jobs[r.index].start, end: jobs[r.index].end})
			attempts = append(attempts, proxyAttempt{proxy: r.proxy, ok: false})
			if recordFailure != nil {
				recordFailure(domain)
			}
			firstErr = r.err
			continue
		}
		domain := r.proxy
		if u, err := url.Parse(r.proxy); err == nil {
			domain = u.Host
		}
		log.Log("PARTOK %s part=%d bytes=%d", domain, r.index, r.size)
		proxyUsed[r.proxy] = proxyUsed[r.proxy] + r.size
		attempts = append(attempts, proxyAttempt{proxy: r.proxy, bytes: r.size, ok: true})
		histMu.Lock()
		confirmedBytes += r.size
		histMu.Unlock()
		allDone = true
	}

	if len(failedParts) > 0 {
		log.Log("RETRY START failed=%d maxRetry=%d", len(failedParts), task.MaxRetry)
		for i := 0; i < task.MaxRetry && len(failedParts) > 0; i++ {
			if ctx.Err() != nil {
				break
			}
			var stillFailed []struct {
				index int
				start int64
				end   int64
			}
			log.Log("RETRY ROUND %d/%d parts=%d", i+1, task.MaxRetry, len(failedParts))
			for _, fp := range failedParts {
				if ctx.Err() != nil {
					stillFailed = append(stillFailed, fp)
					break
				}
				retryOK := false
				for _, p := range proxyList {
					if ctx.Err() != nil {
						break
					}
					downloadURL := p + "/" + task.URL
					req, err := http.NewRequestWithContext(ctx, "GET", downloadURL, nil)
					if err != nil {
						continue
					}
					req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", fp.start, fp.end))
					ApplyBrowserHeaders(req)

					resp, err := SharedClient.Do(req)
					if err != nil {
						continue
					}
					if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
						resp.Body.Close()
						continue
					}

					partFile := fmt.Sprintf("%s.part.%d", outputPath, fp.index)
					f, _ := os.Create(partFile)
					if f == nil {
						resp.Body.Close()
						continue
					}

					buf := make([]byte, 64*1024)
					var written int64
					writeOk := true
					for {
						n, readErr := resp.Body.Read(buf)
						if n > 0 {
							if _, werr := f.Write(buf[:n]); werr != nil {
								writeOk = false
								break
							}
							written += int64(n)
							histMu.Lock()
							rawDownloaded += int64(n)
							histMu.Unlock()
						}
						if readErr == io.EOF {
							break
						}
						if readErr != nil {
							writeOk = false
							break
						}
					}
					f.Close()
					resp.Body.Close()

					if writeOk && written > 0 {
						proxyUsed[p] = proxyUsed[p] + written
						allDone = true
						retryOK = true
						domain := p
						if u, err := url.Parse(p); err == nil {
							domain = u.Host
						}
						log.Log("RETRYOK %s part=%d bytes=%d", domain, fp.index, written)
						histMu.Lock()
						confirmedBytes += written
						histMu.Unlock()
						break
					}
				}
				if !retryOK {
					stillFailed = append(stillFailed, fp)
					log.Log("RETRYFAIL part=%d (all proxies exhausted)", fp.index)
				}
			}
			failedParts = stillFailed
		}
	}

	if !allDone {
		log.Log("DOWNLOAD FAILED all parts failed: %v", firstErr)
		task.Status = "failed"
		return task, fmt.Errorf("all parts failed: %w", firstErr)
	}
	log.Log("DOWNLOAD COMPLETED %s", task.URL)

	outFile, err := os.Create(outputPath)
	if err != nil {
		task.Status = "failed"
		return task, fmt.Errorf("create output: %w", err)
	}

	buf := make([]byte, 1024*1024)
	for i := 0; i < numParts; i++ {
		partFile := fmt.Sprintf("%s.part.%d", outputPath, i)
		f, err := os.Open(partFile)
		if err != nil {
			continue
		}
		for {
			n, readErr := f.Read(buf)
			if n > 0 {
				if _, werr := outFile.Write(buf[:n]); werr != nil {
					f.Close()
					outFile.Close()
					task.Status = "failed"
					return task, fmt.Errorf("write part %d: %w", i, werr)
				}
			}
			if readErr == io.EOF {
				break
			}
			if readErr != nil {
				break
			}
		}
		f.Close()
		os.Remove(partFile)
	}
	outFile.Close()

	info, _ := os.Stat(outputPath)
	task.TotalBytes = info.Size()
	task.Downloaded = info.Size()
	task.Status = "completed"

	if onProgress != nil {
		onProgress(ProgressData{
			Downloaded: confirmedBytes,
			TotalBytes: totalBytes,
			Speed:      calcSpeed(),
		})
	}

	if recordSuccess != nil {
		log.Log("RECORDING %d proxies:", len(proxyUsed))
		for p, bs := range proxyUsed {
			if bs == 0 {
				continue
			}
			domain := p
			if u, err := url.Parse(p); err == nil {
				domain = u.Host
			}
			log.Log("RECORD %s bytes=%d", domain, bs)
			s := calcSpeed()
			recordSuccess(domain, bs, s)
		}
	}

	return task, nil
}

func guessFileName(rawURL string) string {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return "downloaded_file"
	}
	name := filepath.Base(parsed.Path)
	if name == "" || name == "." || name == "/" {
		return "downloaded_file"
	}
	return name
}
