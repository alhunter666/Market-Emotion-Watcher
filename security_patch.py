import os
import sys
import re
import logging
from dotenv import load_dotenv

# 预先加载本地隔离的环境变量
load_dotenv()

class ZeroTrustMaskingFilter(logging.Filter):
    """
    零信任安全过滤器：
    拦截所有日志流，自动匹配包含 KEY、TOKEN、SECRET 字段或长敏感特征的代码，
    将其脱敏动态替换为 ***
    """
    def filter(self, record):
        if isinstance(record.msg, str):
            # 匹配敏感信息并脱敏（不区分大小写）
            pattern = re.compile(r'(key|token|secret|pwd|password)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]+)["\']?', re.IGNORECASE)
            record.msg = pattern.sub(r'\1=***', record.msg)
        return True

class MaskedStdout:
    """
    终端输出重定向外壳：
    拦截一切 sys.stdout.write 行为（包括普通的 print），防止 debug 或 try-except 时明文暴露密钥
    """
    def __init__(self, original_stdout):
        self.stdout = original_stdout
        # 匹配潜在的密钥赋值格式
        self.pattern = re.compile(r'(key|token|secret|pwd|password)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]+)["\']?', re.IGNORECASE)

    def write(self, text):
        # 动态替换
        masked_text = self.pattern.sub(r'\1=***', text)
        self.stdout.write(masked_text)

    def flush(self):
        self.stdout.flush()

def apply_global_security_patch():
    """
    在全局范围内激活零信任防御：
    重定向标准输出并为根日志处理器注入过滤器
    """
    # 1. 拦截标准控制台输出
    sys.stdout = MaskedStdout(sys.stdout)
    
    # 2. 拦截 Python 日志系统
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 确保有处理器
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        root_logger.addHandler(handler)
        
    for handler in root_logger.handlers:
        handler.addFilter(ZeroTrustMaskingFilter())

if __name__ == "__main__":
    # 激活安全补丁
    apply_global_security_patch()
    
    print("====== 零信任安全机制测试 ======")
    # 获取环境变量
    mock_key = os.getenv("MACRO_FRED_API_KEY", "NOT_FOUND")
    
    # 【强制验证】故意打印敏感短语，验证拦截效果
    print(f"正在尝试打印测试密钥: MACRO_FRED_API_KEY='{mock_key}'")
    print("错误测试示例: error_log -> token='secret_token_12345'")
