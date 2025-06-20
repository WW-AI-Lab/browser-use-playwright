"""日志工具模块"""
import logging
import sys
from pathlib import Path
from typing import Any, Dict

import structlog
from rich.console import Console
from rich.logging import RichHandler

from ..core.config import config


def setup_logging() -> structlog.BoundLogger:
    """设置结构化日志"""
    
    # 确保日志目录存在
    log_file = Path(config.logging.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 配置标准logging
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper()),
        format="%(message)s",
        handlers=[
            RichHandler(console=Console(stderr=True), show_time=False),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    
    # 配置structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.dev.ConsoleRenderer() if config.app.debug else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.logging.level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger()


# 全局日志实例
logger = setup_logging()


def get_logger(name: str = None) -> structlog.BoundLogger:
    """获取结构化日志器"""
    if name:
        return structlog.get_logger(name)
    return logger
