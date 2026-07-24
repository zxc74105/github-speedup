package bindings

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"

	"multi-proxy-downloader/core"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

type DownloadAPI struct {
	ctx          context.Context
	tasks        []*TaskInfo
	mu           sync.Mutex
	nextID       int
	successRecs  []ProxyRecord
	recordsPath  string
}

type TaskInfo struct {
	ID             int       `json:"id"`
	URL            string    `json:"url"`
	FileName       string    `json:"fileName"`
	SaveDir        string    `json:"saveDir"`
	TotalBytes     int64     `json:"totalBytes"`
	Downloaded     int64     `json:"downloaded"`
	Speed          float64   `json:"speed"`
	ETA            string    `json:"eta"`
	Status         string    `json:"status"`
	WorkerCount    int       `json:"workerCount"`
	ProxySwitchCnt int       `json:"proxySwitchCnt"`
	Progress       float64   `json:"progress"`
	CreatedAt      time.Time `json:"createdAt"`
}

type ProxyRecord struct {
	Domain       string    `json:"domain"`
	SuccessCount int       `json:"successCount"`
	TotalBytes   int64     `json:"totalBytes"`
	AverageSpeed float64   `json:"averageSpeed"`
	FailCount    int       `json:"failCount"`
	FirstUsedAt  time.Time `json:"firstUsedAt"`
	LastUsedAt   time.Time `json:"lastUsedAt"`
	SpeedHistory []float64 `json:"speedHistory"`
}

type CreateTaskReq struct {
	URL      string `json:"url"`
	SaveDir  string `json:"saveDir"`
	Concurrency int `json:"concurrency"`
	PartSize int    `json:"partSize"`
	MaxRetry int    `json:"maxRetry"`
	Timeout  int    `json:"timeout"`
}

func (d *DownloadAPI) SetCtx(ctx context.Context) {
	d.ctx = ctx
}

func NewDownloadAPI(ctx context.Context) *DownloadAPI {
	home, _ := os.UserHomeDir()
	recordsDir := filepath.Join(home, ".multi-proxy-downloader")
	os.MkdirAll(recordsDir, 0755)
	recordsPath := filepath.Join(recordsDir, "proxy-records.json")

	api := &DownloadAPI{
		ctx:         ctx,
		nextID:      1,
		recordsPath: recordsPath,
	}
	api.loadRecords()
	return api
}

func (d *DownloadAPI) loadRecords() {
	data, err := os.ReadFile(d.recordsPath)
	if err != nil {
		d.successRecs = []ProxyRecord{}
		return
	}
	json.Unmarshal(data, &d.successRecs)
}

func (d *DownloadAPI) saveRecords() {
	data, _ := json.MarshalIndent(d.successRecs, "", "  ")
	os.WriteFile(d.recordsPath, data, 0644)
}

func (d *DownloadAPI) CreateTask(req CreateTaskReq) (*TaskInfo, error) {
	if req.SaveDir == "" {
		home, _ := os.UserHomeDir()
		req.SaveDir = filepath.Join(home, "Downloads")
	}
	if req.Concurrency == 0 {
		req.Concurrency = 20
	}
	if req.PartSize == 0 {
		req.PartSize = 10
	}
	if req.MaxRetry == 0 {
		req.MaxRetry = 3
	}
	if req.Timeout == 0 {
		req.Timeout = 30
	}

	task := &core.DownloadTask{
		URL:           req.URL,
		SaveDir:       req.SaveDir,
		PartSizeBytes: int64(req.PartSize) * 1024 * 1024,
		MaxConcurrent: req.Concurrency,
		MaxRetry:      req.MaxRetry,
		Timeout:       req.Timeout,
	}

	onProgress := func(p core.ProgressData) {
		runtime.EventsEmit(d.ctx, "download:progress", p)
	}

	recordSuccess := func(domain string, bytes int64, speed float64) {
		d.mu.Lock()
		defer d.mu.Unlock()
		found := false
		for i, rec := range d.successRecs {
			if rec.Domain == domain {
				d.successRecs[i].SuccessCount++
				d.successRecs[i].TotalBytes += bytes
				d.successRecs[i].LastUsedAt = time.Now()
				// Rolling average
				totalSpeed := rec.AverageSpeed * float64(rec.SuccessCount-1) + speed
				d.successRecs[i].AverageSpeed = totalSpeed / float64(rec.SuccessCount)
				d.successRecs[i].SpeedHistory = append(d.successRecs[i].SpeedHistory, speed)
				if len(d.successRecs[i].SpeedHistory) > 100 {
					d.successRecs[i].SpeedHistory = d.successRecs[i].SpeedHistory[1:]
				}
				found = true
				break
			}
		}
		if !found {
			d.successRecs = append(d.successRecs, ProxyRecord{
				Domain:       domain,
				SuccessCount: 1,
				TotalBytes:   bytes,
				AverageSpeed: speed,
				FirstUsedAt:  time.Now(),
				LastUsedAt:   time.Now(),
				SpeedHistory: []float64{speed},
			})
		}
		d.saveRecords()
	}

	recordFailure := func(domain string) {
		d.mu.Lock()
		defer d.mu.Unlock()
		for i, rec := range d.successRecs {
			if rec.Domain == domain {
				d.successRecs[i].FailCount++
				break
			}
		}
		d.saveRecords()
	}

	result, err := core.StartBackgroundDownload(task, recordSuccess, recordFailure, onProgress)
	if err != nil {
		return nil, err
	}

	info := &TaskInfo{
		ID:         d.nextID,
		URL:        result.URL,
		FileName:   result.FileName,
		SaveDir:    result.SaveDir,
		TotalBytes: result.TotalBytes,
		Downloaded: result.Downloaded,
		Speed:      result.Speed,
		ETA:        result.ETA,
		Status:     result.Status,
		CreatedAt:  result.CreatedAt,
	}
	if result.TotalBytes > 0 {
		info.Progress = float64(result.Downloaded) / float64(result.TotalBytes) * 100
	}

	d.mu.Lock()
	info.ID = d.nextID
	d.nextID++
	d.tasks = append(d.tasks, info)
	d.mu.Unlock()

	return info, nil
}

func (d *DownloadAPI) GetTasks() []*TaskInfo {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.tasks
}

func (d *DownloadAPI) GetSuccessRecords() []ProxyRecord {
	d.mu.Lock()
	defer d.mu.Unlock()
	sorted := make([]ProxyRecord, len(d.successRecs))
	copy(sorted, d.successRecs)
	sort.Slice(sorted, func(i, j int) bool {
		if sorted[i].SuccessCount != sorted[j].SuccessCount {
			return sorted[i].SuccessCount > sorted[j].SuccessCount
		}
		return sorted[i].AverageSpeed > sorted[j].AverageSpeed
	})
	return sorted
}

func (d *DownloadAPI) DeleteProxies(domains []string) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	keep := []ProxyRecord{}
	for _, rec := range d.successRecs {
		shouldDelete := false
		for _, dom := range domains {
			if rec.Domain == dom {
				shouldDelete = true
				break
			}
		}
		if !shouldDelete {
			keep = append(keep, rec)
		}
	}
	d.successRecs = keep
	d.saveRecords()
	return nil
}
