#!/usr/bin/env python3
"""Web UI启动脚本"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入并启动Web应用
from src.web.app import app
import uvicorn

if __name__ == "__main__":
    print("启动Browser-Use-Playwright Web UI")
    print("地址: http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000) 