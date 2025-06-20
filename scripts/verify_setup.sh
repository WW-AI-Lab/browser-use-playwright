#!/bin/bash
set -e

echo "🔍 验证项目环境设置..."

# 检查Python版本
echo "检查Python版本..."
python --version

# 检查虚拟环境
echo "检查虚拟环境..."
which python

# 检查核心依赖
echo "检查核心依赖..."
python -c "import browser_use; print('✅ browser-use 已安装')"
python -c "import playwright; print('✅ playwright 已安装')"
python -c "import jinja2; print('✅ jinja2 已安装')"

# 检查项目结构
echo "检查项目结构..."
python scripts/test_setup.py

# 测试CLI命令
echo "测试CLI命令..."
python -m src.cli.main version

echo "🎉 环境验证完成!" 