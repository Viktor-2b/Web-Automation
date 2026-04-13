import os
import ddddocr
import requests

s = requests.session()  # 保持会话，使用s代表本次访问的统一用户身份
ocr = ddddocr.DdddOcr  # 调用解析验证码方法


def get_code():  # 解析验证码
    code_url = "https://ctf.bugku.com/captcha.html0.5735172580060957"  # 对应General中的Request URL
    head = {  # 模拟请求的头部信息，对应Request Headers中的必要项目
        # 伪装成谷歌浏览器
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        # 跳转来的网址
        "referer": "https://ctf.bugku.com/login",
        # 请求内容
        "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    }
    img = s.get(code_url)  # 根据url获得图片，get对应Request Method的方法
    # 以二进制方式将验证码图片写入文件
    with open("code.png", "wb") as f:
        f.write(img.content)
        f.close()
    # 以二进制方式打开图片
    with open("code.png", "rb") as f:
        img_code = f.read()
        f.close()
    os.remove("code.png")  # 删除临时文件
    code = ocr.classification(img_code)  # 解析验证码
    return code
