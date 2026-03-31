import rookiepy
import requests


def get_browser_cookies(domain="sjtu.edu.cn"):
    """
    使用 rookiepy 自动从本地 Edge 浏览器读取指定域名的 Cookie
    """
    print("🍪 正在尝试使用 rookiepy 提取 Edge Cookie...")
    try:
        raw_cookies = rookiepy.edge([domain])

        if not raw_cookies:
            print("⚠️ 未找到该域名的 Cookie，请确认你已经在 Edge 中登录了 Canvas。")
            return None, None

        cookie_dict = {cookie['name']: cookie['value'] for cookie in raw_cookies}

        # 测试提取到的 Cookie 是否有效
        test_url = "https://oc.sjtu.edu.cn/api/v1/users/self"
        response = requests.get(test_url, cookies=cookie_dict, timeout=10)

        if response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''):
            print(f"✅ Cookie 提取成功！当前登录用户: {response.json().get('name')}")
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            return cookie_str, cookie_dict
        else:
            print(f"⚠️ Cookie 可能已过期。状态码: {response.status_code}")
            return None, None

    except PermissionError:
        print("❌ 权限被拒绝！请确保彻底关闭了 Edge 浏览器，然后再试。")
        return None, None
    except Exception as e:
        print(f"❌ 提取 Cookie 失败: {e}")
        return None, None

