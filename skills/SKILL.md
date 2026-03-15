# Clash 订阅管理器 Skill

管理本地 Clash 配置文件，支持远程订阅源自动更新、规则集管理，生成订阅链接供其他设备使用。

---

## 安装

```bash
# 克隆仓库
cd ~/tools
git clone https://github.com/deepwzh/clash-sub-manager.git
cd clash-sub-manager

# 创建虚拟环境并安装依赖
uv venv .venv
source .venv/bin/activate
uv pip install pyyaml fastapi uvicorn httpx

# 安装为全局命令
uv tool install .

# 验证安装
clash-sub --help
```

---

## 快速开始

```bash
# 1. 添加远程订阅源
clash-sub source-add "我的机场" "https://example.com/subscribe/xxx"

# 2. 更新订阅源（获取节点）
clash-sub source-update

# 3. 查看节点
clash-sub list

# 4. 添加规则集
clash-sub provider-add google <代理组名>
clash-sub provider-add youtube <代理组名>

# 5. 创建订阅
clash-sub sub-create "我的订阅" --base-url "https://your-domain/clash-sub"

# 6. 启动服务
clash-sub serve --port 8080
```

---

## 命令详解

### 节点管理

```bash
# 列出所有节点
clash-sub list

# 通过 URL 添加节点
clash-sub add-url "vmess://xxx" --name "节点名称"
clash-sub add-url "trojan://password@server:443?sni=xxx#节点名称"

# 删除节点
clash-sub delete "节点名称"

# 清空节点
clash-sub clear
```

### 订阅源管理

```bash
# 列出订阅源
clash-sub source-list

# 添加订阅源
clash-sub source-add "机场名" "https://订阅URL"

# 更新订阅源
clash-sub source-update          # 更新全部
clash-sub source-update <ID>     # 更新指定源

# 删除订阅源
clash-sub source-remove <ID>
```

### 规则集管理

```bash
# 列出内置规则集
clash-sub provider-list-builtin

# 添加规则集（绑定到指定代理组）
clash-sub provider-add google <代理组名>
clash-sub provider-add youtube <代理组名>
clash-sub provider-add telegram <代理组名>

# 添加自定义规则集
clash-sub provider-add my-rules <代理组名> --url "https://example.com/rules.yaml"

# 列出已添加的规则集
clash-sub provider-list

# 删除规则集
clash-sub provider-remove google
```

**内置规则集：**

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

### 订阅管理

```bash
# 创建订阅
clash-sub sub-create "订阅名称" --base-url "https://your-domain/clash-sub"

# 按关键词过滤
clash-sub sub-create "香港订阅" --keywords "香港,HK" --base-url "https://..."

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

---

## 配置代理组

规则集需要绑定到代理组，代理组在 `config.yaml` 中配置：

```yaml
proxy-groups:
  - name: Proxies
    type: select
    proxies:
      - 自动选择
      - 手动选择
  
  - name: 自动选择
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
      - 节点1
      - 节点2
  
  - name: Google
    type: select
    proxies:
      - 节点1
      - 节点2
      - Proxies
```

然后添加规则集绑定到代理组：

```bash
clash-sub provider-add google Google
```

---

## 客户端兼容性

订阅服务会根据客户端 User-Agent 自动适配输出格式：

| 客户端 | User-Agent 示例 | 输出格式 |
|--------|-----------------|----------|
| ClashX Meta | `ClashX Meta/v1.4.31` | 包含 rule-providers |
| Clash.Meta | `Clash.Meta` | 包含 rule-providers |
| Mihomo | `Mihomo` | 包含 rule-providers |
| 原版 Clash/ClashX | `ClashX/1.118.0` | 不含 rule-providers，兼容格式 |
| Stash/Shadowrocket | `Stash` / `Shadowrocket` | 包含 rule-providers |
| 浏览器 | `Mozilla/5.0` | 403 错误 |

**注意：** `RULE-SET` 语法仅 Clash Meta 内核支持，原版 Clash 客户端会报错。使用原版 Clash 请升级到 ClashX Meta 或 Mihomo 版本。

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页 |
| `/proxies` | GET | 列出所有节点 (JSON) |
| `/sources` | GET | 列出所有订阅源 (JSON) |
| `/sources/update` | GET | 更新所有订阅源 |
| `/subscriptions` | GET | 列出所有订阅 (JSON) |
| `/sub/{token}` | GET | 获取订阅内容 (Clash YAML) |
| `/sub/{token}/base64` | GET | 获取订阅内容 (Base64) |

---

## 文件结构

```
clash-sub-manager/
├── main.py          # 主程序
├── config.yaml      # Clash 配置文件
├── sources.json     # 远程订阅源数据库
├── providers.json   # 规则集配置
├── subs.json        # 订阅数据库
├── pyproject.toml   # Python 项目配置
└── README.md        # 说明文档
```

---

## Systemd 服务配置

```ini
# /etc/systemd/system/clash-sub.service

[Unit]
Description=Clash Subscription Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/clash-sub-manager
ExecStart=/path/to/clash-sub-manager/.venv/bin/python main.py serve --host 127.0.0.1 --port 8080
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

---

## Caddy 反向代理配置

```caddyfile
# Clash 订阅管理器
handle /clash-sub/* {
    uri strip_prefix /clash-sub
    reverse_proxy http://127.0.0.1:8080
}
```

---

## 使用示例

### 配置规则集路由

```bash
# 1. 在 config.yaml 中配置代理组
# 2. 添加规则集，绑定到对应代理组
clash-sub provider-add google Google
clash-sub provider-add youtube Google
clash-sub provider-add telegram Telegram

# 3. 重启服务
systemctl restart clash-sub

# 4. 在 Clash 中更新订阅
```

### 在 Clash 中添加订阅

1. 打开 Clash 客户端
2. 进入「配置」/「Profiles」
3. 添加订阅地址：`https://your-domain/clash-sub/sub/<token>`
4. Clash 会自动识别订阅名称

---

## 注意事项

- 订阅链接仅允许 Clash 客户端访问，浏览器直接访问会返回 403
- 规则集使用 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) 社区规则库
- 规则集更新间隔为 24 小时（Clash 自动更新）
- 原版 Clash 不支持 RULE-SET，建议使用 ClashX Meta 或 Mihomo 版本

---

## GitHub 仓库

https://github.com/deepwzh/clash-sub-manager