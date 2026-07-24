package main

import (
	"context"
	"multi-proxy-downloader/bindings"
)

type App struct {
	ctx      context.Context
	Download *bindings.DownloadAPI
	Proxy    *bindings.ProxyAPI
	Config   *bindings.ConfigAPI
}

func NewApp() *App {
	return &App{}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	if a.Download == nil {
		a.Download = bindings.NewDownloadAPI(ctx)
	}
	if a.Proxy == nil {
		a.Proxy = bindings.NewProxyAPI(ctx)
	}
	if a.Config == nil {
		a.Config = bindings.NewConfigAPI()
	}
}
