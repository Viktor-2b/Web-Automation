import json
import os
import re
import time

import cv2
import easyocr
import numpy as np
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from utils.config import CREDENTIALS_FILE, STATE_FILE, TARGET_VIDEO_URL

# cookie和token手动更新办法：Network->Fetch/XHR->任意请求->Headers->Request Headers
# course_id手动更新办法：Network->Fetch/XHR->findVodVideoList->Payload


# 初始化环境变量
load_dotenv()
USERNAME = os.getenv("SJTU_USERNAME")
PASSWORD = os.getenv("SJTU_PASSWORD")
# 将 reader 放在外层，避免每次调用函数时都重新加载深度学习模型
reader = easyocr.Reader(['en'])


def update_credentials_json(cookie, token, hash_id, short_id=None):
    """将凭证更新到结构化的 JSON 文件中"""
    data = {"global_cookie": "", "courses": {}}
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                pass

    data["global_cookie"] = cookie
    if short_id:
        if "courses" not in data:
            data["courses"] = {}
        data["courses"][short_id] = {"token": token, "hash_id": hash_id}

    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=4)
    print(f"\n✅ 凭证已结构化更新至 {CREDENTIALS_FILE}")


def auto_sniff_credentials(target_url=TARGET_VIDEO_URL, short_id=None):
    print("🚀 正在启动自动化浏览器...")

    with sync_playwright() as p:
        # 启动 Chromium 浏览器，headless=False 意味着显示实体浏览器界面
        browser = p.chromium.launch(headless=False)
        # 检查是否有历史登录记录
        if os.path.exists(STATE_FILE):
            print("🍪 发现本地保存的登录状态，尝试免密登录...")
            context = browser.new_context(storage_state=STATE_FILE)
        else:
            context = browser.new_context()

        page = context.new_page()
        sniffed_data = {"cookie": None, "token": None, "canvas_course_id": None}
        # 监听浏览器的所有底层网络请求，拦截目标接口
        def handle_request(request):
            if "findVodVideoList" in request.url and request.method == "POST":
                print("\n拦截到目标接口: findVodVideoList")
                # 提取请求头中的 Token
                headers = request.headers
                sniffed_data["token"] = headers.get("token")
                # 提取表单或 JSON 中的核心课程哈希 ID
                post_data = request.post_data
                if post_data:
                    data_dict = json.loads(post_data)
                    if "canvasCourseId" in data_dict:
                        sniffed_data["canvas_course_id"] = data_dict["canvasCourseId"]

        # 将监听器绑定到当前页面
        page.on("request", handle_request)

        print("🌐 正在打开目标链接...")
        page.goto(target_url)

        # 自动化登录逻辑分支 (仅在未登录时触发)
        if "login/canvas" in page.url:
            print("🔒 检测到 Canvas 登录页...")
            try:
                # 点击主页面的登录入口
                login_btn = page.locator("#jaccount")
                login_btn.click(timeout=3000)
                print("📱 正在跳转至 JAccount 登录...")

                # 等待整个页面重定向到 JAccount 域名
                page.wait_for_url(re.compile(r"jaccount\.sjtu\.edu\.cn"), timeout=10000)
                print("🔍 已确认进入 JAccount 登录页面...")

                # 填写账密
                page.locator("#input-login-user").wait_for(timeout=5000)
                print("🤖 正在自动填充账号密码...")
                page.locator("#input-login-user").fill(USERNAME)
                page.locator("#input-login-pass").fill(PASSWORD)

                # 提取验证码
                print("👁️ 正在截取并识别验证码...")
                captcha_element = page.locator("#captcha-img")
                captcha_element.wait_for(state="visible", timeout=5000)
                page.wait_for_timeout(500)  # 给图片渲染一点缓冲时间

                # 0. 截图获取原始二进制数据
                img_bytes = captcha_element.screenshot()
                # 1. 将 bytes 转为 numpy 数组，供 OpenCV 读取
                img_array = np.frombuffer(img_bytes, np.uint8)
                img_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                # 2. 双三次插值放大 2 倍
                img_cv = cv2.resize(img_cv, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                # 3. 转灰度图
                gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                # 4. 自动阈值二值化 (OTSU 算法)，THRESH_BINARY_INV 会把暗的文字变白，亮的背景变黑，因为膨胀操作是针对白色的
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                # 5. 形态学膨胀 (Dilation) - 让文字变粗。2x2 的核对于放大两倍的图刚刚好，不会糊成一团
                kernel = np.ones((2, 2), np.uint8)
                dilated = cv2.dilate(thresh, kernel, iterations=1)
                # 6. 反色。把文字变回黑色，背景变回白色，迎合 OCR 模型的训练习惯
                result = cv2.bitwise_not(dilated)
                # 7. 补充 Padding (四周各加 20 像素的白边)
                result_padded = cv2.copyMakeBorder(result, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255])
                # 将处理完毕的图像编码回 bytes 丢给 OCR
                _, buffer = cv2.imencode('.png', result_padded)
                processed_img_bytes = buffer.tobytes()

                # 深度学习识别
                results = reader.readtext(processed_img_bytes, detail=0)
                captcha_text = "".join(results).replace(" ", "")
                print(f"✅ OCR识别结果: '{captcha_text}'")

                # 提交登录表单
                page.locator("#input-login-captcha").fill(captcha_text)
                page.locator("#submit-password-button").click()
                print("⏳ 登录请求已提交，等待系统跳转与数据拦截...")

            except Exception as e:
                print(f"⚠️ 自动登录流程中断，请在浏览器中手动完成登录。提示: {e}")
                if 'img_bytes' in locals():
                    with open("captcha_error.png", "wb") as f: f.write(img_bytes)
                if 'processed_img_bytes' in locals():
                    with open("captcha_error_enhanced.png", "wb") as f: f.write(processed_img_bytes)
        # 轮询等待器：无论是免密登录还是 OCR 自动登录，都在这里等结果
        timeout = 60
        start_time = time.time()
        while time.time() - start_time < timeout:
            page.wait_for_timeout(1000)
            # 实时从浏览器上下文中提取最新的完整 Cookie，绕过 Headers 被隐藏的问题
            canvas_cookies = context.cookies("https://oc.sjtu.edu.cn")
            video_cookies = context.cookies("https://v.sjtu.edu.cn/jy-application-canvas-sjtu")
            all_target_cookies = canvas_cookies + video_cookies

            c_cookie = "; ".join([f"{c['name']}={c['value']}" for c in all_target_cookies])

            c_token = sniffed_data["token"]
            c_course_id = sniffed_data["canvas_course_id"]

            if c_cookie and c_token and c_course_id:
                print("\n🎉 完美！所有凭证已成功拦截！")
                print(f"🔑 Token: {str(c_token)[:15]}...")
                print(f"🍪 Cookie: {str(c_cookie)[:35]}...")
                print(f"🆔 Course ID: {c_course_id}")

                context.storage_state(path=STATE_FILE)
                print(f"💾 登录状态已保存至 {STATE_FILE}，下次运行将自动免密登录！")

                update_credentials_json(c_cookie, c_token, c_course_id, short_id)
                break
        else:
            print("\n❌ 抓取超时：未能获取到完整凭证。")

        browser.close()


if __name__ == "__main__":
    auto_sniff_credentials(TARGET_VIDEO_URL)