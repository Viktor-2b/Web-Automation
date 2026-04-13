import time
from selenium import webdriver

# 目标网址
TARGET_URL = "https://yjsxk.sjtu.edu.cn/yjsxkapp/sys/xsxkapp/course.html"
# 登录网址
BASE_URL = "https://yjsxk.sjtu.edu.cn/yjsxkapp/sys/xsxkapp/index.html"
# Cookie字符串
RAW_COOKIE = 0
# 关键词
KEY_WORD = "自然语言理解"


def login():
    # 配置浏览器驱动 (以Chrome为例)
    options = webdriver.ChromeOptions()
    # 实际使用中可能需要配置用户数据目录以复用登录状态
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # 启动浏览器
    driver = webdriver.Chrome(options=options)

    try:
        # 必须先访问一次该域名的页面，Selenium 才能设置 Cookie
        driver.get(BASE_URL)
        driver.delete_all_cookies() # 清除cookie
        # 解析 Cookie 字符串
        for item in RAW_COOKIE.split(';'):
            item = item.strip()
            if not item: continue
            if '=' in item:
                name, value = item.split('=', 1)
                # 构造 Cookie 字典
                cookie_dict = {
                    'name': name,
                    'value': value,
                    'domain': 'yjsxk.sjtu.edu.cn',  # 显式指定域名
                    'path': '/'
                }
                driver.add_cookie(cookie_dict)

        driver.get(TARGET_URL)
        time.sleep(1)  # 等待服务器验证 Cookie
    except Exception:
        driver.get(BASE_URL)
        time.sleep(1)

