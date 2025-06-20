#!/usr/bin/env python3
"""
Azure OpenAI配置设置脚本
帮助用户配置Azure OpenAI环境变量
"""

import os
import sys
from pathlib import Path

def check_current_config():
    """检查当前配置"""
    print("🔍 检查当前Azure OpenAI配置...")
    
    config_items = {
        "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY"),
        "AZURE_OPENAI_API_BASE": os.getenv("AZURE_OPENAI_API_BASE"),
        "AZURE_OPENAI_API_VERSION": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        "AZURE_OPENAI_DEPLOYMENT_NAME": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
        "AZURE_OPENAI_MODEL": os.getenv("AZURE_OPENAI_MODEL", "gpt-4o")
    }
    
    all_configured = True
    
    for key, value in config_items.items():
        if key in ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_BASE"]:
            # 必需的配置
            if value:
                print(f"✅ {key}: {'*' * 20}...{value[-10:] if len(value) > 10 else value}")
            else:
                print(f"❌ {key}: 未设置")
                all_configured = False
        else:
            # 可选的配置
            print(f"ℹ️  {key}: {value}")
    
    return all_configured


def create_env_file():
    """创建.env文件模板"""
    env_template = """# Azure OpenAI Configuration
# 请填写您的Azure OpenAI配置信息

# 必需配置
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_API_BASE=https://your-resource.openai.azure.com/

# 可选配置（有默认值）
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_MODEL=gpt-4o

# 其他配置
# AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4-turbo  # 如果使用GPT-4 Turbo
# AZURE_OPENAI_MODEL=gpt-4-turbo  # 如果使用GPT-4 Turbo
"""
    
    env_file = Path(".env")
    
    if env_file.exists():
        print(f"⚠️  .env文件已存在: {env_file.absolute()}")
        response = input("是否覆盖现有文件？(y/N): ").strip().lower()
        if response != 'y':
            print("❌ 操作已取消")
            return False
    
    try:
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_template)
        
        print(f"✅ .env文件已创建: {env_file.absolute()}")
        print("📝 请编辑.env文件，填写您的Azure OpenAI配置信息")
        return True
        
    except Exception as e:
        print(f"❌ 创建.env文件失败: {e}")
        return False


def show_setup_instructions():
    """显示设置说明"""
    print("\n" + "="*60)
    print("📋 Azure OpenAI配置说明")
    print("="*60)
    
    print("""
1. 获取Azure OpenAI配置信息：
   - 登录Azure Portal (https://portal.azure.com)
   - 找到您的Azure OpenAI资源
   - 在"密钥和终结点"页面获取：
     * API密钥 (Key 1 或 Key 2)
     * 终结点 (Endpoint)
   - 在"模型部署"页面查看：
     * 部署名称 (Deployment name)

2. 设置环境变量（推荐方式）：
   export AZURE_OPENAI_API_KEY="your-api-key"
   export AZURE_OPENAI_API_BASE="https://your-resource.openai.azure.com/"
   export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"

3. 或者使用.env文件：
   - 运行此脚本创建.env文件模板
   - 编辑.env文件填写配置信息
   - 项目会自动加载.env文件

4. 验证配置：
   python scripts/test_douban_book_search.py

5. 开始录制测试：
   browser-use-playwright record douban-book
""")


def test_configuration():
    """测试配置"""
    print("\n🧪 测试Azure OpenAI配置...")
    
    try:
        # 添加项目路径
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        sys.path.insert(0, str(project_root / "src"))
        
        from src.core.config import config
        from src.core.recorder import create_azure_openai_llm
        
        # 检查配置
        azure_config = config.recording.browser_use.azure_openai
        
        if not azure_config.is_configured:
            print("❌ Azure OpenAI配置不完整")
            return False
        
        # 尝试创建LLM实例
        llm = create_azure_openai_llm()
        print("✅ Azure OpenAI LLM创建成功")
        
        # 简单测试
        response = llm.invoke("Hello, this is a test message.")
        print("✅ Azure OpenAI连接测试成功")
        print(f"📝 测试响应: {response.content[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置测试失败: {e}")
        return False


def main():
    """主函数"""
    print("🚀 Browser-Use-Playwright - Azure OpenAI配置工具")
    print("="*50)
    
    # 检查当前配置
    is_configured = check_current_config()
    
    if is_configured:
        print("\n✅ 配置完整！")
        
        # 测试配置
        if test_configuration():
            print("\n🎉 配置验证成功！您可以开始使用Browser-Use录制功能了。")
            print("\n💡 运行以下命令开始豆瓣图书搜索测试：")
            print("   browser-use-playwright record douban-book")
        else:
            print("\n⚠️  配置验证失败，请检查配置信息是否正确。")
        
        return
    
    print("\n❌ 配置不完整")
    
    # 询问用户如何配置
    print("\n请选择配置方式：")
    print("1. 设置环境变量（推荐）")
    print("2. 创建.env文件")
    print("3. 查看配置说明")
    print("4. 退出")
    
    while True:
        choice = input("\n请输入选择 (1-4): ").strip()
        
        if choice == "1":
            print("\n📋 请在终端中运行以下命令设置环境变量：")
            print("export AZURE_OPENAI_API_KEY='your-api-key'")
            print("export AZURE_OPENAI_API_BASE='https://your-resource.openai.azure.com/'")
            print("export AZURE_OPENAI_DEPLOYMENT_NAME='gpt-4o'")
            print("\n设置完成后，请重新运行此脚本验证配置。")
            break
            
        elif choice == "2":
            if create_env_file():
                print("\n📝 请编辑.env文件，然后重新运行此脚本验证配置。")
            break
            
        elif choice == "3":
            show_setup_instructions()
            break
            
        elif choice == "4":
            print("👋 再见！")
            break
            
        else:
            print("❌ 无效选择，请输入1-4")


if __name__ == "__main__":
    main() 