"""
日志工具模块
提供带有颜色和格式化时间戳的控制台与文件日志输出
"""
import logging
import sys
import os

def setup_logger(name: str = "proxy_test", log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """配置并返回日志记录器"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    class ColorFormatter(logging.Formatter):
        COLOR_MAP = {
            logging.DEBUG: "[36m",    # Cyan
            logging.INFO: "[32m",     # Green
            logging.WARNING: "[33m",  # Yellow
            logging.ERROR: "[31m",    # Red
            logging.CRITICAL: "[35m", # Magenta
        }
        RESET = "[0m"

        def format(self, record):
            color = self.COLOR_MAP.get(record.levelno, "")
            level_name = f"{color}{record.levelname:<7}{self.RESET}" if color else f"{record.levelname:<7}"
            record_copy = logging.makeLogRecord(record.__dict__)
            record_copy.levelname = level_name
            return super().format(record_copy)

    formatter = ColorFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        plain_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(plain_formatter)
        logger.addHandler(file_handler)

    return logger

def get_logger(name: str = "proxy_test") -> logging.Logger:
    """获取默认日志记录器"""
    return logging.getLogger(name) if logging.getLogger(name).handlers else setup_logger(name)
