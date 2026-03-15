# Clash 订阅管理器

管理本地 Clash 配置文件，支持远程订阅源自动更新，生成订阅链接供其他设备使用。

## 功能

- 📋 **节点管理**: 增删改查代理节点
- 🌐 **远程订阅源**: 支持添加远程订阅 URL，自动解析并更新
- 🔗 **订阅生成**: 创建多个订阅，支持节点过滤
- 🔒 **访问控制**: 仅允许 Clash 客户端访问订阅内容
- 📝 **自动命名**: Clash 自动识别订阅名称
- 🎯 **多格式输出**: 支持 Clash YAML 和 Base64 格式
- 🚀 **HTTP 服务**: 提供 HTTPS 订阅链接供其他设备访问

## 安装

```bash
cd ~/tools/clash-sub-manager

# 使用 uv 安装（推荐）
uv tool install .

# 全局命令
clash-sub --help
```

## 快速开始

```bash
# 1. 添加远程订阅源
clash-sub source-add "我的机场" "https://example.com/subscribe/xxx"

# 2. 更新订阅源
clash-sub source-update

# 3. 查看节点
clash-sub list

# 4. 创建订阅
clash-sub sub-create "手机订阅" --base-url "https://your-domain/clash-sub"

# 5. 在 Clash 中添加订阅地址
# https://your-domain/clash-sub/sub/<token>
```

## 命令详解

### 规则集管理

```bash
# 列出内置规则集
clash-sub provider-list-builtin

# 添加规则集（使用内置规则集）
clash-sub provider-add google 美国
clash-sub provider-add youtube 美国
clash-sub provider-add telegram 香港
clash-sub provider-add github 美国

# 添加自定义规则集
clash-sub provider-add my-rules 美国 --url "https://example.com/rules.yaml"

# 列出已添加的规则集
clash-sub provider-list

# 删除规则集
clash-sub provider-remove google
```

内置规则集：
| 键名 | 说明 |
|------|------|
| google | Google 服务 |
| youtube | YouTube 视频平台 |
| telegram | Telegram 即时通讯 |
| twitter | Twitter/X 社交平台 |
| github | GitHub 代码托管 |
| openai | OpenAI/ChatGPT |
| anthropic | Anthropic/Claude AI |
| spotify | Spotify 音乐 |
| netflix | Netflix 流媒体 |
| discord | Discord 社区平台 |
| tiktok | TikTok 短视频 |
| facebook | Facebook 社交平台 |
| instagram | Instagram 图片社交 |
| whatsapp | WhatsApp 即时通讯 |
| cloudflare | Cloudflare CDN |
| notion | Notion 笔记 |

### 节点管理

```bash
# 列出所有节点（按来源分组）
clash-sub list

# 添加节点
clash-sub add "香港01" --type trojan --server example.com --port 443 --password "xxx"
clash-sub add "美国01" --type vmess --server example.com --port 443 --uuid "xxx"

# 删除节点
clash-sub delete "香港01"

# 清空节点
clash-sub clear                    # 清空所有
clash-sub clear --source <订阅源ID>  # 清空指定源
```

### 远程订阅源

```bash
# 列出所有订阅源
clash-sub source-list

# 添加订阅源
clash-sub source-add "机场A" "https://xxx"
clash-sub source-add "机场B" "https://yyy" --interval 7200  # 每2小时更新

# 更新订阅源
clash-sub source-update          # 更新全部
clash-sub source-update abc123   # 更新指定源

# 删除订阅源
clash-sub source-remove <ID>
```

### 订阅管理

```bash
# 创建订阅
clash-sub sub-create "我的订阅" --base-url "https://your-domain/clash-sub"

# 按关键词过滤
clash-sub sub-create "香港订阅" --keywords "香港,HK" --base-url "https://..."

# 按订阅源过滤
clash-sub sub-create "机场A订阅" --sources <订阅源ID> --base-url "https://..."

# 列出所有订阅
clash-sub sub-list

# 删除订阅
clash-sub sub-delete <token>
```

### HTTP 服务

