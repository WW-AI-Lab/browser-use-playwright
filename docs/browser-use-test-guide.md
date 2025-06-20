# Browser-Use 录制功能测试指南

本文档介绍如何测试Browser-use-Playwright的Browser-Use录制功能，包括Azure OpenAI配置和豆瓣图书搜索测试。

## 📋 测试概览

### 测试目标
使用Browser-Use录制功能，在豆瓣网站上搜索图书《架构简洁之道》，并获取：
1. 图书的评分
2. 图书的简介/内容简介  
3. 图书的基本信息（作者、出版社等）

### 技术架构
- **录制引擎**: Browser-Use + Azure OpenAI GPT-4o
- **浏览器**: 本地Chrome（显示界面）
- **输出**: JSON格式的工作流文件

## 🚀 快速开始

### 1. 环境检查
```bash
# 检查依赖和Python版本
python scripts/check_dependencies.py

# 如果有缺失依赖，脚本会提示安装
```

### 2. Azure OpenAI配置
```bash
# 运行配置工具
python scripts/setup_azure_openai.py

# 或者手动设置环境变量
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_API_BASE="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"
```

### 3. 开始录制测试
```bash
# 使用CLI命令（推荐）
browser-use-playwright record douban-book

# 或者直接运行测试脚本
python scripts/test_douban_book_search.py
```

## 🔧 详细配置说明

### Azure OpenAI配置要求

| 配置项 | 环境变量 | 说明 | 示例 |
|--------|----------|------|------|
| API密钥 | `AZURE_OPENAI_API_KEY` | 必需 | `abc123...` |
| API端点 | `AZURE_OPENAI_API_BASE` | 必需 | `https://your-resource.openai.azure.com/` |
| API版本 | `AZURE_OPENAI_API_VERSION` | 可选 | `2024-02-15-preview` |
| 部署名称 | `AZURE_OPENAI_DEPLOYMENT_NAME` | 可选 | `gpt-4o` |
| 模型名称 | `AZURE_OPENAI_MODEL` | 可选 | `gpt-4o` |

### 获取Azure OpenAI配置信息

1. **登录Azure Portal**: https://portal.azure.com
2. **找到Azure OpenAI资源**: 搜索并选择您的OpenAI服务
3. **获取密钥和端点**:
   - 点击左侧菜单的"密钥和终结点"
   - 复制"密钥1"或"密钥2"作为API密钥
   - 复制"终结点"作为API基础URL
4. **查看模型部署**:
   - 点击左侧菜单的"模型部署"
   - 查看部署的模型名称（如gpt-4o、gpt-4-turbo等）

## 🎬 录制流程说明

### 1. 录制启动
- 脚本会自动启动Chrome浏览器（非无头模式）
- Browser-Use Agent会接管浏览器控制
- AI会根据任务描述自动执行操作

### 2. 执行步骤
预期的录制步骤：
1. 导航到豆瓣首页 (https://www.douban.com)
2. 定位搜索框
3. 输入"架构简洁之道"
4. 点击搜索或按Enter
5. 在搜索结果中找到对应图书
6. 点击进入图书详情页
7. 提取评分、简介等信息

### 3. 结果输出
录制完成后会生成：
- **工作流文件**: `workflows/douban_book_search_architecture_clean_code.json`
- **步骤列表**: 包含所有录制的操作步骤
- **变量信息**: 可能包含提取的数据变量

## 📁 输出文件结构

### 工作流JSON格式
```json
{
  "name": "douban_book_search_architecture_clean_code",
  "description": "搜索《架构简洁之道》并获取评分和简介",
  "version": "1.0.0",
  "steps": [
    {
      "id": "step_1_abc123",
      "type": "navigate",
      "description": "导航到豆瓣首页",
      "url": "https://www.douban.com"
    },
    {
      "id": "step_2_def456", 
      "type": "fill",
      "description": "输入搜索关键词",
      "selector": "#inp-query",
      "value": "架构简洁之道"
    }
    // ... 更多步骤
  ],
  "variables": {
    "book_rating": {
      "name": "book_rating",
      "type": "string", 
      "description": "图书评分"
    }
    // ... 更多变量
  }
}
```

## 🔍 验证和查看结果

### 查看录制的工作流
```bash
# 列出所有工作流
browser-use-playwright list

# 查看特定工作流详情
browser-use-playwright show douban_book_search_architecture_clean_code

# 启动Web UI查看
browser-use-playwright web
```

### Web UI界面
- 访问: http://localhost:8000
- 功能: 查看、编辑、清理工作流
- 支持: 步骤编辑、变量管理、工作流优化

## 🛠️ 故障排除

### 常见问题

#### 1. Azure OpenAI连接失败
```
❌ Azure OpenAI配置不完整
```
**解决方案**:
- 检查环境变量是否正确设置
- 验证API密钥和端点URL
- 确认模型部署状态

#### 2. 浏览器启动失败
```
❌ 浏览器启动失败
```
**解决方案**:
- 安装Playwright浏览器: `playwright install chromium`
- 检查Chrome是否已安装
- 确认用户数据目录权限

#### 3. 依赖缺失
```
❌ browser-use 未安装
```
**解决方案**:
- 运行依赖检查: `python scripts/check_dependencies.py`
- 安装缺失依赖: `pip install -r requirements.txt`

#### 4. 录制超时
```
❌ Browser-Use录制失败: timeout
```
**解决方案**:
- 检查网络连接
- 增加超时时间配置
- 简化任务描述

### 调试模式
```bash
# 启用调试日志
export Browser-use-Playwright_RPA_DEBUG=true

# 查看详细日志
tail -f logs/browser-use-playwright.log
```

## 📊 预期结果

### 成功标准
- ✅ 浏览器成功启动并显示界面
- ✅ AI成功导航到豆瓣网站
- ✅ 成功搜索并找到《架构简洁之道》
- ✅ 成功提取图书评分和简介信息
- ✅ 生成完整的工作流JSON文件
- ✅ 工作流包含5-10个有效步骤

### 性能指标
- **录制时间**: 预计2-5分钟
- **步骤数量**: 5-10个步骤
- **成功率**: >90%（在正常网络环境下）

## 🔄 后续步骤

录制完成后，可以进行：

1. **工作流优化**:
   ```bash
   browser-use-playwright clean douban_book_search_architecture_clean_code
   ```

2. **执行测试** (Phase 2功能):
   ```bash
   browser-use-playwright run --workflow douban_book_search_architecture_clean_code.json
   ```

3. **自愈测试** (Phase 3功能):
   ```bash
   browser-use-playwright heal --workflow douban_book_search_architecture_clean_code.json
   ```

## 📞 技术支持

如果遇到问题，请：
1. 查看日志文件: `logs/browser-use-playwright.log`
2. 运行诊断脚本: `python scripts/check_dependencies.py`
3. 检查配置: `python scripts/setup_azure_openai.py`
4. 提交Issue到GitHub仓库

---

**注意**: 这是Phase 1的测试功能，主要验证Browser-Use录制能力。Phase 2将实现Playwright执行功能，Phase 3将实现AI自愈功能。 