#!/usr/bin/env python3
"""
Clash 订阅管理器
- 读取和管理本地 Clash 配置文件
- 支持远程订阅源自动更新
- 提供 HTTP 订阅链接
- 支持节点增删改查
"""

import argparse
import base64
import json
import os
import re
import yaml
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote
import secrets
import string

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, Response

# 配置
DEFAULT_CONFIG = Path(__file__).parent / "config.yaml"
DEFAULT_DB = Path(__file__).parent / "subs.json"
DEFAULT_SOURCES = Path(__file__).parent / "sources.json"


class SubscriptionManager:
    """订阅管理器核心类"""
    
    def __init__(self, config_path: Path = DEFAULT_CONFIG, db_path: Path = DEFAULT_DB, sources_path: Path = DEFAULT_SOURCES):
        self.config_path = config_path
        self.db_path = db_path
        self.sources_path = sources_path
        self.config = {}
        self.subscriptions = {}  # {token: {name, created, filters}}
        self.sources = []  # 远程订阅源列表
        self._load_config()
        self._load_db()
        self._load_sources()
    
    def _load_config(self):
        """加载 Clash 配置文件"""
        if not self.config_path.exists():
            # 创建默认配置
            self.config = {
                'port': 7890,
                'socks-port': 7891,
                'allow-lan': True,
                'mode': 'Rule',
                'log-level': 'info',
                'proxies': [],
                'proxy-groups': [],
                'rules': ['MATCH,Proxies']
            }
            self._save_config()
        else:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}
    
    def _save_config(self):
        """保存配置文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def _load_db(self):
        """加载订阅数据库"""
        if self.db_path.exists():
            with open(self.db_path, 'r', encoding='utf-8') as f:
                self.subscriptions = json.load(f)
    
    def _save_db(self):
        """保存订阅数据库"""
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.subscriptions, f, ensure_ascii=False, indent=2)
    
    def _load_sources(self):
        """加载远程订阅源"""
        if self.sources_path.exists():
            with open(self.sources_path, 'r', encoding='utf-8') as f:
                self.sources = json.load(f)
    
    def _save_sources(self):
        """保存远程订阅源"""
        with open(self.sources_path, 'w', encoding='utf-8') as f:
            json.dump(self.sources, f, ensure_ascii=False, indent=2)
    
    def _generate_token(self, length: int = 16) -> str:
        """生成随机订阅 token"""
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    # === 远程订阅源管理 ===
    
    def add_source(self, name: str, url: str, auto_update: bool = True, interval: int = 3600) -> dict:
        """添加远程订阅源"""
        source = {
            'id': self._generate_token(8),
            'name': name,
            'url': url,
            'auto_update': auto_update,
            'interval': interval,  # 更新间隔（秒）
            'last_update': None,
            'proxy_count': 0
        }
        self.sources.append(source)
        self._save_sources()
        return source
    
    def remove_source(self, source_id: str) -> bool:
        """删除远程订阅源"""
        for i, s in enumerate(self.sources):
            if s['id'] == source_id:
                self.sources.pop(i)
                self._save_sources()
                return True
        return False
    
    def list_sources(self) -> List[dict]:
        """列出所有远程订阅源"""
        return self.sources
    
    async def fetch_source(self, url: str) -> List[dict]:
        """获取远程订阅内容并解析节点"""
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.text
        
        proxies = []
        
        # 尝试解析不同格式
        # 1. 尝试 YAML (Clash 格式)
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and 'proxies' in data:
                proxies = data['proxies']
                return proxies
        except:
            pass
        
        # 2. 尝试 Base64 解码 (V2Ray 订阅格式)
        try:
            # 移除空白字符
            content = content.strip()
            # 添加必要的 padding
            padding = 4 - len(content) % 4
            if padding != 4:
                content += '=' * padding
            
            decoded = base64.b64decode(content).decode('utf-8')
            
            # 解析 vmess:// trojan:// ss:// 等链接
            for line in decoded.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                proxy = self._parse_proxy_url(line)
                if proxy:
                    proxies.append(proxy)
            
            if proxies:
                return proxies
        except:
            pass
        
        # 3. 直接解析 URL 链接
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            proxy = self._parse_proxy_url(line)
            if proxy:
                proxies.append(proxy)
        
        return proxies
    
    def _parse_proxy_url(self, url: str) -> Optional[dict]:
        """解析代理 URL (vmess://, trojan://, ss://, ssr://)"""
        try:
            if url.startswith('vmess://'):
                return self._parse_vmess(url)
            elif url.startswith('trojan://'):
                return self._parse_trojan(url)
            elif url.startswith('ss://'):
                return self._parse_ss(url)
            elif url.startswith('ssr://'):
                return self._parse_ssr(url)
        except Exception as e:
            pass
        return None
    
    def _parse_vmess(self, url: str) -> Optional[dict]:
        """解析 vmess:// 链接"""
        # vmess://base64_json
        import json
        
        b64 = url[8:]  # 去掉 vmess://
        # 添加 padding
        padding = 4 - len(b64) % 4
        if padding != 4:
            b64 += '=' * padding
        
        try:
            data = json.loads(base64.b64decode(b64).decode('utf-8'))
        except:
            return None
        
        proxy = {
            'name': data.get('ps', data.get('add', 'vmess')),
            'type': 'vmess',
            'server': data.get('add'),
            'port': int(data.get('port', 443)),
            'uuid': data.get('id'),
            'alterId': int(data.get('aid', 0)),
            'cipher': data.get('scy', 'auto'),
            'udp': True
        }
        
        net = data.get('net', 'tcp')
        if net == 'ws':
            proxy['network'] = 'ws'
            proxy['ws-opts'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host', proxy['server'])}
            }
        elif net == 'grpc':
            proxy['network'] = 'grpc'
            proxy['grpc-opts'] = {'grpc-service-name': data.get('path', '')}
        
        tls = data.get('tls', '')
        if tls == 'tls':
            proxy['tls'] = True
            if data.get('sni'):
                proxy['servername'] = data['sni']
        
        return proxy
    
    def _parse_trojan(self, url: str) -> Optional[dict]:
        """解析 trojan:// 链接"""
        # trojan://password@server:port?sni=xxx#name
        parsed = urlparse(url)
        
        proxy = {
            'name': parsed.fragment or parsed.hostname or 'trojan',
            'type': 'trojan',
            'server': parsed.hostname,
            'port': parsed.port or 443,
            'password': parsed.username,
            'udp': True,
            'tls': True
        }
        
        # 解析查询参数
        query = parse_qs(parsed.query)
        if 'sni' in query:
            proxy['sni'] = query['sni'][0]
        if 'type' in query and query['type'][0] == 'ws':
            proxy['network'] = 'ws'
            proxy['ws-opts'] = {'path': query.get('path', ['/'])[0]}
        
        return proxy
    
    def _parse_ss(self, url: str) -> Optional[dict]:
        """解析 ss:// 链接 (Shadowsocks)"""
        # ss://base64@server:port#name 或 ss://base64#name
        parsed = urlparse(url)
        
        name = parsed.fragment or 'ss'
        
        if '@' in url:
            # ss://method:password@server:port#name
            match = re.match(r'ss://([^@]+)@([^:]+):(\d+)', url)
            if match:
                method, password, server, port = match.groups()
            else:
                return None
        else:
            # ss://base64#name
            b64 = url[5:].split('#')[0]
            padding = 4 - len(b64) % 4
            if padding != 4:
                b64 += '=' * padding
            decoded = base64.b64decode(b64).decode('utf-8')
            match = re.match(r'([^:]+):([^@]+)@([^:]+):(\d+)', decoded)
            if match:
                method, password, server, port = match.groups()
            else:
                return None
        
        return {
            'name': name,
            'type': 'ss',
            'server': server,
            'port': int(port),
            'cipher': method,
            'password': password,
            'udp': True
        }
    
    def _parse_ssr(self, url: str) -> Optional[dict]:
        """解析 ssr:// 链接 (ShadowsocksR) - 简化版，转为 ss"""
        # SSR 格式复杂，这里简化处理
        b64 = url[6:]  # 去掉 ssr://
        padding = 4 - len(b64) % 4
        if padding != 4:
            b64 += '=' * padding
        
        try:
            decoded = base64.b64decode(b64).decode('utf-8')
            # server:port:protocol:method:obfs:password_base64/?params
            parts = decoded.split('/?')
            main_parts = parts[0].split(':')
            
            return {
                'name': 'ssr_' + main_parts[0],
                'type': 'ss',  # 简化为 ss
                'server': main_parts[0],
                'port': int(main_parts[1]),
                'cipher': main_parts[3],
                'password': base64.b64decode(main_parts[5] + '==').decode('utf-8'),
                'udp': True
            }
        except:
            return None
    
    async def update_source(self, source_id: str = None) -> dict:
        """更新远程订阅源"""
        results = {'updated': 0, 'failed': 0, 'total': 0}
        
        sources_to_update = self.sources
        if source_id:
            sources_to_update = [s for s in self.sources if s['id'] == source_id]
        
        for source in sources_to_update:
            results['total'] += 1
            try:
                proxies = await self.fetch_source(source['url'])
                
                # 移除该源的旧节点（根据名称前缀或标记）
                prefix = f"[{source['name']}]"
                self.config['proxies'] = [
                    p for p in self.config.get('proxies', [])
                    if not p.get('name', '').startswith(prefix)
                ]
                
                # 添加新节点（带前缀）
                for p in proxies:
                    p['name'] = f"{prefix} {p.get('name', 'node')}"
                    p['_source'] = source['id']
                
                self.config['proxies'].extend(proxies)
                
                source['last_update'] = datetime.now().isoformat()
                source['proxy_count'] = len(proxies)
                results['updated'] += 1
                
            except Exception as e:
                print(f"  ✗ 更新失败 [{source['name']}]: {e}")
                results['failed'] += 1
        
        self._save_config()
        self._save_sources()
        return results
    
    # === 节点管理 ===
    
    def list_proxies(self) -> list:
        """列出所有代理节点"""
        return self.config.get('proxies', [])
    
    def get_proxy(self, name: str) -> Optional[dict]:
        """获取指定节点"""
        for proxy in self.config.get('proxies', []):
            if proxy.get('name') == name:
                return proxy
        return None
    
    def add_proxy(self, proxy: dict) -> bool:
        """添加节点"""
        if not proxy.get('name'):
            raise ValueError("节点必须有 name 字段")
        
        if self.get_proxy(proxy['name']):
            raise ValueError(f"节点已存在: {proxy['name']}")
        
        if 'proxies' not in self.config:
            self.config['proxies'] = []
        
        self.config['proxies'].append(proxy)
        self._save_config()
        return True
    
    def update_proxy(self, name: str, updates: dict) -> bool:
        """更新节点"""
        for i, proxy in enumerate(self.config.get('proxies', [])):
            if proxy.get('name') == name:
                if 'name' in updates and updates['name'] != name:
                    raise ValueError("不允许修改节点名称，请删除后重新添加")
                
                self.config['proxies'][i].update(updates)
                self._save_config()
                return True
        return False
    
    def delete_proxy(self, name: str) -> bool:
        """删除节点"""
        proxies = self.config.get('proxies', [])
        for i, proxy in enumerate(proxies):
            if proxy.get('name') == name:
                proxies.pop(i)
                self.config['proxies'] = proxies
                self._save_config()
                return True
        return False
    
    def clear_proxies(self, source_id: str = None) -> int:
        """清空节点"""
        if source_id:
            # 清空指定源的节点
            before = len(self.config.get('proxies', []))
            self.config['proxies'] = [
                p for p in self.config.get('proxies', [])
                if p.get('_source') != source_id
            ]
            self._save_config()
            return before - len(self.config['proxies'])
        else:
            # 清空所有
            count = len(self.config.get('proxies', []))
            self.config['proxies'] = []
            self._save_config()
            return count
    
    # === 订阅管理 ===
    
    def create_subscription(self, name: str, filters: dict = None) -> dict:
        """创建订阅"""
        token = self._generate_token()
        self.subscriptions[token] = {
            'name': name,
            'created': datetime.now().isoformat(),
            'filters': filters or {},
            'access_count': 0
        }
        self._save_db()
        return {'token': token, 'name': name}
    
    def list_subscriptions(self) -> dict:
        """列出所有订阅"""
        return self.subscriptions
    
    def delete_subscription(self, token: str) -> bool:
        """删除订阅"""
        if token in self.subscriptions:
            del self.subscriptions[token]
            self._save_db()
            return True
        return False
    
    def get_subscription_url(self, token: str, base_url: str) -> Optional[str]:
        """获取订阅 URL"""
        if token not in self.subscriptions:
            return None
        return f"{base_url}/sub/{token}"
    
    # === 订阅输出 ===
    
    def generate_subscription(self, token: str, format: str = 'yaml') -> Optional[str]:
        """生成订阅内容"""
        if token not in self.subscriptions:
            return None
        
        sub = self.subscriptions[token]
        sub['access_count'] = sub.get('access_count', 0) + 1
        sub['last_access'] = datetime.now().isoformat()
        self._save_db()
        
        # 过滤节点
        filters = sub.get('filters', {})
        proxies = self.config.get('proxies', [])
        
        if filters.get('names'):
            proxies = [p for p in proxies if p.get('name') in filters['names']]
        elif filters.get('keywords'):
            keywords = filters['keywords']
            proxies = [p for p in proxies if any(kw in p.get('name', '') for kw in keywords)]
        elif filters.get('sources'):
            # 按订阅源过滤
            proxies = [p for p in proxies if p.get('_source') in filters['sources']]
        
        # 构建输出配置
        output = {
            'port': self.config.get('port', 7890),
            'socks-port': self.config.get('socks-port', 7891),
            'allow-lan': self.config.get('allow-lan', True),
            'mode': self.config.get('mode', 'Rule'),
            'log-level': self.config.get('log-level', 'info'),
        }
        
        if 'dns' in self.config:
            output['dns'] = self.config['dns']
        
        output['proxies'] = proxies
        
        # 动态生成 proxy-groups
        proxy_names = [p['name'] for p in proxies]
        output['proxy-groups'] = [
            {
                'name': 'Proxies',
                'type': 'select',
                'proxies': ['自动选择', '手动选择'] + proxy_names
            },
            {
                'name': '自动选择',
                'type': 'url-test',
                'url': 'http://www.gstatic.com/generate_204',
                'interval': 300,
                'tolerance': 50,
                'proxies': proxy_names
            },
            {
                'name': '手动选择',
                'type': 'select',
                'proxies': proxy_names
            }
        ]
        
        output['rules'] = self.config.get('rules', ['MATCH,Proxies'])
        
        if format == 'base64':
            # Base64 编码的节点链接
            lines = []
            for p in proxies:
                url = self._proxy_to_url(p)
                if url:
                    lines.append(url)
            return base64.b64encode('\n'.join(lines).encode()).decode()
        else:
            return yaml.dump(output, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def _proxy_to_url(self, proxy: dict) -> Optional[str]:
        """将节点转换为 URL 格式"""
        ptype = proxy.get('type')
        
        if ptype == 'vmess':
            import json
            data = {
                'v': '2',
                'ps': proxy.get('name', 'vmess'),
                'add': proxy.get('server'),
                'port': str(proxy.get('port', 443)),
                'id': proxy.get('uuid'),
                'aid': str(proxy.get('alterId', 0)),
                'scy': proxy.get('cipher', 'auto'),
                'net': proxy.get('network', 'tcp'),
                'tls': 'tls' if proxy.get('tls') else '',
            }
            b64 = base64.b64encode(json.dumps(data).encode()).decode()
            return f"vmess://{b64}"
        
        elif ptype == 'trojan':
            name = proxy.get('name', 'trojan')
            server = proxy.get('server')
            port = proxy.get('port', 443)
            password = proxy.get('password')
            sni = proxy.get('sni', server)
            return f"trojan://{password}@{server}:{port}?sni={sni}#{name}"
        
        elif ptype == 'ss':
            name = proxy.get('name', 'ss')
            method = proxy.get('cipher')
            password = proxy.get('password')
            server = proxy.get('server')
            port = proxy.get('port', 8388)
            b64 = base64.b64encode(f"{method}:{password}".encode()).decode()
            return f"ss://{b64}@{server}:{port}#{name}"
        
        return None


# === CLI 命令 ===

def cli_list_proxies(args):
    """列出所有节点"""
    mgr = SubscriptionManager()
    proxies = mgr.list_proxies()
    
    if not proxies:
        print("暂无节点")
        return
    
    print(f"\n共有 {len(proxies)} 个节点:\n")
    
    # 按来源分组
    by_source = {}
    for p in proxies:
        source = p.get('_source', 'local')
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(p)
    
    for source, procs in by_source.items():
        source_name = source
        for s in mgr.sources:
            if s['id'] == source:
                source_name = s['name']
                break
        print(f"  [{source_name}]")
        for p in procs:
            print(f"    • {p.get('name', 'unnamed')} ({p.get('type', 'unknown')})")
        print()


def cli_add_proxy(args):
    """添加节点"""
    mgr = SubscriptionManager()
    
    proxy = {'name': args.name}
    
    if args.type == 'trojan':
        proxy.update({
            'type': 'trojan',
            'server': args.server,
            'port': args.port,
            'password': args.password,
            'udp': True,
            'tls': True
        })
        if args.network:
            proxy['network'] = args.network
        if args.grpc_service:
            proxy['grpc-opts'] = {'grpc-service-name': args.grpc_service}
    elif args.type == 'vmess':
        proxy.update({
            'type': 'vmess',
            'server': args.server,
            'port': args.port,
            'uuid': args.uuid,
            'alterId': args.alter_id or 0,
            'cipher': args.cipher or 'auto',
            'udp': True
        })
    
    try:
        mgr.add_proxy(proxy)
        print(f"✓ 节点添加成功: {args.name}")
    except Exception as e:
        print(f"✗ 添加失败: {e}")


def cli_delete_proxy(args):
    """删除节点"""
    mgr = SubscriptionManager()
    
    if mgr.delete_proxy(args.name):
        print(f"✓ 节点已删除: {args.name}")
    else:
        print(f"✗ 节点不存在: {args.name}")


def cli_clear_proxies(args):
    """清空节点"""
    mgr = SubscriptionManager()
    
    count = mgr.clear_proxies(args.source)
    print(f"✓ 已清空 {count} 个节点")


# === 远程订阅源命令 ===

def cli_source_list(args):
    """列出远程订阅源"""
    import asyncio
    
    mgr = SubscriptionManager()
    sources = mgr.list_sources()
    
    if not sources:
        print("暂无远程订阅源")
        print("\n使用 'source-add' 命令添加订阅源")
        return
    
    print(f"\n共有 {len(sources)} 个订阅源:\n")
    for s in sources:
        status = "✓" if s.get('last_update') else "○"
        print(f"  {status} {s['name']} ({s['id']})")
        print(f"      URL: {s['url']}")
        print(f"      节点数: {s.get('proxy_count', 0)}")
        print(f"      上次更新: {s.get('last_update', '从未更新')}")
        print()


def cli_source_add(args):
    """添加远程订阅源"""
    mgr = SubscriptionManager()
    
    source = mgr.add_source(args.name, args.url, auto_update=not args.no_auto, interval=args.interval)
    print(f"\n✓ 订阅源添加成功!")
    print(f"  名称: {source['name']}")
    print(f"  ID: {source['id']}")
    print(f"  URL: {source['url']}")
    print(f"\n使用 'source-update {source['id']}' 立即更新")


def cli_source_remove(args):
    """删除远程订阅源"""
    mgr = SubscriptionManager()
    
    if mgr.remove_source(args.id):
        print(f"✓ 订阅源已删除: {args.id}")
    else:
        print(f"✗ 订阅源不存在: {args.id}")


def cli_source_update(args):
    """更新远程订阅源"""
    import asyncio
    
    mgr = SubscriptionManager()
    
    print("\n正在更新订阅源...")
    results = asyncio.run(mgr.update_source(args.id))
    
    print(f"\n✓ 更新完成:")
    print(f"  成功: {results['updated']}")
    print(f"  失败: {results['failed']}")
    print(f"  总计: {results['total']}")


# === 订阅命令 ===

def cli_create_sub(args):
    """创建订阅"""
    mgr = SubscriptionManager()
    
    filters = {}
    if args.nodes:
        filters['names'] = args.nodes.split(',')
    elif args.keywords:
        filters['keywords'] = args.keywords.split(',')
    elif args.sources:
        filters['sources'] = args.sources.split(',')
    
    result = mgr.create_subscription(args.name, filters)
    print(f"\n✓ 订阅创建成功!")
    print(f"  名称: {result['name']}")
    print(f"  Token: {result['token']}")
    print(f"\n订阅地址: {args.base_url}/sub/{result['token']}")


def cli_list_subs(args):
    """列出所有订阅"""
    mgr = SubscriptionManager()
    subs = mgr.list_subscriptions()
    
    if not subs:
        print("暂无订阅")
        return
    
    print(f"\n共有 {len(subs)} 个订阅:\n")
    for token, info in subs.items():
        print(f"  • {info['name']}")
        print(f"    Token: {token}")
        print(f"    创建时间: {info.get('created', 'unknown')}")
        print(f"    访问次数: {info.get('access_count', 0)}")
        if info.get('filters'):
            print(f"    过滤器: {info['filters']}")
        print()


def cli_delete_sub(args):
    """删除订阅"""
    mgr = SubscriptionManager()
    
    if mgr.delete_subscription(args.token):
        print(f"✓ 订阅已删除: {args.token}")
    else:
        print(f"✗ 订阅不存在: {args.token}")


def cli_serve(args):
    """启动 HTTP 服务"""
    import asyncio
    
    mgr = SubscriptionManager()
    app = FastAPI(title="Clash Subscription Manager")
    
    @app.get("/", response_class=HTMLResponse)
    async def index():
        return f"""
        <html>
        <head><title>Clash 订阅管理器</title></head>
        <body>
            <h1>Clash 订阅管理器</h1>
            <p>节点数: {len(mgr.list_proxies())}</p>
            <p>订阅源数: {len(mgr.sources)}</p>
            <p>订阅数: {len(mgr.subscriptions)}</p>
            <h2>API 端点</h2>
            <ul>
                <li>GET /proxies - 列出所有节点</li>
                <li>GET /sources - 列出所有订阅源</li>
                <li>GET /sources/update - 更新所有订阅源</li>
                <li>GET /subscriptions - 列出所有订阅</li>
                <li>GET /sub/{{token}} - 获取订阅内容 (YAML)</li>
                <li>GET /sub/{{token}}/base64 - 获取订阅内容 (Base64)</li>
            </ul>
        </body>
        </html>
        """
    
    @app.get("/proxies")
    async def list_proxies():
        return mgr.list_proxies()
    
    @app.get("/sources")
    async def list_sources():
        return mgr.sources
    
    @app.get("/sources/update")
    async def update_sources():
        results = await mgr.update_source()
        return results
    
    @app.get("/subscriptions")
    async def list_subscriptions():
        return mgr.subscriptions
    
    @app.get("/sub/{token}")
    async def get_subscription(request: Request, token: str):
        # 检查 User-Agent，只允许 Clash 客户端访问
        ua = request.headers.get('user-agent', '')
        
        # 允许的客户端：Clash, ClashMeta, ClashX, Stash, Shadowrocket 等
        allowed_clients = ['Clash', 'clash', 'Stash', 'stash', 'Shadowrocket']
        
        # 如果不是允许的客户端，返回提示信息
        if not any(client in ua for client in allowed_clients):
            raise HTTPException(
                status_code=403, 
                detail="此订阅仅限 Clash 客户端访问。请在 Clash 中添加此订阅链接。"
            )
        
        content = mgr.generate_subscription(token, format='yaml')
        if content is None:
            raise HTTPException(status_code=404, detail="订阅不存在")
        
        # 获取订阅名称，用于文件名
        sub_info = mgr.subscriptions.get(token, {})
        sub_name = sub_info.get('name', 'clash-sub')
        
        # 文件名编码：ASCII 部分用于 filename，UTF-8 编码用于 filename*
        # RFC 5987 格式
        safe_name_ascii = re.sub(r'[^a-zA-Z0-9_\-]', '_', sub_name)
        safe_name_utf8 = quote(sub_name)
        
        # 设置 Content-Disposition，Clash 会用这个作为配置名称
        # 同时提供 ASCII 和 UTF-8 编码的文件名
        headers = {
            'Content-Disposition': f"attachment; filename=\"{safe_name_ascii}.yaml\"; filename*=UTF-8''{safe_name_utf8}.yaml",
            'profile-update-interval': '24'  # 建议更新间隔（小时）
        }
        
        return Response(
            content=content,
            media_type='text/yaml; charset=utf-8',
            headers=headers
        )
    
    @app.get("/sub/{token}/base64")
    async def get_subscription_base64(request: Request, token: str):
        # 同样检查 User-Agent
        ua = request.headers.get('user-agent', '')
        allowed_clients = ['Clash', 'clash', 'Stash', 'stash', 'Shadowrocket', 'v2ray', 'V2Ray']
        
        if not any(client in ua for client in allowed_clients):
            raise HTTPException(
                status_code=403, 
                detail="此订阅仅限 Clash/V2Ray 客户端访问。"
            )
        
        content = mgr.generate_subscription(token, format='base64')
        if content is None:
            raise HTTPException(status_code=404, detail="订阅不存在")
        
        sub_info = mgr.subscriptions.get(token, {})
        sub_name = sub_info.get('name', 'clash-sub')
        
        safe_name_ascii = re.sub(r'[^a-zA-Z0-9_\-]', '_', sub_name)
        safe_name_utf8 = quote(sub_name)
        
        headers = {
            'Content-Disposition': f"attachment; filename=\"{safe_name_ascii}.txt\"; filename*=UTF-8''{safe_name_utf8}.txt",
            'profile-update-interval': '24'
        }
        
        return Response(
            content=content,
            media_type='text/plain; charset=utf-8',
            headers=headers
        )
    
    print(f"\n🚀 服务启动中...")
    print(f"   地址: http://{args.host}:{args.port}")
    print(f"   配置: {mgr.config_path}")
    print()
    
    uvicorn.run(app, host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(description="Clash 订阅管理器", formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # === 节点管理 ===
    
    p_list = subparsers.add_parser('list', help='列出所有节点')
    p_list.set_defaults(func=cli_list_proxies)
    
    p_add = subparsers.add_parser('add', help='添加节点')
    p_add.add_argument('name', help='节点名称')
    p_add.add_argument('--type', required=True, choices=['trojan', 'vmess', 'ss'], help='节点类型')
    p_add.add_argument('--server', required=True, help='服务器地址')
    p_add.add_argument('--port', type=int, required=True, help='端口')
    p_add.add_argument('--password', help='密码 (trojan/ss)')
    p_add.add_argument('--uuid', help='UUID (vmess)')
    p_add.add_argument('--network', help='传输协议')
    p_add.add_argument('--grpc-service', help='gRPC 服务名')
    p_add.add_argument('--alter-id', type=int, default=0, help='alterId (vmess)')
    p_add.add_argument('--cipher', default='auto', help='加密方式')
    p_add.set_defaults(func=cli_add_proxy)
    
    p_del = subparsers.add_parser('delete', help='删除节点')
    p_del.add_argument('name', help='节点名称')
    p_del.set_defaults(func=cli_delete_proxy)
    
    p_clear = subparsers.add_parser('clear', help='清空节点')
    p_clear.add_argument('--source', help='指定订阅源 ID')
    p_clear.set_defaults(func=cli_clear_proxies)
    
    # === 远程订阅源 ===
    
    p_src = subparsers.add_parser('source', help='订阅源管理').add_subparsers(dest='source_cmd')
    
    p_src_list = subparsers.add_parser('source-list', help='列出所有订阅源')
    p_src_list.set_defaults(func=cli_source_list)
    
    p_src_add = subparsers.add_parser('source-add', help='添加订阅源')
    p_src_add.add_argument('name', help='订阅源名称')
    p_src_add.add_argument('url', help='订阅 URL')
    p_src_add.add_argument('--no-auto', action='store_true', help='禁用自动更新')
    p_src_add.add_argument('--interval', type=int, default=3600, help='更新间隔(秒)')
    p_src_add.set_defaults(func=cli_source_add)
    
    p_src_remove = subparsers.add_parser('source-remove', help='删除订阅源')
    p_src_remove.add_argument('id', help='订阅源 ID')
    p_src_remove.set_defaults(func=cli_source_remove)
    
    p_src_update = subparsers.add_parser('source-update', help='更新订阅源')
    p_src_update.add_argument('id', nargs='?', help='订阅源 ID (不指定则更新全部)')
    p_src_update.set_defaults(func=cli_source_update)
    
    # === 订阅管理 ===
    
    p_sub = subparsers.add_parser('sub-create', help='创建订阅')
    p_sub.add_argument('name', help='订阅名称')
    p_sub.add_argument('--nodes', help='指定节点 (逗号分隔)')
    p_sub.add_argument('--keywords', help='关键词过滤 (逗号分隔)')
    p_sub.add_argument('--sources', help='订阅源 ID 过滤 (逗号分隔)')
    p_sub.add_argument('--base-url', default='http://localhost:8080', help='服务基础 URL')
    p_sub.set_defaults(func=cli_create_sub)
    
    p_subs = subparsers.add_parser('sub-list', help='列出所有订阅')
    p_subs.set_defaults(func=cli_list_subs)
    
    p_sub_del = subparsers.add_parser('sub-delete', help='删除订阅')
    p_sub_del.add_argument('token', help='订阅 Token')
    p_sub_del.set_defaults(func=cli_delete_sub)
    
    # === 服务 ===
    
    p_serve = subparsers.add_parser('serve', help='启动 HTTP 服务')
    p_serve.add_argument('--host', default='0.0.0.0', help='监听地址')
    p_serve.add_argument('--port', type=int, default=8080, help='端口')
    p_serve.set_defaults(func=cli_serve)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    args.func(args)


if __name__ == '__main__':
    main()