"""模板渲染器模块"""
import re
from typing import Any, Dict, List, Optional, Union

from jinja2 import Environment, Template, meta
from structlog import get_logger

logger = get_logger(__name__)


class TemplateRenderer:
    """模板渲染器
    
    支持Jinja2模板语法和简单变量替换
    """
    
    def __init__(self):
        """初始化渲染器"""
        self.jinja_env = Environment(
            # 安全设置
            autoescape=False,
            # 变量语法
            variable_start_string='{{',
            variable_end_string='}}',
            # 块语法  
            block_start_string='{%',
            block_end_string='%}',
            # 注释语法
            comment_start_string='{#',
            comment_end_string='#}',
        )
        
        # 添加自定义过滤器
        self.jinja_env.filters['quote'] = self._quote_filter
        self.jinja_env.filters['urlencode'] = self._urlencode_filter
        self.jinja_env.filters['default'] = self._default_filter
        
        logger.info("模板渲染器初始化完成")
    
    def render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        """渲染模板字符串
        
        Args:
            template_str: 模板字符串
            context: 渲染上下文
            
        Returns:
            渲染后的字符串
        """
        if not template_str:
            return template_str
        
        try:
            # 检查是否包含Jinja2语法
            if self._has_jinja_syntax(template_str):
                return self._render_jinja_template(template_str, context)
            else:
                return self._render_simple_template(template_str, context)
                
        except Exception as e:
            logger.error("模板渲染失败", 
                        template=template_str,
                        context=context,
                        error=str(e))
            # 返回原始字符串，避免中断执行
            return template_str
    
    def render_workflow_step(self, step_data: Dict[str, Any], 
                           context: Dict[str, Any]) -> Dict[str, Any]:
        """渲染工作流步骤
        
        Args:
            step_data: 步骤数据
            context: 渲染上下文
            
        Returns:
            渲染后的步骤数据
        """
        rendered_step = step_data.copy()
        
        # 需要渲染的字段
        renderable_fields = [
            'url', 'selector', 'xpath', 'value', 'description',
            'key', 'wait_condition'
        ]
        
        for field in renderable_fields:
            if field in rendered_step and rendered_step[field]:
                rendered_step[field] = self.render_template(
                    str(rendered_step[field]), context
                )
        
        # 渲染元数据
        if 'metadata' in rendered_step and rendered_step['metadata']:
            rendered_step['metadata'] = self._render_dict_values(
                rendered_step['metadata'], context
            )
        
        logger.debug("步骤渲染完成", 
                    step_id=rendered_step.get('id'),
                    rendered_fields=renderable_fields)
        
        return rendered_step
    
    def extract_variables(self, template_str: str) -> List[str]:
        """提取模板中的变量名
        
        Args:
            template_str: 模板字符串
            
        Returns:
            变量名列表
        """
        if not template_str:
            return []
        
        variables = set()
        
        try:
            if self._has_jinja_syntax(template_str):
                # 使用Jinja2解析
                ast = self.jinja_env.parse(template_str)
                jinja_vars = meta.find_undeclared_variables(ast)
                variables.update(jinja_vars)
            
            # 同时检查简单变量语法 ${var}
            simple_vars = re.findall(r'\$\{(\w+)\}', template_str)
            variables.update(simple_vars)
            
        except Exception as e:
            logger.warning("变量提取失败", 
                          template=template_str,
                          error=str(e))
        
        return sorted(list(variables))
    
    def validate_context(self, template_str: str, 
                        context: Dict[str, Any]) -> Dict[str, Any]:
        """验证渲染上下文
        
        Args:
            template_str: 模板字符串
            context: 渲染上下文
            
        Returns:
            验证结果 {valid: bool, missing_vars: List[str], extra_vars: List[str]}
        """
        required_vars = self.extract_variables(template_str)
        provided_vars = set(context.keys())
        required_vars_set = set(required_vars)
        
        missing_vars = list(required_vars_set - provided_vars)
        extra_vars = list(provided_vars - required_vars_set)
        
        return {
            'valid': len(missing_vars) == 0,
            'missing_vars': missing_vars,
            'extra_vars': extra_vars,
            'required_vars': required_vars
        }
    
    def _has_jinja_syntax(self, template_str: str) -> bool:
        """检查是否包含Jinja2语法"""
        jinja_patterns = [
            r'\{\{.*?\}\}',  # 变量 {{ var }}
            r'\{%.*?%\}',    # 块 {% block %}
            r'\{#.*?#\}',    # 注释 {# comment #}
        ]
        
        for pattern in jinja_patterns:
            if re.search(pattern, template_str):
                return True
        return False
    
    def _render_jinja_template(self, template_str: str, 
                              context: Dict[str, Any]) -> str:
        """使用Jinja2渲染模板"""
        template = self.jinja_env.from_string(template_str)
        return template.render(**context)
    
    def _render_simple_template(self, template_str: str, 
                               context: Dict[str, Any]) -> str:
        """使用简单变量替换渲染模板"""
        result = template_str
        
        # 替换 ${var} 格式的变量
        def replace_var(match):
            var_name = match.group(1)
            return str(context.get(var_name, match.group(0)))
        
        result = re.sub(r'\$\{(\w+)\}', replace_var, result)
        
        return result
    
    def _render_dict_values(self, data: Dict[str, Any], 
                           context: Dict[str, Any]) -> Dict[str, Any]:
        """递归渲染字典值"""
        result = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.render_template(value, context)
            elif isinstance(value, dict):
                result[key] = self._render_dict_values(value, context)
            elif isinstance(value, list):
                result[key] = [
                    self.render_template(item, context) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        
        return result
    
    def _quote_filter(self, value: Any) -> str:
        """引号过滤器"""
        return f'"{value}"'
    
    def _urlencode_filter(self, value: Any) -> str:
        """URL编码过滤器"""
        import urllib.parse
        return urllib.parse.quote(str(value))
    
    def _default_filter(self, value: Any, default_value: Any = "") -> Any:
        """默认值过滤器"""
        return value if value is not None else default_value


class ContextManager:
    """上下文管理器
    
    管理执行上下文和变量
    """
    
    def __init__(self):
        """初始化上下文管理器"""
        self._context = {}
        self._variable_history = []
        
        logger.info("上下文管理器初始化完成")
    
    def set_variable(self, name: str, value: Any, 
                    source: str = "manual") -> None:
        """设置变量
        
        Args:
            name: 变量名
            value: 变量值
            source: 变量来源
        """
        old_value = self._context.get(name)
        self._context[name] = value
        
        # 记录变量历史
        self._variable_history.append({
            'name': name,
            'old_value': old_value,
            'new_value': value,
            'source': source,
            'timestamp': str(datetime.now())
        })
        
        logger.debug("变量已设置", 
                    name=name,
                    value=value,
                    source=source)
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """获取变量值"""
        return self._context.get(name, default)
    
    def update_context(self, context: Dict[str, Any], 
                      source: str = "batch") -> None:
        """批量更新上下文"""
        for name, value in context.items():
            self.set_variable(name, value, source)
    
    def get_context(self) -> Dict[str, Any]:
        """获取完整上下文"""
        return self._context.copy()
    
    def clear_context(self) -> None:
        """清空上下文"""
        self._context.clear()
        self._variable_history.clear()
        logger.info("上下文已清空")
    
    def get_variable_history(self) -> List[Dict[str, Any]]:
        """获取变量历史"""
        return self._variable_history.copy()
    
    def extract_from_page(self, page_data: Dict[str, Any], 
                         extraction_rules: Dict[str, str]) -> Dict[str, Any]:
        """从页面数据中提取变量
        
        Args:
            page_data: 页面数据
            extraction_rules: 提取规则 {var_name: extraction_expression}
            
        Returns:
            提取的变量字典
        """
        extracted = {}
        
        for var_name, rule in extraction_rules.items():
            try:
                # 这里可以实现更复杂的提取逻辑
                # 目前简单实现
                if rule in page_data:
                    extracted[var_name] = page_data[rule]
                    self.set_variable(var_name, extracted[var_name], "extraction")
                
            except Exception as e:
                logger.warning("变量提取失败",
                              var_name=var_name,
                              rule=rule,
                              error=str(e))
        
        return extracted


# 全局渲染器实例
renderer = TemplateRenderer()
context_manager = ContextManager()

# 导入datetime用于历史记录
from datetime import datetime
