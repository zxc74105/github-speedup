package core

import (
	"errors"
	"math/rand"
	"sync"
)

type ProxyPool struct {
	mu         sync.Mutex
	queue      []string
	assigned   map[string]string
	ErrorCount int
}

func NewProxyPool(proxies []string) *ProxyPool {
	queue := make([]string, len(proxies))
	copy(queue, proxies)
	rand.Shuffle(len(queue), func(i, j int) {
		queue[i], queue[j] = queue[j], queue[i]
	})
	return &ProxyPool{
		queue:      queue,
		assigned:   make(map[string]string),
		ErrorCount: 0,
	}
}

func (p *ProxyPool) Assign(workerID string) (string, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if proxy, ok := p.assigned[workerID]; ok {
		return proxy, nil
	}
	return p.assignLocked(workerID)
}

func (p *ProxyPool) Fail(workerID string) (string, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	proxy, ok := p.assigned[workerID]
	if !ok {
		return p.assignLocked(workerID)
	}
	p.ErrorCount++
	delete(p.assigned, workerID)
	p.queue = append(p.queue, proxy)
	return p.assignLocked(workerID)
}

func (p *ProxyPool) assignLocked(workerID string) (string, error) {
	if len(p.queue) == 0 {
		return "", errors.New("no proxies available")
	}
	proxy := p.queue[0]
	p.queue = p.queue[1:]
	p.assigned[workerID] = proxy
	return proxy, nil
}

func (p *ProxyPool) Release(workerID string) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	proxy, ok := p.assigned[workerID]
	if !ok {
		return errors.New("no proxy assigned to worker")
	}
	delete(p.assigned, workerID)
	p.queue = append([]string{proxy}, p.queue...)
	return nil
}
