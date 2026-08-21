"""
代理抓取模块
负责从多个网络免费源高并发异步拉取原始代理 IP 列表并去重解析
支持通过本地代理/镜像抓取源（针对国内本地环境）或在 GitHub Actions 中直连抓取
"""
import os
import re
import asyncio
import aiohttp
from typing import List, Dict, Optional
from proxy_test.config import PROXY_SOURCES
from proxy_test.logger import get_logger

logger = get_logger("proxy_test.fetcher")


class ProxyFetcher:
    """代理抓取器"""

    def __init__(self, sources: Optional[Dict[str, str]] = None, fetch_proxy: Optional[str] = None):
        self.sources = sources or PROXY_SOURCES
        self.fetch_proxy = fetch_proxy or os.environ.get("FETCH_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    def fetch_all(self) -> List[Dict[str, str]]:
        """同步阻塞式获取所有代理（内部通过 asyncio 异步运行）"""
        try:
            loop = asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if in_loop:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(self.fetch_all_async())).result()
        else:
            return asyncio.run(self.fetch_all_async())

    async def fetch_all_async(self) -> List[Dict[str, str]]:
        """完全异步并发从所有配置的代理源获取代理列表并去重"""
        logger.info("开始从 %s 个免费代理源并发获取原始代理列表...", len(self.sources))
        all_proxies = {}
        timeout = aiohttp.ClientTimeout(total=45)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                self._fetch_from_source(session, name, url)
                for name, url in self.sources.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (source_name, _), result in zip(self.sources.items(), results):
                if isinstance(result, Exception):
                    logger.warning("  [%s] 抓取失败: %s", source_name, result)
                elif isinstance(result, list):
                    for proxy in result:
                        key = f"{proxy['protocol']}://{proxy['address']}"
                        if key not in all_proxies:
                            all_proxies[key] = proxy
                    logger.info("  [%s] 成功获取 %s 个代理", source_name, len(result))

        unique_list = list(all_proxies.values())
        logger.info("抓取完毕: 去重后共获得 %s 个候选代理", len(unique_list))
        return unique_list

    async def _fetch_from_source(self, session: aiohttp.ClientSession, source_name: str, url: str) -> List[Dict[str, str]]:
        """从单个源异步获取并解析代理"""
        proxies = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            }
            req_timeout = aiohttp.ClientTimeout(total=25)
            async with session.get(url, headers=headers, proxy=self.fetch_proxy, timeout=req_timeout, ssl=False) as resp:
                if resp.status != 200:
                    return []
                raw_bytes = await resp.read()
                text = raw_bytes.decode("utf-8", errors="ignore")

            # 快代理: 解析嵌入 <script> 的 fpsList JSON ({"ip": "...", "port": "..."})
            if source_name.startswith("kuaidaili_"):
                pairs = re.findall(
                    r'"ip"\s*:\s*"(\d{1,3}(?:\.\d{1,3}){3})"[^}]*?"port"\s*:\s*"(\d{1,5})"',
                    text,
                )
                for ip, port in pairs:
                    p = int(port)
                    if 1 <= p <= 65535:
                        proxies.append({
                            "protocol": "http",
                            "address": f"{ip}:{p}",
                            "source": source_name,
                        })
                return proxies

            # ProxyList+: HTML 表格 <td>IP</td><td>Port</td> 相邻单元格
            if source_name.startswith("proxylistplus_"):
                pairs = re.findall(
                    r"<td[^>]*>\s*(\d{1,3}(?:\.\d{1,3}){3})\s*</td>\s*<td[^>]*>\s*(\d{1,5})\s*</td>",
                    text,
                    re.IGNORECASE,
                )
                for ip, port in pairs:
                    p = int(port)
                    if 1 <= p <= 65535:
                        proxies.append({
                            "protocol": "http",
                            "address": f"{ip}:{p}",
                            "source": source_name,
                        })
                return proxies

            # 89ip / free_proxy_list / sslproxies_org: 全文检索 ip:port 模式
            if source_name in ("free_proxy_list", "sslproxies_org", "89ip"):
                matches = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3}:\d{1,5})", text)
                for address in matches:
                    protocol = "https" if "ssl" in source_name else "http"
                    proxies.append({
                        "protocol": protocol,
                        "address": address,
                        "source": source_name,
                    })
                return proxies

            # 根据源名称猜测默认协议
            src_lower = source_name.lower()
            if "socks5" in src_lower:
                default_proto = "socks5"
            elif "socks4" in src_lower:
                default_proto = "socks4"
            elif "https" in src_lower:
                default_proto = "https"
            else:
                default_proto = "http"

            for line in text.strip().splitlines():
                line = line.strip()
                if not line or line.startswith(('#', '//', ';')):
                    continue

                line_proto = default_proto
                if "://" in line:
                    parts = line.split("://", 1)
                    if len(parts) == 2:
                        line_proto = parts[0].strip().lower()
                        line = parts[1].strip()

                match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})", line)
                if match:
                    ip = match.group(1)
                    port = int(match.group(2))
                    if 1 <= port <= 65535:
                        proxies.append({
                            "protocol": line_proto,
                            "address": f"{ip}:{port}",
                            "source": source_name
                        })
        except Exception as e:
            logger.debug("解析源 %s 失败: %s", source_name, e)

        return proxies
