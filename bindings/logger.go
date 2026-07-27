package bindings

import "multi-proxy-downloader/core"

func InitLogger() *core.AccessLogger {
	return core.InitLogger()
}

func GetLogger() *core.AccessLogger {
	return core.GetLogger()
}
