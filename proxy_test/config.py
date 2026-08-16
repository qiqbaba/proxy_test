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
    # 1. 实时 HTTPS 专用源 (高可用)
    "sslproxies_org": "https://www.sslproxies.org/",
    "proxyscrape_https": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=https&timeout=10000&country=all",
    "roosterkid_https": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "r00tee_https": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",
    
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
    
    # 3. 实时 SOCKS4 代理源
    "proxyscraper_socks4": "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks4.txt",
    "anonym0uswork_socks4": "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks4_proxies.txt",

    # 4. 高匿/精选综合源
    "proxifly_all": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
    "vpslab_all_elite": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/all_elite.txt",
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
