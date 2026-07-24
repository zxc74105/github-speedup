package bindings

type ServerAPI struct {
	service *HTTPService
}

func NewServerAPI(service *HTTPService) *ServerAPI {
	return &ServerAPI{service: service}
}

func (s *ServerAPI) Start(port int, allowRemote bool) error {
	return s.service.Start(port, allowRemote)
}

func (s *ServerAPI) Stop() error {
	return s.service.Stop()
}

func (s *ServerAPI) IsRunning() bool {
	return s.service.IsRunning()
}

func (s *ServerAPI) GetAddress() string {
	return s.service.GetAddress()
}
