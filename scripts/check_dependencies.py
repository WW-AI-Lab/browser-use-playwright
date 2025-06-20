#!/usr/bin/env python3
"""
依赖检查和安装脚本
检查项目所需的依赖是否已安装
"""

import subprocess
import sys
from pathlib import Path


def check_python_version():
    """检查Python版本"""
    print("🐍 检查Python版本...")
    
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} (需要Python 3.11+)")
        return False


def check_virtual_env():
    """检查是否在虚拟环境中"""
    print("🔧 检查虚拟环境...")
    
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ 在虚拟环境中")
        return True
    else:
        print("⚠️  不在虚拟环境中（推荐使用虚拟环境）")
        return False


def check_package(package_name, import_name=None):
    """检查单个包是否安装"""
    if import_name is None:
        import_name = package_name.replace('-', '_')
    
    try:
        __import__(import_name)
        print(f"✅ {package_name}")
        return True
    except ImportError:
        print(f"❌ {package_name}")
        return False


def check_core_dependencies():
    """检查核心依赖"""
    print("\n📦 检查核心依赖...")
    
    dependencies = [
        ("browser-use", "browser_use"),
        ("playwright", "playwright"),
        ("langchain-openai", "langchain_openai"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("typer", "typer"),
        ("pydantic", "pydantic"),
        ("structlog", "structlog"),
        ("jinja2", "jinja2"),
        ("pyyaml", "yaml"),
        ("python-dotenv", "dotenv"),
    ]
    
    missing = []
    for package, import_name in dependencies:
        if not check_package(package, import_name):
            missing.append(package)
    
    return missing


def install_missing_packages(missing_packages):
    """安装缺失的包"""
    if not missing_packages:
        return True
    
    print(f"\n🔧 发现 {len(missing_packages)} 个缺失的依赖包")
    print("缺失的包:", ", ".join(missing_packages))
    
    response = input("\n是否自动安装缺失的依赖？(y/N): ").strip().lower()
    if response != 'y':
        print("❌ 跳过安装")
        return False
    
    try:
        print("\n📥 安装缺失的依赖...")
        
        # 使用pip安装
        cmd = [sys.executable, "-m", "pip", "install"] + missing_packages
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        print("✅ 依赖安装完成")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False


def check_playwright_browsers():
    """检查Playwright浏览器"""
    print("\n🌐 检查Playwright浏览器...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if "chromium" in result.stdout.lower():
            print("⚠️  Playwright浏览器未安装")
            
            response = input("是否安装Playwright浏览器？(y/N): ").strip().lower()
            if response == 'y':
                print("📥 安装Playwright浏览器...")
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                print("✅ Playwright浏览器安装完成")
                return True
            else:
                print("❌ 跳过Playwright浏览器安装")
                return False
        else:
            print("✅ Playwright浏览器已安装")
            return True
            
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"❌ 检查Playwright浏览器失败: {e}")
        return False


def install_from_requirements():
    """从requirements.txt安装依赖"""
    requirements_file = Path("requirements.txt")
    
    if not requirements_file.exists():
        print("❌ requirements.txt文件不存在")
        return False
    
    print("\n📋 从requirements.txt安装依赖...")
    
    try:
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
        result = subprocess.run(cmd, check=True)
        print("✅ requirements.txt安装完成")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装失败: {e}")
        return False


def main():
    """主函数"""
    print("🚀 Browser-Use-Playwright - 依赖检查工具")
    print("="*50)
    
    # 检查Python版本
    if not check_python_version():
        print("\n❌ Python版本不符合要求，请升级到Python 3.11+")
        sys.exit(1)
    
    # 检查虚拟环境
    check_virtual_env()
    
    # 检查核心依赖
    missing = check_core_dependencies()
    
    if missing:
        print(f"\n⚠️  发现 {len(missing)} 个缺失的依赖")
        
        # 询问安装方式
        print("\n请选择安装方式：")
        print("1. 从requirements.txt安装所有依赖（推荐）")
        print("2. 只安装缺失的依赖")
        print("3. 跳过安装")
        
        choice = input("\n请输入选择 (1-3): ").strip()
        
        if choice == "1":
            if install_from_requirements():
                print("\n✅ 依赖安装完成")
            else:
                print("\n❌ 依赖安装失败")
                sys.exit(1)
                
        elif choice == "2":
            if install_missing_packages(missing):
                print("\n✅ 缺失依赖安装完成")
            else:
                print("\n❌ 依赖安装失败")
                sys.exit(1)
                
        else:
            print("\n⚠️  跳过依赖安装")
            print("请手动安装缺失的依赖:")
            print(f"pip install {' '.join(missing)}")
            sys.exit(1)
    
    else:
        print("\n✅ 所有核心依赖已安装")
    
    # 检查Playwright浏览器
    if not check_playwright_browsers():
        print("\n⚠️  Playwright浏览器检查失败")
        print("请手动安装: playwright install chromium")
    
    print("\n🎉 依赖检查完成！")
    print("\n💡 下一步：")
    print("1. 配置Azure OpenAI: python scripts/setup_azure_openai.py")
    print("2. 开始录制测试: browser-use-playwright record douban-book")


if __name__ == "__main__":
    main() 