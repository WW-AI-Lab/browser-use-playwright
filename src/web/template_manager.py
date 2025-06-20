"""模板管理器 - 负责管理HTML模板文件目录"""
from pathlib import Path


class TemplateManager:
    """模板管理器 - 简化版本，只负责目录管理"""
    
    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self.templates_dir.mkdir(exist_ok=True)
    
    def ensure_directories(self):
        """确保必要的目录存在"""
        # 确保模板目录存在
        self.templates_dir.mkdir(exist_ok=True)
        
        # 确保静态文件目录存在
        static_dir = self.templates_dir.parent / "static"
        static_dir.mkdir(exist_ok=True)
        
        # 确保CSS和JS子目录存在
        (static_dir / "css").mkdir(exist_ok=True)
        (static_dir / "js").mkdir(exist_ok=True)


def get_template_manager() -> TemplateManager:
    """获取模板管理器实例"""
    templates_dir = Path(__file__).parent / "templates"
    return TemplateManager(templates_dir) 