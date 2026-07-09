import time
from playwright.sync_api import sync_playwright

# 存放你登录状态的文件夹（第一次登录后，以后免扫码免密）
USER_DATA_DIR = "./gemini_profile"


def chat_with_gemini(prompt: str):
    with sync_playwright() as p:
        # 启动 Chrome，headless=False 代表显示浏览器界面（方便你第一次扫码登录和观察）
        # 等跑通后，改成 headless=True 就可以在后台静默全速运行了！
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            channel="chrome"  # 使用你系统自带的 Chrome
        )

        page = browser.new_page()
        page.goto("https://gemini.google.com/app")

        # 检查是否需要登录
        print("⏳ 正在等待页面加载...")
        # 等待输入框出现，如果超时说明可能还没登录
        try:
            # 寻找聊天输入框 (Gemini 的富文本输入框)
            chat_input = page.wait_for_selector('div.ql-editor[contenteditable="true"]', timeout=15000)
            print("✅ 成功进入聊天界面！")
        except Exception:
            print("⚠️ 找不到输入框。如果是第一次运行，请在弹出的浏览器里手动登录你的 Google 账号！")
            print("登录完成后，请关闭程序重新运行。")
            time.sleep(60)  # 给你一分钟时间登录
            browser.close()
            return

        # 1. 填入你的作业批改提示词
        print(f"🤖 正在输入 Prompt: {prompt[:20]}...")
        chat_input.fill(prompt)

        # 2. 点击发送按钮
        page.locator('button[aria-label="Send message"]').click()

        # 3. 等待 Gemini 回复
        print("⏳ 等待 Gemini 思考和输出...")

        # 监控回复加载完成的标志（Gemini 生成时会有 loading 动画，消失代表生成完毕）
        # 这里我们简单粗暴一点，等待最新一条回复的气泡出现
        page.wait_for_selector('message-content', state='visible', timeout=30000)

        # 等待发送按钮恢复可点击状态（表示生成彻底结束）
        page.wait_for_selector('button[aria-label="Send message"]:not([disabled])', timeout=60000)

        # 4. 获取最后一条回复的文本
        responses = page.query_selector_all('message-content')
        latest_response = responses[-1].inner_text()

        print("\n🎉 Gemini 的回复如下：")
        print("-" * 50)
        print(latest_response)
        print("-" * 50)

        browser.close()
        return latest_response


if __name__ == "__main__":
    test_prompt = "你好！请扮演一位严厉的高校助教，回复我一句测试的话。第一行用方括号写上[测试成功]。"
    chat_with_gemini(test_prompt)