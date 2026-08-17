"""
代理池管理模块
负责代理的持久化存储 (SQLite)、增量更新、动态打分、多线程轮询与自动补给
"""
import os
import time
import random
import sqlite3
import threading
import atexit
from typing import List, Dict, Optional
from urllib.parse import urlparse

from proxy_test.config import CACHE_DB_PATH, DEFAULT_CACHE_TTL, get_auto_workers
from proxy_test.fetcher import ProxyFetcher
from proxy_test.verifier import ProxyVerifier
from proxy_test.logger import get_logger

logger = get_logger("proxy_test.pool")


class ProxyPool:
    """代理池管理器"""

    def __init__(self, cache_ttl: int = DEFAULT_CACHE_TTL, db_path: str = CACHE_DB_PATH, fetch_proxy: Optional[str] = None):
        self.cache_ttl = cache_ttl
        self.db_path = db_path
        self._proxies: List[Dict[str, any]] = []
        self._working_proxies: List[Dict[str, any]] = []
        self._lock = threading.RLock()
        self._last_fetch_time = 0
        self._last_verify_time = 0
        self._current_idx = 0
        self._thread_proxy_map: Dict[int, str] = {}
        self._is_replenishing = False
        self._is_verifying = False

        self.fetcher = ProxyFetcher(fetch_proxy=fetch_proxy)
        self.verifier = ProxyVerifier()

        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()
        self._load_cache()

        atexit.register(self.save_cache)

    def _init_db(self):
        """初始化 SQLite 数据库"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=DELETE;")
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proxy_cache (
                    protocol TEXT NOT NULL,
                    address TEXT NOT NULL,
                    source TEXT,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    score REAL DEFAULT 0.0,
                    latency_ms REAL DEFAULT 0.0,
                    last_verified REAL DEFAULT 0,
                    valid_targets TEXT DEFAULT '',
                    PRIMARY KEY (protocol, address)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("初始化 SQLite 数据库失败: %s", e)

    def _load_cache(self):
        """从 SQLite 加载有效代理"""
        if not os.path.exists(self.db_path):
            return
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT key, value FROM cache_meta")
            meta = {row["key"]: row["value"] for row in cursor.fetchall()}
            self._last_fetch_time = int(meta.get("last_fetch_time", 0))
            self._last_verify_time = int(meta.get("last_verify_time", 0))

            cursor.execute("SELECT * FROM proxy_cache")
            self._proxies = []
            self._working_proxies = []
            for row in cursor.fetchall():
                valid_set = set()
                targets_str = row["valid_targets"]
                if targets_str:
                    valid_set = set(t.strip() for t in targets_str.split(",") if t.strip())

                p = {
                    "protocol": row["protocol"],
                    "address": row["address"],
                    "source": row["source"],
                    "success_count": row["success_count"],
                    "fail_count": row["fail_count"],
                    "score": row["score"],
                    "latency_ms": row["latency_ms"],
                    "last_verified": row["last_verified"],
                    "valid_targets": valid_set
                }
                self._proxies.append(p)
                if p["last_verified"] > 0 and p["score"] >= -5:
                    self._working_proxies.append(p.copy())

            conn.close()
            logger.info("从缓存加载了 %s 个候选代理 (其中 %s 个已验证有效)", len(self._proxies), len(self._working_proxies))
        except Exception as e:
            logger.warning("加载 SQLite 缓存异常: %s", e)

    def save_cache(self):
        """保存代理池数据到 SQLite 数据库 (UPSERT 增量写入)"""
        with self._lock:
            if not self._proxies:
                return
            proxies_to_save = list(self._proxies)
            working_keys = {(p["protocol"], p["address"]) for p in self._working_proxies}
            last_fetch = self._last_fetch_time
            last_verify = self._last_verify_time

        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")

            cursor.execute("INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)", ("last_fetch_time", str(int(last_fetch))))
            cursor.execute("INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)", ("last_verify_time", str(int(last_verify))))

            for p in proxies_to_save:
                key = (p["protocol"], p["address"])
                last_ver = p.get("last_verified", 0.0)
                if key not in working_keys and p.get("score", 0.0) < -5:
                    last_ver = 0.0

                targets_set = p.get("valid_targets", set())
                targets_str = ",".join(targets_set) if isinstance(targets_set, set) else ""

                cursor.execute("""
                    INSERT INTO proxy_cache (protocol, address, source, success_count, fail_count, score, latency_ms, last_verified, valid_targets)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(protocol, address) DO UPDATE SET
                        source = EXCLUDED.source,
                        success_count = EXCLUDED.success_count,
                        fail_count = EXCLUDED.fail_count,
                        score = EXCLUDED.score,
                        latency_ms = EXCLUDED.latency_ms,
                        last_verified = EXCLUDED.last_verified,
                        valid_targets = EXCLUDED.valid_targets
                """, (
                    p["protocol"],
                    p["address"],
                    p.get("source", ""),
                    p.get("success_count", 0),
                    p.get("fail_count", 0),
                    p.get("score", 0.0),
                    p.get("latency_ms", 0.0),
                    last_ver,
                    targets_str
                ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("保存 SQLite 缓存失败: %s", e)

    def fetch_proxies(self, force: bool = False, min_count: int = 200, fetch_proxy: Optional[str] = None) -> int:
        """获取并更新代理池候选列表"""
        now = time.time()
        if not force and (now - self._last_fetch_time) < self.cache_ttl and len(self._proxies) >= min_count:
            logger.info("当前候选代理充足 (%s 个)，跳过网络抓取", len(self._proxies))
            return len(self._proxies)

        existing_history = {}
        with self._lock:
            for p in self._proxies:
                key = f"{p['protocol']}://{p['address']}"
                existing_history[key] = p

        if fetch_proxy:
            self.fetcher.fetch_proxy = fetch_proxy

        fetched = self.fetcher.fetch_all()
        merged = {}
        for p in fetched:
            key = f"{p['protocol']}://{p['address']}"
            if key in existing_history:
                old = existing_history[key]
                p["success_count"] = old.get("success_count", 0)
                p["fail_count"] = old.get("fail_count", 0)
                p["score"] = old.get("score", 0.0)
                p["latency_ms"] = old.get("latency_ms", 0.0)
                p["last_verified"] = old.get("last_verified", 0.0)
                p["valid_targets"] = old.get("valid_targets", set())
            else:
                p["success_count"] = 0
                p["fail_count"] = 0
                p["score"] = 0.0
                p["latency_ms"] = 0.0
                p["last_verified"] = 0.0
                p["valid_targets"] = set()
            merged[key] = p

        with self._lock:
            self._proxies = list(merged.values())
            self._last_fetch_time = now

        self.save_cache()
        return len(self._proxies)

    def verify_proxies_for_target(
        self,
        target_url: str,
        expected_content: Optional[str] = None,
        target_count: int = 10,
        timeout: float = 5.0,
        max_workers: Optional[int] = None,
        force_fetch: bool = False,
        protocols: Optional[List[str]] = None,
        fetch_proxy: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """专门针对指定目标网址测试并返回可用代理列表"""
        domain = urlparse(target_url).netloc or target_url

        if force_fetch or not self._proxies:
            self.fetch_proxies(force=force_fetch, fetch_proxy=fetch_proxy)

        working = self.verifier.verify_proxies(
            proxies=self._proxies,
            target_url=target_url,
            expected_content=expected_content,
            target_count=target_count,
            timeout=timeout,
            max_workers=max_workers,
            target_name=domain,
            protocols=protocols
        )

        with self._lock:
            now = time.time()
            self._last_verify_time = now
            existing_addrs = {(p["protocol"], p["address"]) for p in self._working_proxies}
            for w in working:
                if (w["protocol"], w["address"]) not in existing_addrs:
                    self._working_proxies.append(w)

        self.save_cache()
        return working

    def get_working_proxy(self, target_url: Optional[str] = None, exclusive: bool = False) -> Optional[str]:
        """获取一个可用代理 URL (如 'socks5://1.2.3.4:1080')"""
        domain = urlparse(target_url).netloc if target_url else None
        with self._lock:
            if not self._working_proxies:
                return None

            if domain:
                matching = [p for p in self._working_proxies if domain in p.get("valid_targets", set())]
            else:
                matching = list(self._working_proxies)

            candidates = matching if matching else self._working_proxies
            if not candidates:
                return None

            if exclusive:
                tid = threading.get_ident()
                if tid in self._thread_proxy_map:
                    return self._thread_proxy_map[tid]
                sel = candidates[self._current_idx % len(candidates)]
                self._current_idx += 1
                res = f"{sel['protocol']}://{sel['address']}"
                self._thread_proxy_map[tid] = res
                return res
            else:
                sel = random.choice(candidates)
                return f"{sel['protocol']}://{sel['address']}"

    def report_failure(self, proxy_url: str, target_url: Optional[str] = None):
        """汇报代理请求失败，降低评分并触发熔断"""
        if not proxy_url:
            return
        domain = urlparse(target_url).netloc if target_url else None
        clean_url = proxy_url.split("://")[-1].split("@")[-1]

        with self._lock:
            for p in self._proxies:
                if p.get("address") == clean_url or f"{p.get('protocol')}://{p.get('address')}" == proxy_url:
                    p["fail_count"] = p.get("fail_count", 0) + 1
                    p["score"] = p.get("score", 0.0) - 2.5
                    if domain and isinstance(p.get("valid_targets"), set):
                        p["valid_targets"].discard(domain)
                    if p.get("fail_count", 0) >= 2 or p.get("score", 0.0) <= -3.0:
                        if p in self._working_proxies:
                            self._working_proxies.remove(p)
                    break

    def report_success(self, proxy_url: str, target_url: Optional[str] = None):
        """汇报代理请求成功，提高评分"""
        if not proxy_url:
            return
        domain = urlparse(target_url).netloc if target_url else None
        clean_url = proxy_url.split("://")[-1].split("@")[-1]

        with self._lock:
            for p in self._proxies:
                if p.get("address") == clean_url or f"{p.get('protocol')}://{p.get('address')}" == proxy_url:
                    p["success_count"] = p.get("success_count", 0) + 1
                    p["score"] = min(10.0, p.get("score", 0.0) + 1.0)
                    if domain:
                        if "valid_targets" not in p or not isinstance(p["valid_targets"], set):
                            p["valid_targets"] = set()
                        p["valid_targets"].add(domain)
                    break
