"""
结果导出模块
负责将测试验证通过的代理列表导出为 JSON, TXT 以及按域名分类的文件
"""
import os
import json
import time
from typing import List, Dict, Optional
from urllib.parse import urlparse
from proxy_test.config import DATA_DIR
from proxy_test.logger import get_logger

logger = get_logger("proxy_test.exporter")


class ProxyExporter:
    """代理结果导出器"""

    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.sites_dir = os.path.join(self.data_dir, "sites")
        os.makedirs(self.sites_dir, exist_ok=True)

    def export(
        self,
        working_proxies: List[Dict[str, any]],
        target_url: Optional[str] = None,
        custom_export_path: Optional[str] = None
    ) -> Dict[str, str]:
        """
        导出代理结果到文件系统
        
        Returns:
            导出的文件路径映射字典
        """
        exported_files = {}
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        domain = urlparse(target_url).netloc if target_url else "global"

        # 1. 导出全量最新 JSON 格式
        json_path = os.path.join(self.data_dir, "proxies_latest.json")
        json_data = {
            "meta": {
                "updated_at": now_str,
                "timestamp": time.time(),
                "total_valid": len(working_proxies),
                "target_url": target_url or "general",
            },
            "proxies": [
                {
                    "protocol": p["protocol"],
                    "address": p["address"],
                    "proxy_url": f"{p['protocol']}://{p['address']}",
                    "latency_ms": p.get("latency_ms", 0.0),
                    "score": round(p.get("score", 0.0), 2),
                    "source": p.get("source", ""),
                    "valid_targets": list(p.get("valid_targets", [])) if isinstance(p.get("valid_targets"), (set, list)) else [],
                    "last_verified": p.get("last_verified", 0.0),
                }
                for p in working_proxies
            ]
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        exported_files["json"] = json_path

        # 2. 导出全量 TXT 格式 (每行一个 protocol://ip:port)
        txt_path = os.path.join(self.data_dir, "proxies.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            for p in working_proxies:
                f.write(f"{p['protocol']}://{p['address']}\n")
        exported_files["txt"] = txt_path

        # 3. 按测试站点导出专用 TXT 和 JSON
        if domain and domain != "global":
            safe_domain_name = domain.replace(":", "_").replace("/", "_")
            site_txt_path = os.path.join(self.sites_dir, f"{safe_domain_name}.txt")
            with open(site_txt_path, "w", encoding="utf-8") as f:
                for p in working_proxies:
                    f.write(f"{p['protocol']}://{p['address']}\n")
            exported_files["site_txt"] = site_txt_path

            site_json_path = os.path.join(self.sites_dir, f"{safe_domain_name}.json")
            with open(site_json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "target_url": target_url,
                    "domain": domain,
                    "updated_at": now_str,
                    "count": len(working_proxies),
                    "proxies": [
                        {
                            "protocol": p["protocol"],
                            "address": p["address"],
                            "proxy_url": f"{p['protocol']}://{p['address']}",
                            "latency_ms": p.get("latency_ms", 0.0),
                            "score": round(p.get("score", 0.0), 2),
                            "source": p.get("source", ""),
                            "valid_targets": list(p.get("valid_targets", [])) if isinstance(p.get("valid_targets"), (set, list)) else [domain],
                            "last_verified": p.get("last_verified", 0.0),
                        }
                        for p in working_proxies
                    ]
                }, f, ensure_ascii=False, indent=2)
            exported_files["site_json"] = site_json_path

        # 4. 如果用户指定了自定义导出路径
        if custom_export_path:
            os.makedirs(os.path.dirname(os.path.abspath(custom_export_path)), exist_ok=True)
            if custom_export_path.endswith(".json"):
                with open(custom_export_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
            else:
                with open(custom_export_path, "w", encoding="utf-8") as f:
                    for p in working_proxies:
                        f.write(f"{p['protocol']}://{p['address']}\n")
            exported_files["custom"] = custom_export_path

        logger.info("已将 %s 个可用代理成功导出至: %s", len(working_proxies), self.data_dir)
        return exported_files

    def merge_all_sites(self, custom_export_path: Optional[str] = None) -> Dict[str, str]:
        """
        扫描 data/sites/ 目录下所有已测试站点的 JSON / TXT 产物，并聚合生成全局统一文件
        """
        site_results: Dict[str, List[Dict[str, any]]] = {}
        if os.path.exists(self.sites_dir):
            # 1. 优先读取 .json 格式（带完整延迟、评分等元数据）
            json_domains = set()
            for filename in os.listdir(self.sites_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.sites_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            target_url = data.get("target_url") or f"https://{data.get('domain', filename[:-5])}/"
                            domain = data.get("domain") or filename[:-5]
                            json_domains.add(domain)
                            proxies = data.get("proxies", [])
                            site_results[target_url] = proxies
                    except Exception as e:
                        logger.warning("读取站点 JSON 异常 %s: %s", filepath, e)

            # 2. 兼容仅有 .txt 的历史文件
            for filename in os.listdir(self.sites_dir):
                if filename.endswith(".txt"):
                    domain = filename[:-4]
                    if domain not in json_domains:
                        filepath = os.path.join(self.sites_dir, filename)
                        proxies = []
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if line and "://" in line:
                                        proto, addr = line.split("://", 1)
                                        proxies.append({
                                            "protocol": proto,
                                            "address": addr,
                                            "latency_ms": 500.0,
                                            "score": 1.0,
                                            "valid_targets": {domain}
                                        })
                            if proxies:
                                site_results[f"https://{domain}/"] = proxies
                        except Exception as e:
                            logger.warning("读取站点 TXT 异常 %s: %s", filepath, e)

        return self.export_batch(site_results, custom_export_path=custom_export_path)

    def export_batch(
        self,
        site_results: Dict[str, List[Dict[str, any]]],
        custom_export_path: Optional[str] = None
    ) -> Dict[str, str]:
        """
        批量导出多个站点的测试结果，并聚合生成全局可用代理列表
        
        Args:
            site_results: 字典 { target_url: [proxy_dict, ...] }
            custom_export_path: 自定义导出路径 (可选)
            
        Returns:
            导出的主要文件路径映射
        """
        exported_files = {}
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        # 1. 分别为每个站点写入专属 TXT
        all_unique_proxies: Dict[str, Dict[str, any]] = {}
        site_stats = {}

        for url, proxies in site_results.items():
            domain = urlparse(url).netloc or "global"
            safe_domain_name = domain.replace(":", "_").replace("/", "_")
            site_txt_path = os.path.join(self.sites_dir, f"{safe_domain_name}.txt")
            with open(site_txt_path, "w", encoding="utf-8") as f:
                for p in proxies:
                    f.write(f"{p['protocol']}://{p['address']}\n")
            site_stats[domain] = len(proxies)

            # 汇聚到全局唯一字典 (key: "protocol://address")
            for p in proxies:
                key = f"{p['protocol']}://{p['address']}"
                if key not in all_unique_proxies:
                    item = dict(p)
                    # 确保 valid_targets 是集合/列表
                    targets = set(item.get("valid_targets", []))
                    targets.add(domain)
                    item["valid_targets"] = targets
                    all_unique_proxies[key] = item
                else:
                    targets = set(all_unique_proxies[key].get("valid_targets", []))
                    targets.add(domain)
                    all_unique_proxies[key]["valid_targets"] = targets
                    # 更新更佳评分与更低延迟
                    if p.get("score", 0) > all_unique_proxies[key].get("score", 0):
                        all_unique_proxies[key]["score"] = p.get("score", 0)
                    if p.get("latency_ms", 9999) < all_unique_proxies[key].get("latency_ms", 9999):
                        all_unique_proxies[key]["latency_ms"] = p.get("latency_ms")

        working_list = list(all_unique_proxies.values())
        # 按评分降序、延迟升序排序
        working_list.sort(key=lambda x: (-x.get("score", 0), x.get("latency_ms", 9999)))

        # 2. 导出全局 proxies_latest.json
        json_path = os.path.join(self.data_dir, "proxies_latest.json")
        json_data = {
            "meta": {
                "updated_at": now_str,
                "timestamp": time.time(),
                "total_unique_valid": len(working_list),
                "sites_tested": len(site_results),
                "site_summary": site_stats,
            },
            "proxies": [
                {
                    "protocol": p["protocol"],
                    "address": p["address"],
                    "proxy_url": f"{p['protocol']}://{p['address']}",
                    "latency_ms": p.get("latency_ms", 0.0),
                    "score": round(p.get("score", 0.0), 2),
                    "source": p.get("source", ""),
                    "valid_targets": sorted(list(p.get("valid_targets", []))),
                    "last_verified": p.get("last_verified", 0.0),
                }
                for p in working_list
            ]
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        exported_files["json"] = json_path

        # 3. 导出全局 proxies.txt
        txt_path = os.path.join(self.data_dir, "proxies.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            for p in working_list:
                f.write(f"{p['protocol']}://{p['address']}\n")
        exported_files["txt"] = txt_path

        # 4. 自定义导出
        if custom_export_path:
            os.makedirs(os.path.dirname(os.path.abspath(custom_export_path)), exist_ok=True)
            if custom_export_path.endswith(".json"):
                with open(custom_export_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
            else:
                with open(custom_export_path, "w", encoding="utf-8") as f:
                    for p in working_list:
                        f.write(f"{p['protocol']}://{p['address']}\n")
            exported_files["custom"] = custom_export_path

        logger.info("批量测试完成: 共测试 %s 个网站，汇总生成 %s 个全局独立可用代理", len(site_results), len(working_list))
        return exported_files

