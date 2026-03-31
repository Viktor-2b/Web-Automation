# ==========================================
# ⚙️ 全局爬虫配置中心
# ==========================================

# 统一的 User-Agent伪装，所有爬虫脚本都从这里导入
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TARGET_VIDEO_URL = "https://oc.sjtu.edu.cn/courses/90616/external_tools/8329?display=borderless"

# 本地状态文件路径
ENV_FILE = ".env"
STATE_FILE = "state.json"
CREDENTIALS_FILE = "credentials.json"