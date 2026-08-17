"""
命令行测试工具 (CLI)
支持通过命令行对单个或批量爬虫目标网站进行代理检测、表格输出与格式化保存
"""
import os
import sys
import json
import argparse
from typing import List, Dict
from urllib.parse import urlparse

from proxy_test import test_website_proxies, get_global_pool, ProxyExporter
from proxy_test.config import DEFAULT_CRAWLER_TARGETS
from proxy_test.logger import get_logger

logger = get_logger("proxy_test.cli")


def print_single_table(proxies: list, target_url: str):
    """格式化打印单站点详细代理表格"""
    if not proxies:
        print(f"\n[!] 目标网站 {target_url} 未找到可用代理。")
        return

    headers = ["#", "协议", "代理地址 (IP:Port)", "延迟 (ms)", "积分", "代理源"]
    col_widths = [4, 8, 24, 12, 8, 22]

    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
    sep_line = "-+-".join("-" * w for w in col_widths)

    print("\n" + "=" * len(header_line))
    print(header_line)
    print(sep_line)

    for i, p in enumerate(proxies, 1):
        proto = p.get("protocol", "http").upper()
        addr = p.get("address", "")
        latency = f"{p.get('latency_ms', 0.0):.1f} ms"
        score = f"{p.get('score', 0.0):.1f}"
        source = p.get("source", "")[:20]

        row = [str(i), proto, addr, latency, score, source]
        print(" | ".join(f"{val:<{w}}" for val, w in zip(row, col_widths)))

    print("=" * len(header_line) + "\n")


# Windows 终端 UTF-8 编码适配
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def print_summary_table(site_results: Dict[str, List[Dict]], target_meta_map: Dict[str, Dict]):
    """格式化打印站点代理测试汇总表格（统计每个站点的可用数与延迟，不逐条列出代理明细）"""
    headers = ["#", "标识", "目标网站", "可用数", "最佳延迟", "平均延迟", "状态"]
    col_widths = [4, 16, 30, 8, 12, 12, 10]

    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
    sep_line = "-+-".join("-" * w for w in col_widths)

    print("\n" + "=" * len(header_line))
    print(" 爬虫目标代理测试汇总表")
    print("=" * len(header_line))
    print(header_line)
    print(sep_line)

    total_valid_count = 0
    all_unique_addrs = set()

    for idx, (url, proxies) in enumerate(site_results.items(), 1):
        meta = target_meta_map.get(url, {})
        tag = meta.get("name", meta.get("source", urlparse(url).netloc))
        url_display = url[:28] + ".." if len(url) > 30 else url
        count = len(proxies)
        total_valid_count += count

        for p in proxies:
            all_unique_addrs.add(f"{p['protocol']}://{p['address']}")

        if proxies:
            latencies = [p.get("latency_ms", 0.0) for p in proxies]
            min_lat = f"{min(latencies):.1f} ms"
            avg_lat = f"{sum(latencies)/len(latencies):.1f} ms"
            status = "[OK] 正常"
        else:
            min_lat = "-"
            avg_lat = "-"
            status = "[--] 警告"

        row = [str(idx), str(tag), url_display, str(count), min_lat, avg_lat, status]
        print(" | ".join(f"{val:<{w}}" for val, w in zip(row, col_widths)))

    print("=" * len(header_line))
    print(f"[*] 汇总: 已测试 {len(site_results)} 个爬虫站点 | 站点可用总槽位: {total_valid_count} | 全局独立代理: {len(all_unique_addrs)} 个\n")


