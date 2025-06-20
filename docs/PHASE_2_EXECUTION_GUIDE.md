# Phase 2 执行功能测试指南

## 🎯 Phase 2 功能概览

Phase 2 实现了完整的工作流执行功能，包括：

### ✅ 核心功能
- **PlaywrightExecutor**: 使用Playwright执行工作流步骤
- **TemplateRenderer**: 支持Jinja2模板和变量替换
- **TaskManager**: 并发任务调度和监控
- **执行结果模型**: 完整的执行状态跟踪

### ✅ 支持的步骤类型
- `navigate`: 页面导航
- `click`: 元素点击
- `fill`: 表单填写
- `select`: 下拉选择
- `wait`: 等待操作
- `scroll`: 页面滚动
- `hover`: 鼠标悬停
- `press_key`: 按键操作
- `screenshot`: 截图保存
- `extract`: 数据提取
- `custom`: 自定义操作

### ✅ 高级特性
- 变量渲染和模板支持
- 并发执行控制
- Chrome Profile复用
- 错误处理和重试
- 详细执行报告

## 🚀 快速测试

### 1. 单个工作流执行

```bash
# 执行已录制的豆瓣工作流
./browser-use-playwright run douban_book_search_architecture_clean_code \
  --vars '{"search_query": "Python编程"}' \
  --headless \
  --timeout 30

# 使用变量文件执行
echo '{"search_query": "机器学习"}' > test_vars.json
./browser-use-playwright run douban_book_search_architecture_clean_code \
  --vars-file test_vars.json \
  --output result.json
```

### 2. 批量执行

```bash
# 批量执行多个搜索任务
./browser-use-playwright batch douban_book_search_architecture_clean_code \
  examples/batch_data.json \
  --concurrent 3 \
  --output-dir batch_results/
```

### 3. 任务监控

```bash
# 查看正在运行的任务
./browser-use-playwright tasks
```

### 4. 功能测试脚本

```bash
# 运行完整的执行功能测试
python scripts/test_execution.py
```

## 📊 CLI命令详解

### `browser-use-playwright run` - 执行工作流

```
Usage: browser-use-playwright run [OPTIONS] WORKFLOW_NAME

Arguments:
  workflow_name  工作流名称 [required]

Options:
  --vars -v          TEXT  输入变量JSON字符串
  --vars-file -f     PATH  输入变量JSON文件
  --headless              无头模式运行
  --timeout -t       INT   超时时间(秒) [default: 30]
  --output -o        PATH  结果输出文件
  --progress/--no-progress 显示进度条 [default: progress]
```

### `browser-use-playwright batch` - 批量执行

```
Usage: browser-use-playwright batch [OPTIONS] WORKFLOW_NAME DATA_FILE

Arguments:
  workflow_name  工作流名称 [required]
  data_file      批量数据文件(JSON) [required]

Options:
  --concurrent -c    INT   并发数量 [default: 5]
  --headless/--no-headless 无头模式运行 [default: headless]
  --timeout -t       INT   超时时间(秒) [default: 30]
  --output-dir -o    PATH  结果输出目录
  --continue-on-error/--stop-on-error 遇到错误是否继续
```

### `browser-use-playwright tasks` - 任务监控

```
Usage: browser-use-playwright tasks

显示当前正在运行的任务列表
```

## 🔧 变量和模板

### 变量格式

支持两种变量语法：

```json
{
  "search_query": "Python编程",
  "target_url": "https://www.douban.com",
  "wait_time": 3000
}
```

### 模板语法

**Jinja2语法:**
```
{{ variable_name }}
{{ variable_name | default("默认值") }}
{{ variable_name | quote }}
{{ variable_name | urlencode }}
```

**简单语法:**
```
${variable_name}
```

### 使用示例

工作流步骤中的模板：
```json
{
  "type": "navigate",
  "url": "{{ target_url }}/search?q={{ search_query | urlencode }}"
}
```

## 📈 执行结果

### 单个执行结果

```json
{
  "workflow_name": "douban_book_search_architecture_clean_code",
  "execution_id": "exec_12345678",
  "status": "success",
  "duration": 15.23,
  "success_rate": 1.0,
  "step_results": [...],
  "input_variables": {...},
  "output_variables": {...}
}
```

### 批量执行结果

```json
{
  "batch_id": "batch_87654321",
  "workflow_name": "douban_book_search_architecture_clean_code",
  "status": "success",
  "total_executions": 5,
  "successful_executions": 4,
  "failed_executions": 1,
  "success_rate": 0.8,
  "execution_results": [...]
}
```

## 🐛 常见问题

### 1. 选择器超时
**问题**: `Page.click: Timeout exceeded`
**解决**: 
- 检查选择器是否正确
- 增加超时时间
- 使用更稳定的选择器

### 2. 变量渲染失败
**问题**: 模板变量未替换
**解决**:
- 检查变量名是否正确
- 确认变量已在输入中提供
- 验证模板语法

### 3. 并发执行冲突
**问题**: 批量执行时浏览器实例冲突
**解决**:
- 降低并发数量
- 使用无头模式
- 确保Chrome Profile目录权限

## 🎉 Phase 2 完成状态

✅ **已完成的功能**:
- Playwright执行器实现
- 模板渲染系统
- 并发执行管理
- CLI命令集成
- 错误处理和日志
- 执行结果跟踪

✅ **测试验证**:
- 单个工作流执行 ✓
- 变量渲染功能 ✓
- 批量执行功能 ✓
- 错误处理机制 ✓
- CLI命令接口 ✓

🎯 **下一步**: Phase 3 - Browser-Use自愈功能实现

---

*Phase 2 执行功能已完全实现并通过测试验证！* 