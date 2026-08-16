# Proxy Test - 高性能异步代理抓取与目标网站可用性测试工具

从高并发分布式爬虫框架中独立抽离的代理检测与管理系统。专为**快速验证指定目标网站连通性**、**代理池管理**以及 **GitHub Actions 定时自动更新**设计。

---

## 核心特性

- **两阶段漏斗高效验证**：
  - **阶段一 (快速预筛)**：1.0s 超短超时 TCP 端口异步握手，瞬间剔除 90% 僵尸死节点。
  - **阶段二 (协议请求)**：针对 HTTP/HTTPS/SOCKS4/SOCKS5 发起真实 GET 请求，测量响应延迟 (`latency_ms`)，支持网页关键字内容匹配 (`expected_content`)。
- **目标网站可用性隔离 (`valid_targets`)**：解决“代理能上网但在特定爬虫站被阻断 (Cloudflare/403)”的问题，支持针对特定域名精准验证与分发。
- **多源并发异步抓取**：内置 20+ 个高质量免费代理源，自动解析 HTML、JSON、RAW 等多种格式并全局去重。
- **SQLite 增量持久化缓存**：支持 TTL 有效期、评分自适应调度（$score = success - 3 \times fail$）、失败快速熔断与自动补给。
- **开箱即用的 GitHub Actions 持续集成**：自带 `.github/workflows/test_proxies.yml`，定时自动化运行并自动推送最新可用列表到仓库。

---

## 安装依赖

```bash
pip install -r requirements.txt
```

---

## 命令行工具 (CLI) 快速使用

### 1. 批量测试所有爬虫目标网站 (默认模式)
工具内置了 `fuli_crawler` 爬虫系统的全部 11 个目标网站（包括 `seju`, `u3c3`, `datang`, `gcbt`, `madou`, `jingpin_toupai`, `taose`, `dashen`, `tanhua`, `jingpin`, `mianfei_guochan`）：

```bash
# 批量测试所有 11 个爬虫站点，每个站点获取 10 个可用代理并聚合导出
python cli.py -u all -c 10

# 批量测试时强制重新从网络源拉取最新候选代理
python cli.py -u all -f -c 10
```

### 2. 测试指定单个或多个网站
```bash
# 测试单个目标网站 (如 u3c3.com) 并获取 10 个可用代理
python cli.py -u https://u3c3.com/ -c 10 --timeout 5.0

# 批量测试指定的多个网站 (以逗号分隔)
python cli.py -u "https://u3c3.com/,https://seju.life/" -c 5

# 测试百度并要求返回包含指定文字
python cli.py -u https://www.baidu.com --expect "百度一下" -c 5

# 只筛选 SOCKS5 和 HTTPS 协议的代理
python cli.py -u https://u3c3.com/ --protocols socks5,https -c 5
```

### 3. 自定义导出
```bash
# 结果会自动输出到 data/ 目录及 data/sites/ 各站点专属文件，也可指定自定义导出文件
python cli.py -u all -c 10 -o ./my_proxies.json
```

---

## Python API 调用示例

### 1. 便捷函数快速测试
```python
from proxy_test import test_website_proxies, get_working_proxy

# 针对指定网站测试 5 个可用代理
proxies = test_website_proxies(
    target_url="https://u3c3.com/",
    expected_content=None,
    target_count=5,
    timeout=5.0
)

for p in proxies:
    print(f"可用代理: {p['protocol']}://{p['address']} (延迟: {p['latency_ms']}ms)")
```

### 2. 获取单个可用代理并接入网络库
```python
import requests
from proxy_test import get_working_proxy

proxy_url = get_working_proxy(target_url="https://api.myip.com")
print(f"获取代理: {proxy_url}")

# 在 requests 中使用
res = requests.get("https://api.myip.com", proxies={"http": proxy_url, "https": proxy_url}, timeout=5)
print(res.text)
```

---

## 结果保存与 GitHub Actions 自动更新

定时在 GitHub Actions 运行后，测试结果会保存为：
- `data/proxies_latest.json`：包含协议、地址、延迟、评分与已验证站点的完整 JSON。
- `data/proxies.txt`：纯文本列表（`protocol://ip:port`，每行一个）。
- `data/sites/<domain>.txt`：针对特定网站测试通过的专属代理列表。

外部其他项目可直接通过 GitHub Raw 订阅拉取：
```python
import requests
# 从 GitHub 仓库获取最新可用代理
resp = requests.get("https://raw.githubusercontent.com/用户名/仓库名/main/data/proxies.txt")
proxies = [line.strip() for line in resp.text.splitlines() if line.strip()]
```
