#!/usr/bin/env python3
"""创建.env.example文件的脚本"""

env_content = """# Browser-Use LLM配置
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_claude_api_key_here

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=./logs/browser-use-playwright.log

# 浏览器配置
CHROME_EXECUTABLE_PATH=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
CHROME_USER_DATA_DIR=./chrome-profiles/default

# 执行配置
MAX_CONCURRENT_TASKS=10
DEFAULT_TIMEOUT=30
"""

with open('.env.example', 'w', encoding='utf-8') as f:
    f.write(env_content)

print('✅ .env.example 创建成功') 