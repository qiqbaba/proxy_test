"""
使用示例与集成示范
演示如何通过 Python 代码直接调用 proxy_test 并在 requests / httpx 中使用
"""
from proxy_test import test_website_proxies, get_working_proxy, get_global_pool

def demo_test_website():
    print("=" * 60)
    print("示例 1: 一行代码测试指定网站的可用代理")
    print("=" * 60)
    
    target_site = "https://api.myip.com"
    proxies = test_website_proxies(
        target_url=target_site,
        target_count=3,
        timeout=4.0
    )
    
    for p in proxies:
        print(f"-> 协议: {p['protocol']:<6} | 地址: {p['address']:<21} | 延迟: {p.get('latency_ms', 0):.1f}ms")


def demo_get_working_proxy():
    print("\n" + "=" * 60)
    print("示例 2: 获取单个代理并在 requests 中实际发请求")
    print("=" * 60)

    proxy_url = get_working_proxy(target_url="https://api.myip.com")
    print(f"获取到的可用代理: {proxy_url}")

    if proxy_url:
        try:
            import urllib.request
            proxy_handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url
            })
            opener = urllib.request.build_opener(proxy_handler)
            req = urllib.request.Request("https://api.myip.com", headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=5) as response:
                content = response.read().decode("utf-8")
                print(f"使用代理请求成功! 返回内容: {content.strip()}")
        except Exception as e:
            print(f"代理请求测试: {e}")


def demo_pool_scoring():
    print("\n" + "=" * 60)
    print("示例 3: 动态反馈评分与失败熔断机制")
    print("=" * 60)

    pool = get_global_pool()
    proxy = pool.get_working_proxy()
    if proxy:
        print(f"汇报成功并加分: {proxy}")
        pool.report_success(proxy)


if __name__ == "__main__":
    demo_test_website()
    demo_get_working_proxy()
    demo_pool_scoring()
