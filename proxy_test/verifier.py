"""
代理验证模块
采用高并发异步协程实现：
1. 快速 TCP 端口握手（预筛过滤死节点）
2. 真实网络请求与协议握手（HTTP / HTTPS / SOCKS4 / SOCKS5，支持远程 DNS 与本地 DNS 缓存）
3. 响应耗时 (latency_ms) 测定与 HTML 关键字 (expected_content) 比对
4. 目标数量达成提前退出 (target_count) 与打散扫描特征的随机微延迟
"""
import time
import random
import asyncio
import aiohttp
from typing import List, Dict, Optional, Callable
from aiohttp_socks import ProxyConnector
from proxy_test.config import DEFAULT_VERIFY_TIMEOUT, DEFAULT_VERIFY_SSL, get_auto_workers
from proxy_test.logger import get_logger

logger = get_logger("proxy_test.verifier")


async def check_tcp_port(ip: str, port: int, timeout: float = 1.0) -> bool:
    """阶段一：超短超时快速进行 TCP 端口握手，剔除不通的主机"""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout
        )
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


class ProxyVerifier:
    """代理验证器"""

    def __init__(self, default_test_url: str = "https://api.myip.com"):
        self.default_test_url = default_test_url

    def verify_proxies(
        self,
        proxies: List[Dict[str, any]],
        target_url: Optional[str] = None,
        expected_content: Optional[str] = None,
        target_count: int = 10,
        timeout: float = DEFAULT_VERIFY_TIMEOUT,
        max_workers: Optional[int] = None,
        on_proxy_valid: Optional[Callable[[Dict[str, any]], None]] = None,
        target_name: Optional[str] = None,
        protocols: Optional[List[str]] = None
    ) -> List[Dict[str, any]]:
        """
        验证代理列表（同步包装，支持在主线程或异步事件循环中安全运行）
        """
        if not proxies:
            return []

        # 协议过滤（如用户只想要 socks5 或 https）
        if protocols:
            allow_protos = {p.lower() for p in protocols}
            candidate_proxies = [p for p in proxies if p.get("protocol", "").lower() in allow_protos]
        else:
            candidate_proxies = list(proxies)

        if not candidate_proxies:
            logger.warning("经过协议筛选后无候选代理")
            return []

        try:
            loop = asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if in_loop:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(
                    lambda: asyncio.run(
                        self.verify_proxies_async(
                            proxies=candidate_proxies,
                            target_url=target_url,
                            expected_content=expected_content,
                            target_count=target_count,
                            timeout=timeout,
                            max_workers=max_workers,
                            on_proxy_valid=on_proxy_valid,
                            target_name=target_name
                        )
                    )
                ).result()
        else:
            return asyncio.run(
                self.verify_proxies_async(
                    proxies=candidate_proxies,
                    target_url=target_url,
                    expected_content=expected_content,
                    target_count=target_count,
                    timeout=timeout,
                    max_workers=max_workers,
                    on_proxy_valid=on_proxy_valid,
                    target_name=target_name
                )
            )

    async def verify_proxies_async(
        self,
        proxies: List[Dict[str, any]],
        target_url: Optional[str] = None,
        expected_content: Optional[str] = None,
        target_count: int = 10,
        timeout: float = DEFAULT_VERIFY_TIMEOUT,
        max_workers: Optional[int] = None,
        on_proxy_valid: Optional[Callable[[Dict[str, any]], None]] = None,
        target_name: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """异步并发验证代理可用性"""
        if not proxies:
            return []

        test_url = target_url or self.default_test_url
        workers_count = max_workers or get_auto_workers()
        verify_timeout = min(timeout, 10.0)

        # 按历史评分降序，优先测试高分节点
        sorted_proxies = sorted(proxies, key=lambda x: x.get("score", 0.0), reverse=True)

        logger.info(
            "开始验证 %s 个候选代理 [目标网址: %s | 期望可用: %s | 并发: %s | 超时: %ss]...",
            len(sorted_proxies), test_url, target_count, workers_count, verify_timeout
        )

        working = []
        queue = asyncio.Queue()
        for p in sorted_proxies:
            queue.put_nowait(p)

        stop_event = asyncio.Event()
        verified_count = [0]
        start_time = time.time()

        async def worker():
            while not queue.empty() and not stop_event.is_set():
                proxy = await queue.get()
                protocol = proxy.get("protocol", "http").lower()
                address = proxy.get("address", "")

                try:
                    # 随机微延迟打散并发扫描特征
                    await asyncio.sleep(random.uniform(0.05, 0.25))

                    # 1. 快速 TCP 握手检测
                    try:
                        ip, port_str = address.split(":", 1)
                        port = int(port_str)
                    except ValueError:
                        proxy["fail_count"] = proxy.get("fail_count", 0) + 1
                        proxy["score"] = proxy.get("success_count", 0) - 3 * proxy["fail_count"]
                        continue

                    tcp_ok = await check_tcp_port(ip, port, timeout=min(verify_timeout, 1.2))
                    if not tcp_ok:
                        proxy["fail_count"] = proxy.get("fail_count", 0) + 1
                        proxy["score"] = proxy.get("success_count", 0) - 3 * proxy["fail_count"]
                        continue

                    # 2. 真实网络连通与内容校验
                    proxy_url = f"{protocol}://{address}"
                    connector = None
                    client_proxy = None

                    if protocol in ("socks5", "socks4"):
                        connector = ProxyConnector.from_url(proxy_url, rdns=True)
                    else:
                        connector = aiohttp.TCPConnector(use_dns_cache=True)
                        client_proxy = proxy_url

                    req_start = time.time()
                    async with aiohttp.ClientSession(connector=connector) as session:
                        async with session.get(
                            test_url,
                            proxy=client_proxy,
                            timeout=aiohttp.ClientTimeout(total=verify_timeout),
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"},
                            ssl=DEFAULT_VERIFY_SSL
                        ) as resp:
                            req_end = time.time()
                            latency_ms = round((req_end - req_start) * 1000, 1)

                            if resp.status == 200:
                                is_valid = True
                                if expected_content:
                                    html = await resp.text(errors="ignore")
                                    if expected_content not in html:
                                        is_valid = False

                                if is_valid and not stop_event.is_set():
                                    proxy["success_count"] = proxy.get("success_count", 0) + 1
                                    proxy["score"] = proxy["success_count"] - 3 * proxy.get("fail_count", 0)
                                    proxy["last_verified"] = time.time()
                                    proxy["latency_ms"] = latency_ms

                                    if "valid_targets" not in proxy or not isinstance(proxy["valid_targets"], set):
                                        proxy["valid_targets"] = set()
                                    if target_name:
                                        proxy["valid_targets"].add(target_name)

                                    working.append(proxy)
                                    if on_proxy_valid:
                                        try:
                                            on_proxy_valid(proxy)
                                        except Exception as cb_err:
                                            logger.debug("on_proxy_valid 回调异常: %s", cb_err)

                                    if len(working) >= target_count:
                                        stop_event.set()
                                else:
                                    proxy["fail_count"] = proxy.get("fail_count", 0) + 1
                                    proxy["score"] = proxy.get("success_count", 0) - 3 * proxy["fail_count"]
                            else:
                                proxy["fail_count"] = proxy.get("fail_count", 0) + 1
                                proxy["score"] = proxy.get("success_count", 0) - 3 * proxy["fail_count"]

                except asyncio.CancelledError:
                    break
                except Exception:
                    proxy["fail_count"] = proxy.get("fail_count", 0) + 1
                    proxy["score"] = proxy.get("success_count", 0) - 3 * proxy["fail_count"]
                finally:
                    queue.task_done()
                    if not stop_event.is_set():
                        verified_count[0] += 1
                        curr = verified_count[0]
                        if curr % 10000 == 0 or curr == len(sorted_proxies):
                            logger.info("  进度: %s/%s [已发现可用: %s 个, 耗时: %.1fs]", curr, len(sorted_proxies), len(working), time.time() - start_time)

        num_workers = min(workers_count, len(sorted_proxies))
        tasks = [asyncio.create_task(worker()) for _ in range(num_workers)]
        await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time
        logger.info("验证完成: 获得 %s 个可用代理 (总耗时 %.2fs)", len(working), elapsed)
        return working
