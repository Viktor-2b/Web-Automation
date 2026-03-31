import os
import requests
from bs4 import BeautifulSoup
import time

# --- 配置 ---
# 目标网站的基础 URL
BASE_URL = "https://exploit.education"
# Protostar 题目列表页
PROTOSTAR_URL = f"{BASE_URL}/protostar/"
# 保存源码的本地目录
SAVE_DIR = "/outputs/protostar_source_codes"


# --- 主爬虫逻辑 ---

def get_challenge_links():
    """从 Protostar 主页获取所有题目的链接"""
    print(f"[*] Fetching challenge list from {PROTOSTAR_URL}...")
    try:
        response = requests.get(PROTOSTAR_URL)
        response.raise_for_status()  # 如果请求失败则抛出异常

        soup = BeautifulSoup(response.text, 'html.parser')

        # 寻找所有指向题目的 <a> 标签
        # 网站结构：<div class="col-md-3">...<a href="/protostar/stack-one/">...</a>...</div>
        challenge_links = []
        # find_all 会返回一个 list
        for a_tag in soup.find_all('a', href=True):
            if a_tag['href'].startswith('/protostar/stack-') or \
                    a_tag['href'].startswith('/protostar/heap-') or \
                    a_tag['href'].startswith('/protostar/format-') or \
                    a_tag['href'].startswith('/protostar/net-'):
                challenge_links.append(BASE_URL + a_tag['href'])

        print(f"[+] Found {len(challenge_links)} challenges.")
        return challenge_links

    except requests.exceptions.RequestException as e:
        print(f"[!] Error fetching challenge list: {e}")
        return []


def get_source_code(challenge_url):
    """从单个题目页面抓取源代码"""
    print(f"    -> Parsing {challenge_url} for source code...")
    try:
        response = requests.get(challenge_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # 寻找包含源代码的 <pre><code> 标签
        # 网站结构：<pre><code class="language-c">...source code...</code></pre>
        code_block = soup.find('pre')
        if code_block:
            source_code = code_block.get_text()
            return source_code
        else:
            print(f"    [!] Warning: No <pre> code block found on {challenge_url}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"    [!] Error fetching source code from {challenge_url}: {e}")
        return None


def save_code_to_file(challenge_url, source_code):
    """将源代码保存到本地文件"""
    # 从 URL 中提取文件名，例如 "stack-one"
    challenge_name = challenge_url.strip('/').split('/')[-1]
    # 将 "stack-one" 转换为 "stack1.c"
    filename = challenge_name.replace('-', '') + ".c"

    # 确保保存目录存在
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
        print(f"[*] Created directory: {SAVE_DIR}")

    file_path = os.path.join(SAVE_DIR, filename)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(source_code)
    print(f"    [+] Saved source code to {file_path}")


# --- 程序入口 ---
if __name__ == "__main__":
    print("--- Protostar Source Code Scraper ---")

    links = get_challenge_links()

    if links:
        total = len(links)
        for i, link in enumerate(links):
            print(f"\n[*] Processing challenge {i + 1}/{total}...")
            code = get_source_code(link)
            if code:
                save_code_to_file(link, code)
            # 友好爬取，每次请求之间暂停一小段时间
            time.sleep(1)

    print("\n--- Scraper finished. ---")