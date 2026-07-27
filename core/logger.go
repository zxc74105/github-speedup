package core

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type AccessLogger struct {
	mu       sync.Mutex
	filePath string
}

var globalLogger *AccessLogger

func InitLogger() *AccessLogger {
	dir := AppDir()
	path := filepath.Join(dir, "proxy-access.log")
	f, err := os.Create(path)
	if err != nil {
		return nil
	}
	f.Close()

	l := &AccessLogger{filePath: path}
	globalLogger = l
	return l
}

func GetLogger() *AccessLogger {
	return globalLogger
}

func (l *AccessLogger) Log(format string, args ...interface{}) {
	if l == nil {
		return
	}
	l.mu.Lock()
	defer l.mu.Unlock()

	msg := fmt.Sprintf(format, args...)
	line := fmt.Sprintf("[%s] %s\n", time.Now().Format("2006-01-02 15:04:05.000"), msg)

	f, err := os.OpenFile(l.filePath, os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.WriteString(line)
}
