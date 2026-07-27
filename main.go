package main

import (
	"context"
	"embed"

	"multi-proxy-downloader/bindings"

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"github.com/wailsapp/wails/v2/pkg/options/linux"
	"github.com/wailsapp/wails/v2/pkg/options/mac"
	"github.com/wailsapp/wails/v2/pkg/options/windows"
)

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	downloadAPI := bindings.NewDownloadAPI(context.Background())
	proxyAPI := bindings.NewProxyAPI(context.Background())
	configAPI := bindings.NewConfigAPI()
	httpService := bindings.NewHTTPService(proxyAPI, downloadAPI)
	serverAPI := bindings.NewServerAPI(httpService)

	app := &App{}

	err := wails.Run(&options.App{
		Title:     "Multi-Proxy Downloader",
		Width:     1000,
		Height:    780,
		MinWidth:  800,
		MinHeight: 600,
		AssetServer: &assetserver.Options{
			Assets: assets,
		},
		BackgroundColour: &options.RGBA{R: 245, G: 246, B: 248, A: 1},
		OnStartup: func(ctx context.Context) {
			bindings.InitLogger()
			app.ctx = ctx
			app.Download = downloadAPI
			app.Proxy = proxyAPI
			app.Config = configAPI
			downloadAPI.SetCtx(ctx)
			proxyAPI.SetCtx(ctx)
			configAPI.SetCtx(ctx)

			// Auto-start HTTP API if enabled in settings
			settings := configAPI.GetSettings()
			if settings.EnableHTTPAPI {
				go httpService.Start(settings.HTTPAPIPort, settings.AllowRemoteAccess)
			}
		},
		Bind: []interface{}{
			downloadAPI,
			proxyAPI,
			configAPI,
			serverAPI,
		},
		Windows: &windows.Options{
			WebviewIsTransparent: true,
		},
		Mac: &mac.Options{
			Appearance: mac.NSAppearanceNameAqua,
		},
		Linux: &linux.Options{},
	})

	if err != nil {
		println("Error:", err.Error())
	}
}
