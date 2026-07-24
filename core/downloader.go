package core

import (
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
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
	Status         string // preparing, downloading, paused, completed, failed
	Parts          []FilePart
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
	ID        int
	Proxy     string
	Speed     float64
	Status    string
}

var (
	tasks   []*DownloadTask
	taskMu  sync.Mutex
	nextID  int = 1
	cancels []contextCancel
)

type contextCancel struct {
	id   int
	done func()
}

type progressCallback func(ProgressData)

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

func StartBackgroundDownload(task *DownloadTask, recordSuccess func(string, int64, float64), recordFailure func(string), onProgress func(ProgressData)) (*DownloadTask, error) {
	if task.TotalBytes == 0 {
		length, fileName, err := GetFileInfo(task.URL, "")
		if err != nil {
			return nil, fmt.Errorf("failed to get file info: %w", err)
		}
		task.TotalBytes = length
		task.FileName = fileName
	}
	if task.FileName == "" {
		parsedURL, _ := url.Parse(task.URL)
		task.FileName = filepath.Base(parsedURL.Path)
	}
	if task.PartSizeBytes == 0 {
		task.PartSizeBytes = 10 * 1024 * 1024
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

	task.Parts = DivideFileIntoParts(task.TotalBytes, task.PartSizeBytes)
	task.Status = "downloading"
	task.CreatedAt = time.Now()

	taskMu.Lock()
	taskID := nextID
	nextID++
	taskMu.Unlock()

	var wg sync.WaitGroup
	wg.Add(task.MaxConcurrent)
	var mu sync.Mutex
	var totalDownloaded int64
	var history []struct {
		t  time.Time
		bs int64
	}

	calculateSpeed := func() float64 {
		now := time.Now()
		mu.Lock()
		history = append(history, struct{ t time.Time; bs int64 }{t: now, bs: totalDownloaded})
		for len(history) > 0 && now.Sub(history[0].t) > 10*time.Second {
			history = history[1:]
		}
		mu.Unlock()
		if len(history) > 1 {
			d := history[len(history)-1].t.Sub(history[0].t).Seconds()
			if d > 0 {
				return float64(history[len(history)-1].bs-history[0].bs) / d
			}
		}
		return 0
	}

	// Load proxies
	proxies, _ := ReadLines("proxies.txt")
	pool := NewProxyPool(proxies)

	for i := 0; i < task.MaxConcurrent; i++ {
		go func(workerID int) {
			defer wg.Done()
			for {
				taskMu.Lock()
				if task.Status == "paused" || task.Status == "completed" || task.Status == "failed" {
					taskMu.Unlock()
					return
				}
				taskMu.Unlock()

				// Find next undownloaded part
				mu.Lock()
				partIdx := -1
				for idx, p := range task.Parts {
					if !p.Downloaded {
						partIdx = idx
						break
					}
				}
				mu.Unlock()

				if partIdx == -1 {
					return
				}

				part := task.Parts[partIdx]
				partFileName := fmt.Sprintf("%s.%d.part", task.FileName, part.Number)
				partPath := filepath.Join(task.SaveDir, partFileName)
				partSize := part.End - part.Start + 1

				// Check if part already exists
				if fi, err := os.Stat(partPath); err == nil && fi.Size() == partSize {
					mu.Lock()
					task.Parts[partIdx].Downloaded = true
					totalDownloaded += partSize
					mu.Unlock()
					if onProgress != nil {
						onProgress(ProgressData{TaskID: taskID, Downloaded: totalDownloaded, TotalBytes: task.TotalBytes, PartDone: true})
					}
					continue
				}

				proxyURL, err := pool.Assign(strconv.Itoa(workerID))
				if err != nil {
					continue
				}

				var localDownloaded int64
				retries := 0
				for retries <= task.MaxRetry {
					_, err := DownloadPartialFile(task.URL, proxyURL, partPath, part.Start, part.End, time.Duration(task.Timeout)*time.Second, func(n int64) {
						mu.Lock()
						totalDownloaded += n
						localDownloaded += n
						spd := calculateSpeed()
						task.Downloaded = totalDownloaded
						task.Speed = spd
						if spd > 0 {
							eta := float64(task.TotalBytes-totalDownloaded) / spd
							task.ETA = fmt.Sprintf("%.0fs", eta)
						}
						mu.Unlock()

						if onProgress != nil {
							onProgress(ProgressData{
								TaskID:      taskID,
								Downloaded:  totalDownloaded,
								TotalBytes:  task.TotalBytes,
								Speed:       spd,
								WorkerID:    workerID,
								WorkerProxy: proxyURL,
							})
						}
					})
					if err != nil {
						os.Remove(partPath)
						mu.Lock()
						totalDownloaded -= localDownloaded
						localDownloaded = 0
						mu.Unlock()
						if recordFailure != nil {
							recordFailure(proxyURL)
						}
						proxyURL, _ = pool.Fail(strconv.Itoa(workerID))
						taskMu.Lock()
						task.ProxySwitchCnt++
						taskMu.Unlock()
						retries++
						continue
					}

					// Verify size
					fi, err := os.Stat(partPath)
					if err != nil || fi.Size() != partSize {
						os.Remove(partPath)
						mu.Lock()
						totalDownloaded -= localDownloaded
						localDownloaded = 0
						mu.Unlock()
						retries++
						continue
					}

					pool.Release(strconv.Itoa(workerID))
					mu.Lock()
					task.Parts[partIdx].Downloaded = true
					task.WorkerCount++
					mu.Unlock()

					if recordSuccess != nil {
						domain := proxyURL
						if u, err := url.Parse(proxyURL); err == nil {
							domain = u.Host
						}
						recordSuccess(domain, partSize, calculateSpeed())
					}
					break
				}
			}
		}(i)
	}

	wg.Wait()

	// Concatenate
	outPath := filepath.Join(task.SaveDir, task.FileName)
	if err := ConcatenateFiles(outPath, task.SaveDir); err != nil {
		task.Status = "failed"
		return task, fmt.Errorf("concatenation failed: %w", err)
	}

	// Verify
	if fi, _ := os.Stat(outPath); fi != nil && fi.Size() == task.TotalBytes {
		task.Status = "completed"
	} else {
		task.Status = "failed"
	}

	task.Downloaded = task.TotalBytes
	return task, nil
}
