"""配置管理模块"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field

# 尝试加载python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()  # 自动加载.env文件
except ImportError:
    pass  # 如果没有安装python-dotenv，继续使用环境变量


class AppConfig(BaseModel):
    """应用基础配置"""
    name: str = "browser-use-playwright"
    version: str = "1.0.0"
    debug: bool = False


class AzureOpenAIConfig(BaseModel):
    """Azure OpenAI配置"""
    api_key: Optional[str] = Field(default=None, description="Azure OpenAI API密钥")
    api_base: Optional[str] = Field(default=None, description="Azure OpenAI API基础URL")
    api_version: str = Field(default="2024-02-15-preview", description="API版本")
    deployment_name: str = Field(default="gpt-4o", description="部署名称")
    model: str = Field(default="gpt-4o", description="模型名称")

    @property
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.api_key and self.api_base)


class BrowserUseConfig(BaseModel):
    """Browser-Use配置"""
    headless: bool = False
    timeout: int = 30
    viewport_width: int = 1280
    viewport_height: int = 720
    user_data_dir: str = "./chrome-profiles/"
    azure_openai: AzureOpenAIConfig = Field(default_factory=AzureOpenAIConfig)


class RecordingConfig(BaseModel):
    """录制配置"""
    browser_use: BrowserUseConfig = Field(default_factory=BrowserUseConfig)
    output_dir: str = "./workflows/"
    auto_cleanup: bool = True


class PlaywrightConfig(BaseModel):
    """Playwright配置"""
    browser: str = "chromium"
    headless: bool = False
    timeout: int = 30
    user_data_dir: str = "./chrome-profiles/"
    use_local_chrome: bool = True
    preserve_user_data: bool = True
    use_system_chrome_profile: bool = True


class ExecutionConfig(BaseModel):
    """执行配置"""
    playwright: PlaywrightConfig = Field(default_factory=PlaywrightConfig)
    concurrent_limit: int = 10
    retry_count: int = 3


class HealingConfig(BaseModel):
    """自愈配置"""
    browser_use: BrowserUseConfig = Field(default_factory=BrowserUseConfig)
    max_attempts: int = 3
    auto_save: bool = True
    backup_original: bool = True


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    format: str = "structured"
    file: str = "./logs/browser-use-playwright.log"
    rotation: str = "daily"


class Config(BaseModel):
    """主配置类"""
    app: AppConfig = Field(default_factory=AppConfig)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    healing: HealingConfig = Field(default_factory=HealingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def load_from_file(cls, config_path: str = "config.yml") -> "Config":
        """从文件加载配置"""
        config_file = Path(config_path)
        if not config_file.exists():
            # 如果配置文件不存在，返回默认配置
            return cls()
        
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        
        return cls(**config_data)

    @classmethod
    def load_from_env(cls) -> "Config":
        """从环境变量加载配置"""
        config = cls()
        
        # 从环境变量加载Azure OpenAI配置
        azure_config = config.recording.browser_use.azure_openai
        azure_config.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_config.api_base = os.getenv("AZURE_OPENAI_API_BASE") 
        azure_config.api_version = os.getenv("AZURE_OPENAI_API_VERSION", azure_config.api_version)
        azure_config.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", azure_config.deployment_name)
        azure_config.model = os.getenv("AZURE_OPENAI_MODEL", azure_config.model)
        
        # 同时为healing配置设置Azure OpenAI
        healing_azure_config = config.healing.browser_use.azure_openai
        healing_azure_config.api_key = azure_config.api_key
        healing_azure_config.api_base = azure_config.api_base
        healing_azure_config.api_version = azure_config.api_version
        healing_azure_config.deployment_name = azure_config.deployment_name
        healing_azure_config.model = azure_config.model
        
        return config


# 全局配置实例
config = Config.load_from_env()
