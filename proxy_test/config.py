"""
配置模块
管理代理源列表、超时设置、验证参数、硬件自适应并发及路径常量
"""
import os
import sys
from functools import lru_cache
from typing import Dict

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据与缓存目录
DATA_DIR = os.environ.get("PROXY_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
CACHE_DIR = os.environ.get("PROXY_CACHE_DIR", os.path.join(PROJECT_ROOT, "cache"))
CACHE_DB_PATH = os.path.join(CACHE_DIR, "proxy_cache.db")

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "sites"), exist_ok=True)

# 默认验证参数
DEFAULT_VERIFY_TIMEOUT = float(os.environ.get("PROXY_VERIFY_TIMEOUT", "5.0"))
DEFAULT_VERIFY_SSL = os.environ.get("PROXY_VERIFY_SSL", "false").lower() == "true"  # 代理验证默认不强制严格校验证书以提升兼容性
DEFAULT_CACHE_TTL = int(os.environ.get("PROXY_CACHE_TTL", "43200"))  # 12 小时

# 默认爬虫目标网站清单 (同步自 fuli_crawler)
DEFAULT_CRAWLER_TARGETS = [
    {"source": "seju", "name": "色橘", "url": "https://seju.life/"},
    {"source": "u3c3", "name": "U3C3", "url": "https://u3c3.com/"},
    {"source": "datang", "name": "大唐解密", "url": "https://dtbt7.com/"},
    {"source": "gcbt", "name": "国产BT", "url": "https://gcbt.net/"},
    {"source": "madou", "name": "麻豆解密", "url": "https://ypb.295282.xyz/"},
    {"source": "jingpin_toupai", "name": "精品偷拍", "url": "https://pms.532862.xyz/"},
    {"source": "taose", "name": "桃色解密", "url": "https://taosebt.com/"},
    {"source": "dashen", "name": "大神解密", "url": "https://j4f4.com/"},
    {"source": "tanhua", "name": "探花解密", "url": "https://thbt8.com/"},
    {"source": "jingpin", "name": "精品解密", "url": "https://jpbt3.com/"},
    {"source": "mianfei_guochan", "name": "免费国产", "url": "https://mfgc3.com/"},
]

# 默认通用测试 URL（若未指定目标网站时使用）
DEFAULT_TEST_URLS = [
    "https://api.myip.com",
    "https://www.cloudflare.com",
    "https://www.baidu.com",
]

# 高质量高频更新免费代理源配置 (HTTP / HTTPS / SOCKS4 / SOCKS5)
PROXY_SOURCES: Dict[str, str] = {
    # 1. 实时 HTTPS 专用源
    "proxyscrape_https": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=https&timeout=10000&country=all",
    "roosterkid_https": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "r00tee_https": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",
    "vmheaven_https": "https://raw.githubusercontent.com/vmheaven/VMHeaven-Free-Proxy-Updated/refs/heads/main/https.txt",
    "ercindedeoglu_https": "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt",
    "jetkai_https": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
    "zloi_https": "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt",
    "vakhov_https": "https://vakhov.github.io/fresh-proxy-list/https.txt",

    # 2. 实时 SOCKS5 代理源
    "proxyscrape_socks5": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
    "speedx_socks5": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "speedx_proxy_list_socks5": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "proxyscraper_socks5": "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks5.txt",
    "monosans_socks5": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "roosterkid_socks5": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
    "thordata_socks5": "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/socks5.txt",
    "vpslab_socks5_all": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/socks5_all.txt",
    "r00tee_socks5": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt",
    "databay_socks5": "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/socks5.txt",
    "vakhov_socks5": "https://vakhov.github.io/fresh-proxy-list/socks5.txt",
    "komutan_socks5": "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/socks5.txt",
    "gfpcom_socks5": "https://raw.githubusercontent.com/wiki/gfpcom/free-proxy-list/lists/socks5.txt",
    # 新增 SOCKS5 优质源
    "murongpig_socks5": "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt",
    "ercindedeoglu_socks5": "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt",
    "zevtyardt_socks5": "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks5.txt",
    "vmheaven_socks5": "https://raw.githubusercontent.com/vmheaven/VMHeaven-Free-Proxy-Updated/refs/heads/main/socks5.txt",
    "jetkai_socks5": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
    "zloi_socks5": "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt",
    "aliilapro_socks5": "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt",
    "shiftytr_socks5": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    "hendrikbgr_socks5": "https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt",
    "hookzof_socks5": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "rdavydov_socks5": "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks5.txt",
    "prxchk_socks5": "https://raw.githubusercontent.com/prxchk/proxy-list/main/socks5.txt",
    "sunny9577_socks5": "https://raw.githubusercontent.com/Sunny9577/proxy-scraper/master/generated/socks5_proxies.txt",

    # 3. 实时 SOCKS4 代理源
    "proxyscrape_socks4": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000&country=all",
    "speedx_socks4": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
    "speedx_proxy_list_socks4": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
    "proxyscraper_socks4": "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks4.txt",
    "monosans_socks4": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
    "roosterkid_socks4": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
    "anonym0uswork_socks4": "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks4_proxies.txt",
    "thordata_socks4": "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/socks4.txt",
    "vpslab_socks4_all": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/socks4_all.txt",
    "r00tee_socks4": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks4.txt",
    "vakhov_socks4": "https://vakhov.github.io/fresh-proxy-list/socks4.txt",
    "komutan_socks4": "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/socks4.txt",
    "gfpcom_socks4": "https://raw.githubusercontent.com/wiki/gfpcom/free-proxy-list/lists/socks4.txt",
    # 新增 SOCKS4 优质源
    "murongpig_socks4": "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt",
    "ercindedeoglu_socks4": "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks4.txt",
    "zevtyardt_socks4": "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks4.txt",
    "vmheaven_socks4": "https://raw.githubusercontent.com/vmheaven/VMHeaven-Free-Proxy-Updated/refs/heads/main/socks4.txt",
    "jetkai_socks4": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
    "zloi_socks4": "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt",
    "aliilapro_socks4": "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks4.txt",
    "shiftytr_socks4": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
    "rdavydov_socks4": "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks4.txt",
    "prxchk_socks4": "https://raw.githubusercontent.com/prxchk/proxy-list/main/socks4.txt",
    "sunny9577_socks4": "https://raw.githubusercontent.com/Sunny9577/proxy-scraper/master/generated/socks4_proxies.txt",

    # 4. 高匿/精选综合源
    "proxifly_all": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
    "vpslab_all_elite": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/all_elite.txt",
    "clarketm_proxy": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
}

@lru_cache(maxsize=None)
def get_auto_workers(base_multiplier: int = 30, max_limit: int = 300, min_limit: int = 50) -> int:
    """
    根据 CPU 核心数、可用内存与操作系统平台自动适配最优并发协程数
    """
    env_val = os.environ.get("PROXY_VERIFY_WORKERS")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass

    try:
        cpu_count = os.cpu_count() or 1
        workers = cpu_count * base_multiplier

        try:
            import psutil
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024 ** 3)
            if total_gb < 1.5:
                workers = min(workers, 50)
            elif total_gb < 3.5:
                workers = min(workers, 120)
        except ImportError:
            if cpu_count == 1:
                workers = min(workers, 60)

        # Windows 下限制最大并发防止句柄耗尽
        if sys.platform.startswith("win"):
            max_limit = min(max_limit, 200)

    except Exception:
        workers = 80

    return max(min_limit, min(workers, max_limit))