def main():
    parser = argparse.ArgumentParser(
        description="proxy_test - 高性能异步代理抓取与目标网站可用性测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例用法:
  # 1. 默认批量测试所有 11 个爬虫目标网站:
  python cli.py -u all -c 10
  
  # 2. 测试单个目标网站:
  python cli.py -u https://u3c3.com/ -c 10 --timeout 5.0
  
  # 3. 批量测试指定多个网站 (以逗号分隔):
  python cli.py -u https://u3c3.com/,https://seju.life/ -c 5
  
  # 4. 强制重新抓取网络代理源并导出自定义文件:
  python cli.py -u all -f -o ./all_proxies.json
"""
    )
    parser.add_argument(
        "-u", "--url", type=str, default="all",
        help="目标测试网址。支持单个 URL、逗号分隔多 URL 或 'all' (测试 fuli_crawler 全部 11 个爬虫网站，默认: all)"
    )
    parser.add_argument("-e", "--expect", type=str, default=None, help="期望网页中包含的文本关键字 (仅单站模式有效)")
    parser.add_argument("-c", "--count", type=int, default=1000, help="每个目标网站期望获取的可用代理数量 (默认: 1000)")
    parser.add_argument("-t", "--timeout", type=float, default=5.0, help="单次请求验证超时秒数 (默认: 5.0)")
    parser.add_argument("-w", "--workers", type=int, default=None, help="并发协程数 (默认根据 CPU 与内存自动计算)")
    parser.add_argument("-f", "--force-fetch", action="store_true", default=False, help="强制重新从网络代理源抓取候选列表")
    parser.add_argument("-p", "--protocols", type=str, default=None, help="允许的协议类型，多个以逗号分隔 (如: socks5,https)")
    parser.add_argument("-o", "--export", type=str, default=None, help="自定义导出文件路径 (.json 或 .txt)")
    parser.add_argument("--fetch-proxy", type=str, default=None, help="拉取代理源时使用的临时代理 (如: http://127.0.0.1:7890)")
    parser.add_argument("--no-export", action="store_true", default=False, help="禁止自动导出到 data/ 目录")
    parser.add_argument("--list-proxies", action="store_true", default=False, help="测试结束后在终端逐条打印可用代理明细列表 (默认不列出)")
    parser.add_argument("--merge", action="store_true", default=False, help="扫描并合并 data/sites/ 目录中的所有测试产物至全局文件")
    parser.add_argument("--merge-artifacts", type=str, default=None, help="从 GitHub Actions 下载的多任务产物根目录合并至 data/sites/ 并生成全局文件")

    args = parser.parse_args()

    exporter = ProxyExporter()

    # 处理产物合并模式
    if args.merge or args.merge_artifacts:
        import shutil
        if args.merge_artifacts and os.path.exists(args.merge_artifacts):
            print(f"[*] 正在从产物目录 {args.merge_artifacts} 搜集各站点测试结果...")
            for root, dirs, files in os.walk(args.merge_artifacts):
                for f in files:
                    if f.endswith(".json") or f.endswith(".txt"):
                        src_file = os.path.join(root, f)
                        dst_file = os.path.join(exporter.sites_dir, f)
                        shutil.copy2(src_file, dst_file)
                        print(f"    -> 导入: {f}")

        print("[*] 正在合并所有站点测试产物...")
        exported = exporter.merge_all_sites(custom_export_path=args.export)
        
        # 加载合并后的站点结果用于打印汇总表格
        site_results = {}
        target_meta_map = {item["url"]: item for item in DEFAULT_CRAWLER_TARGETS}
        for item in DEFAULT_CRAWLER_TARGETS:
            domain = urlparse(item["url"]).netloc
            safe_name = domain.replace(":", "_").replace("/", "_")
            site_json = os.path.join(exporter.sites_dir, f"{safe_name}.json")
            if os.path.exists(site_json):
                try:
                    with open(site_json, "r", encoding="utf-8") as jf:
                        site_results[item["url"]] = json.load(jf).get("proxies", [])
                except Exception:
                    pass
        if site_results:
            print_summary_table(site_results, target_meta_map)
        print(f"[+] 合并完成! 全局代理文件已更新至 data/ 目录。")
        return

    protocols_list = [p.strip().lower() for p in args.protocols.split(",") if p.strip()] if args.protocols else None

    # 解析目标网站列表
    targets: List[Dict[str, str]] = []
    target_meta_map: Dict[str, Dict] = {}

    if args.url.strip().lower() in ("all", "default", "*", ""):
        # 使用 fuli_crawler 默认的 11 个站点
        for item in DEFAULT_CRAWLER_TARGETS:
            targets.append(item)
            target_meta_map[item["url"]] = item
    elif "," in args.url:
        for u in args.url.split(","):
            u = u.strip()
            if u:
                item = {"url": u, "name": urlparse(u).netloc, "source": urlparse(u).netloc}
                targets.append(item)
                target_meta_map[u] = item
    else:
        u = args.url.strip()
        item = {"url": u, "name": urlparse(u).netloc, "source": urlparse(u).netloc}
        targets.append(item)
        target_meta_map[u] = item

    is_batch = len(targets) > 1

    print(f"[*] 启动代理测试任务: 共 {len(targets)} 个目标网站")
    print(f"[*] 每个网站期望可用数: {args.count} 个 | 单次超时: {args.timeout}s | 协议: {protocols_list or '全部'}\n")

    pool = get_global_pool(fetch_proxy=args.fetch_proxy)
    site_results: Dict[str, List[Dict]] = {}

    for idx, target in enumerate(targets, 1):
        url = target["url"]
        name = target.get("name", target.get("source", url))
        print(f"[{idx}/{len(targets)}] 正在测试站点: {name} ({url}) ...")

        # 仅在第一个站点时按用户参数 force_fetch，后续站点复用已抓取缓存池
        force = args.force_fetch if idx == 1 else False

        working = pool.verify_proxies_for_target(
            target_url=url,
            expected_content=args.expect if not is_batch else None,
            target_count=args.count,
            timeout=args.timeout,
            max_workers=args.workers,
            force_fetch=force,
            protocols=protocols_list,
            fetch_proxy=args.fetch_proxy
        )
        site_results[url] = working
        print(f"    -> 找到 {len(working)} 个可用代理")

    # 打印汇总表格（不逐条列出具体代理）
    print_summary_table(site_results, target_meta_map)

    # 仅当显式指定 --list-proxies 时才打印明细表格
    if args.list_proxies:
        for url, proxies in site_results.items():
            print_single_table(proxies, url)

    if not args.no_export:
        if is_batch:
            exported = exporter.export_batch(site_results, custom_export_path=args.export)
            print(f"[+] 结果已聚合导出至 data/ 目录及 data/sites/ 各站点专属文件。")
        else:
            url = targets[0]["url"]
            working = site_results.get(url, [])
            exported = exporter.export(working, target_url=url, custom_export_path=args.export)
            print(f"[+] 测试完成! 共找到 {len(working)} 个针对 {url} 可用的代理。已保存至 data/")


if __name__ == "__main__":
    main()
