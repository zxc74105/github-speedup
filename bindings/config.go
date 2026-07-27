package bindings

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"

	"multi-proxy-downloader/core"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

type Settings struct {
	DefaultSaveDir       string  `json:"defaultSaveDir"`
	DefaultConcurrency   int     `json:"defaultConcurrency"`
	PartSize             int     `json:"partSize"`
	MaxRetry             int     `json:"maxRetry"`
	Timeout              int     `json:"timeout"`
	AutoTestOnStart      bool    `json:"autoTestOnStart"`
	SilentSpeedThreshold float64 `json:"silentSpeedThreshold"`
	SilentLatencyThreshold int   `json:"silentLatencyThreshold"`
	TCPTimeout           int     `json:"tcpTimeout"`
	TestFileSize         string  `json:"testFileSize"`
	Theme                string  `json:"theme"`
	Language             string  `json:"language"`
	CheckUpdate          bool    `json:"checkUpdate"`
	EnableHTTPAPI        bool    `json:"enableHTTPAPI"`
	HTTPAPIPort          int     `json:"httpAPIPort"`
	AllowRemoteAccess    bool    `json:"allowRemoteAccess"`
}

type ConfigAPI struct {
	ctx          context.Context
	settingsPath string
}

func (c *ConfigAPI) SetCtx(ctx context.Context) {
	c.ctx = ctx
}

func (c *ConfigAPI) PickDirectory() (string, error) {
	if c.ctx == nil {
		return "", nil
	}
	dir, err := runtime.OpenDirectoryDialog(c.ctx, runtime.OpenDialogOptions{
		Title: "选择下载目录",
	})
	if err != nil {
		return "", err
	}
	return dir, nil
}

func NewConfigAPI() *ConfigAPI {
	dir := core.AppDir()
	api := &ConfigAPI{
		settingsPath: filepath.Join(dir, "settings.json"),
	}
	return api
}

func (c *ConfigAPI) getDefaults() Settings {
	home, _ := os.UserHomeDir()
	return Settings{
		DefaultSaveDir:     filepath.Join(home, "Downloads"),
		DefaultConcurrency: 20,
		PartSize:           10,
		MaxRetry:           3,
		Timeout:            30,
		AutoTestOnStart:    true,
		SilentSpeedThreshold: 1.0,
		SilentLatencyThreshold: 500,
		TCPTimeout:         5,
		TestFileSize:       "1 MB",
		Theme:              "light",
		Language:           "zh-CN",
		CheckUpdate:        true,
		EnableHTTPAPI:     true,
		HTTPAPIPort:       9090,
		AllowRemoteAccess: true,
	}
}

func (c *ConfigAPI) GetSettings() Settings {
	data, err := os.ReadFile(c.settingsPath)
	if err != nil {
		return c.getDefaults()
	}
	var s Settings
	if json.Unmarshal(data, &s) != nil {
		return c.getDefaults()
	}
	return s
}

func (c *ConfigAPI) SaveSettings(s Settings) error {
	data, _ := json.MarshalIndent(s, "", "  ")
	return os.WriteFile(c.settingsPath, data, 0644)
}

func (c *ConfigAPI) ResetSettings() Settings {
	def := c.getDefaults()
	c.SaveSettings(def)
	return def
}

func (c *ConfigAPI) ExportRecords() (string, error) {
	dir := core.AppDir()
	src := filepath.Join(dir, "proxy-records.json")
	dst := filepath.Join(dir, "proxy-records-export.json")
	data, err := os.ReadFile(src)
	if err != nil {
		return "", err
	}
	os.WriteFile(dst, data, 0644)
	return dst, nil
}

func (c *ConfigAPI) ClearRecords() error {
	dir := core.AppDir()
	path := filepath.Join(dir, "proxy-records.json")
	return os.WriteFile(path, []byte("[]"), 0644)
}
