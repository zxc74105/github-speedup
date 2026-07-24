# 视图19-CLI命令结构与参数图

## 命令结构

本项目为**单命令** CLI 工具，无子命令：

```
mpd.exe [参数]    (所有参数均为可选的 flag)
```

工作模式仅一种：**下载文件**（无其他子命令模式）

## 参数全景

```
mpd.exe

  📌 必需参数 (至少提供 -url)
  ├── -url string        下载文件 URL

  📌 输出控制
  ├── -output string     输出文件路径 (默认: 从 URL 自动提取文件名)
  ├── -overwrite         覆盖已存在的输出文件

  📌 代理配置
  ├── -proxy string      代理列表文件路径 (默认: "proxies.txt")

  📌 并发控制
  ├── -max int           最大并发下载数 (默认: 30)
  ├── -part int          每分片大小 MB (默认: 10)

  📌 容错控制
  ├── -retry int         失败重试次数 (默认: 2)
  ├── -timeout int       无数据超时秒数 (默认: 20)

  📌 输出格式
  ├── -verbose           详细日志模式 (关闭进度条)
  ├── -json-output       JSON 格式日志输出 (自动启用 verbose)

  📌 调试
  ├── -debug             调试日志
  ├── -debug-proxy       代理调试日志

  📌 其他
  └── -v                 显示版本号并退出
```

## 常用参数组合

```
# 1. 最小使用 (只需 URL)
mpd.exe -url "https://example.com/file.zip"
# 自动使用 proxies.txt，自动命名输出文件

# 2. 指定输出路径和代理列表
mpd.exe -url "https://example.com/file.zip" ^
        -output "D:\downloads\file.zip" ^
        -proxy "D:\my-proxies.txt"

# 3. 高并发大文件下载
mpd.exe -url "https://example.com/big-file.iso" ^
        -max 50 -part 20 -verbose

# 4. 低速网络 (提高容错)
mpd.exe -url "https://example.com/file.zip" ^
        -retry 5 -timeout 60 -max 10

# 5. 调试模式
mpd.exe -url "https://example.com/file.zip" ^
        -debug -debug-proxy -verbose

# 6. JSON 输出 (对接其他程序)
mpd.exe -url "https://example.com/file.zip" ^
        -json-output

# 7. 覆盖已有文件
mpd.exe -url "https://example.com/file.zip" ^
        -output "D:\downloads\file.zip" -overwrite

# 8. 覆盖已有文件 + 高并发
mpd.exe -url "https://example.com/file.zip" -overwrite -max 50 -part 20
```

## 参数关系图

```
                        ┌──────────────────┐
                        │  -url (必需)      │
                        │  下载目标 URL     │
                        └────────┬─────────┘
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
                  ▼                             ▼
        ┌──────────────────┐          ┌──────────────────┐
        │  -proxy           │          │  -part            │
        │  代理列表文件      │          │  分片大小 (MB)    │
        │  (默认proxies.txt)│          │  (默认 10)        │
        └────────┬─────────┘          └────────┬─────────┘
                 │                             │
                 ▼                             ▼
        ┌──────────────────┐                   │
        │  -max             │                   │
        │  最大并发数        │◄──────────────────┘
        │  (默认 30)        │     分片数 = ceil(文件大小 / part)
        └────────┬─────────┘     实际并发 = min(max, 分片数)
                 │
                 ▼
        ┌──────────────────┐          ┌──────────────────┐
        │  -retry           │          │  -timeout         │
        │  失败重试次数      │          │  无数据超时 (秒)  │
        │  (默认 2)         │          │  (默认 20)        │
        └────────┬─────────┘          └────────┬─────────┘
                 │                             │
                 └──────────────┬──────────────┘
                                ▼
                       ┌──────────────────┐
                       │  Worker 执行下载   │
                       └────────┬─────────┘
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
                 ▼                             ▼
        ┌──────────────────┐          ┌──────────────────┐
        │  -verbose         │          │  -json-output     │
        │  详细模式          │          │  JSON 输出       │
        └──────────────────┘          └──────────────────┘
                 │                             │
                 └──────────────┬──────────────┘
                                ▼
                       ┌──────────────────┐
                       │  -output          │
                       │  输出文件路径     │
                       │  (自动提取/指定)  │
                       └──────────────────┘
```

## 参数默认值速查

| 参数 | 默认值 | 单位 | 作用域 |
|------|--------|------|--------|
| `-url` | "" (空) | - | 全局 |
| `-output` | 从 URL 提取 | - | 全局 |
| `-proxy` | "proxies.txt" | - | 全局 |
| `-max` | 30 | 连接数 | 全局 |
| `-part` | 10 | MB | 全局 |
| `-retry` | 2 | 次数 | per-part |
| `-timeout` | 20 | 秒 | per-connection |
| `-overwrite` | false | - | 全局 |
| `-verbose` | false | - | 全局 |
| `-json-output` | false | - | 全局 |
| `-debug` | false | - | 全局 |
| `-debug-proxy` | false | - | 全局 |
