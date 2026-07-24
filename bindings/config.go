package bindings

import (
	"encoding/json"
	"os"
	"path/filepath"
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
	settingsPath string
}

func NewConfigAPI() *ConfigAPI {
	home, _ := os.UserHomeDir()
	dir := filepath.Join(home, ".multi-proxy-downloader")
	os.MkdirAll(dir, 0755)
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
		EnableHTTPAPI:     false,
		HTTPAPIPort:       9090,
		AllowRemoteAccess: false,
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
	home, _ := os.UserHomeDir()
	src := filepath.Join(home, ".multi-proxy-downloader", "proxy-records.json")
	dst := filepath.Join(home, "Desktop", "proxy-records-export.json")
	data, err := os.ReadFile(src)
	if err != nil {
		return "", err
	}
	os.WriteFile(dst, data, 0644)
	return dst, nil
}

func (c *ConfigAPI) ClearRecords() error {
	home, _ := os.UserHomeDir()
	path := filepath.Join(home, ".multi-proxy-downloader", "proxy-records.json")
	return os.WriteFile(path, []byte("[]"), 0644)
}