```bash
# 命令行启动（开发/测试）
clash-sub serve --port 8080

# 生产环境使用 systemd
systemctl start clash-sub
systemctl enable clash-sub
systemctl status clash-sub
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页（浏览器可访问） |
| `/proxies` | GET | 列出所有节点 (JSON) |
| `/sources` | GET | 列出所有订阅源 (JSON) |
| `/sources/update` | GET | 更新所有订阅源 |
| `/subscriptions` | GET | 列出所有订阅 (JSON) |
| `/sub/{token}` | GET | 获取订阅内容 (Clash YAML) |
| `/sub/{token}/base64` | GET | 获取订阅内容 (Base64) |

### 访问控制

订阅端点 (`/sub/*`) **仅允许 Clash 客户端访问**。

支持的客户端 User-Agent：
- Clash / ClashX / ClashMeta
- Stash
- Shadowrocket
- V2Ray (Base64 格式)

浏览器直接访问会返回 403 错误：
```json
{"detail":"此订阅仅限 Clash 客户端访问。请在 Clash 中添加此订阅链接。"}
```

### 订阅文件名

订阅响应包含 `Content-Disposition` header，Clash 会自动识别为订阅名称：

```
Content-Disposition: attachment; filename="订阅名称.yaml"
profile-update-interval: 24
```

## 支持的订阅格式

管理器支持解析以下订阅格式：

| 格式 | 说明 |
|------|------|
| Clash YAML | 直接解析 `proxies` 字段 |
| Base64 编码 | V2Ray 订阅格式 |
| vmess:// | VMess 协议链接 |
| trojan:// | Trojan 协议链接 |
| ss:// | Shadowsocks 链接 |
| ssr:// | ShadowsocksR 链接 |

## 文件结构

```
clash-sub-manager/
├── main.py          # 主程序
├── config.yaml      # Clash 配置文件
├── sources.json     # 远程订阅源数据库
├── subs.json        # 订阅数据库
├── pyproject.toml   # Python 项目配置
└── README.md        # 说明文档
```

## 配置文件说明

### config.yaml

主配置文件，包含：
- Clash 基础设置 (port, dns, rules 等)
- 代理节点 (proxies)
- 代理组 (proxy-groups)

### sources.json

远程订阅源数据库：
```json
[
  {
    "id": "abc123",
    "name": "我的机场",
    "url": "https://...",
    "auto_update": true,
    "interval": 3600,
    "last_update": "2026-03-11T00:00:00",
    "proxy_count": 10
  }
]
```

### subs.json

订阅数据库：
```json
{
  "token123": {
    "name": "手机订阅",
    "created": "2026-03-11T00:00:00",
    "filters": {
      "keywords": ["香港", "HK"]
    },
    "access_count": 5
  }
}
```

## Caddy 反向代理配置

```caddyfile
# /etc/caddy/233boy/bbddl1.92ac.cn.conf.add

# Clash 订阅管理器
handle /clash-sub/* {
    uri strip_prefix /clash-sub
    reverse_proxy http://127.0.0.1:8080
}
```

## Systemd 服务

```ini
# /etc/systemd/system/clash-sub.service

[Unit]
Description=Clash Subscription Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/tools/clash-sub-manager
ExecStart=/root/tools/clash-sub-manager/.venv/bin/python main.py serve --host 127.0.0.1 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

管理命令：
```bash
systemctl start clash-sub    # 启动
systemctl stop clash-sub     # 停止
systemctl restart clash-sub  # 重启
systemctl status clash-sub   # 状态
journalctl -u clash-sub -f   # 日志
```

## 使用示例

### 添加机场订阅

```bash
# 1. 添加订阅源
clash-sub source-add "V2ray" "https://sub.example.com/link/abc123"

# 2. 更新获取节点
clash-sub source-update

# 3. 查看节点
clash-sub list
# 输出:
#   [V2ray]
#     • [V2ray] 香港 IPLC 01 (vmess)
#     • [V2ray] 日本 BGP 02 (trojan)

# 4. 创建订阅
clash-sub sub-create "手机订阅" --keywords "香港,HK" --base-url "https://bbddl1.92ac.cn/clash-sub"

# 输出:
#   ✓ 订阅创建成功!
#   名称: 手机订阅
#   Token: xyz789
#   订阅地址: https://bbddl1.92ac.cn/clash-sub/sub/xyz789
```

### 在 Clash 中添加订阅

1. 打开 Clash 客户端
2. 进入「配置」/「Profiles」
3. 添加订阅地址：`https://bbddl1.92ac.cn/clash-sub/sub/xyz789`
4. Clash 会自动识别订阅名称为「手机订阅」

## 常见问题

### Q: 浏览器访问订阅链接显示 403？

A: 这是正常的。订阅链接仅允许 Clash 客户端访问。请在 Clash 中添加订阅地址。

### Q: 如何更新节点？

A: 使用 `clash-sub source-update` 更新远程订阅源，或手动添加/删除节点。

### Q: 如何查看访问日志？

A: 查看 systemd 日志：`journalctl -u clash-sub -f`

## 开发

```bash
# 克隆/进入项目目录
cd ~/tools/clash-sub-manager

# 创建虚拟环境
uv venv .venv
source .venv/bin/activate

# 安装依赖
uv pip install pyyaml fastapi uvicorn httpx

# 运行
python main.py --help
```

## License

MIT