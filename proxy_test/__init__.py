"""
proxy_test - 高性能异步代理抓取、测试与代理池工具包
"""
from typing import List, Dict, Optional, Any
from proxy_test.fetcher import ProxyFetcher
from proxy_test.verifier import ProxyVerifier
from proxy_test.pool import ProxyPool
from proxy_test.exporter import ProxyExporter
from proxy_test.logger import get_logger

__version__ = "1.0.0"

_global_pool: Optional[ProxyPool] = None


def get_global_pool(fetch_proxy: Optional[str] = None) -> ProxyPool:
    """获取单例全局代理池实例"""
    global _global_pool
    if _global_pool is None:
        _global_pool = ProxyPool(fetch_proxy=fetch_proxy)
    elif fetch_proxy:
        _global_pool.fetcher.fetch_proxy = fetch_proxy
    return _global_pool


def test_website_proxies(
    target_url: str,
    expected_content: Optional[str] = None,
    target_count: int = 1000,
    timeout: float = 5.0,
    max_workers: Optional[int] = None,
    force_fetch: bool = False,
    protocols: Optional[List[str]] = None,
    auto_export: bool = True,
    export_path: Optional[str] = None,
    fetch_proxy: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    便捷测试接口：针对指定目标网站快速抓取、并发测试并返回可用代理列表
    
    Args:
        target_url: 目标测试网址 (例如: "https://u3c3.com/" 或 "https://api.myip.com")
        expected_content: 页面中期望包含的文本（可选，用于严格防封检测）
        target_count: 期望获取的可用代理数量（达到后立即停止，提速）
        timeout: 验证超时时间（秒，默认 5.0）
        max_workers: 并发工作协程数（默认根据硬件自动调配）
        force_fetch: 是否强制重新从网络源抓取（默认先利用缓存）
        protocols: 协议过滤列表 (例如: ['socks5', 'https'])
        auto_export: 是否自动导出到 data/ 目录 (默认 True)
        export_path: 自定义导出文件路径 (可选)
        fetch_proxy: 抓取免费代理源时使用的临时代理 (可选，如国内本地运行时)
        
    Returns:
        可用代理字典列表，包含 protocol, address, latency_ms, score 等
    """
    pool = get_global_pool(fetch_proxy=fetch_proxy)
    working = pool.verify_proxies_for_target(
        target_url=target_url,
        expected_content=expected_content,
        target_count=target_count,
        timeout=timeout,
        max_workers=max_workers,
        force_fetch=force_fetch,
        protocols=protocols,
        fetch_proxy=fetch_proxy
    )

    if auto_export and working:
        exporter = ProxyExporter()
        exporter.export(working, target_url=target_url, custom_export_path=export_path)

    return working


def get_working_proxy(
    target_url: Optional[str] = None,
    expected_content: Optional[str] = None,
    timeout: float = 5.0,
    exclusive: bool = False,
    fetch_proxy: Optional[str] = None
) -> Optional[str]:
    """
    获取单个可直接使用的代理 URL 字符串
    
    Returns:
        "socks5://1.2.3.4:1080" 或 "http://5.6.7.8:8080" 或 None
    """
    pool = get_global_pool(fetch_proxy=fetch_proxy)
    proxy = pool.get_working_proxy(target_url=target_url, exclusive=exclusive)
    if not proxy:
        pool.verify_proxies_for_target(
            target_url=target_url or "https://api.myip.com",
            expected_content=expected_content,
            target_count=5,
            timeout=timeout,
            fetch_proxy=fetch_proxy
        )
        proxy = pool.get_working_proxy(target_url=target_url, exclusive=exclusive)
    return proxy


class ProxyTester:
    """代理测试与调度类"""
    def __init__(self, pool: Optional[ProxyPool] = None):
        self.pool = pool or get_global_pool()
        self.exporter = ProxyExporter()

    def test(self, target_url: str, **kwargs) -> List[Dict[str, Any]]:
        return test_website_proxies(target_url=target_url, **kwargs)

    def export(self, proxies: List[Dict[str, Any]], target_url: Optional[str] = None):
        return self.exporter.export(proxies, target_url=target_url)


__all__ = [
    "test_website_proxies",
    "get_working_proxy",
    "ProxyTester",
    "ProxyPool",
    "ProxyFetcher",
    "ProxyVerifier",
    "ProxyExporter",
    "get_global_pool",
]
