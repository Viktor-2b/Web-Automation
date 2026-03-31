import os
import re
import io
import time
import json
import shutil
import requests
from PIL import Image
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from utils.config import USER_AGENT, CREDENTIALS_FILE
from utils.get_credentials import auto_sniff_credentials

BASE_SAVE_DIR = "./outputs/course_records"

def load_credentials():
    """读取本地 JSON 缓存的凭证"""
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            try:
                return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                pass
    return {"global_cookie": "", "courses": {}}

def load_fresh_headers():
    """每次调用时都重新读取最新的 .env 文件，防止中途更新后数据过时"""
    load_dotenv(override=True)
    return {
        "User-Agent": USER_AGENT,
        "Cookie": os.getenv("COOKIE"),
        "token": os.getenv("TOKEN")
    }



def get_course_list(headers):
    """请求 Canvas 课程主页，解析 HTML 获取课程列表"""
    url = "https://oc.sjtu.edu.cn/courses"
    print("📡 正在获取你的 Canvas 课程列表...")
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    courses = []

    # 找到所有的课程行
    rows = soup.find_all('tr', class_='course-list-table-row')
    for row in rows:
        # 提取课程 ID
        star_span = row.find('span', attrs={'data-course-id': True})
        if not star_span:
            continue
        course_id = star_span['data-course-id']
        # 提取课程名称
        name_span = row.find('span', class_='name')
        course_name = name_span.text.strip() if name_span else "未知课程"

        # 提取发布状态（防止选择未发布的课程导致出错）
        published_span = row.find('td', class_='course-list-published-column')
        is_published = "是" in published_span.text if published_span else False

        courses.append({
            "id": course_id,
            "name": course_name,
            "published": is_published
        })

    return courses


def cli_select_course(courses):
    """在终端渲染交互式菜单，让用户选择"""
    if not courses:
        print("❌ 未找到任何课程。")
        return None

    print("\n" + "=" * 50)
    print("📚 请选择你要下载的课程：")
    print("=" * 50)

    valid_choices = {}
    for i, course in enumerate(courses, 1):
        status = "" if course['published'] else " [未发布]"
        print(f" {i:2d}. {course['name']}{status}")
        valid_choices[str(i)] = course

    print("=" * 50)

    while True:
        choice = input(f"\n👉 请输入课程编号 (1-{len(courses)}): ").strip()
        if choice in valid_choices:
            selected = valid_choices[choice]
            if not selected['published']:
                print("⚠️ 警告：该课程尚未发布，可能无法获取视频。")
            return selected
        else:
            print("❌ 输入有误，请输入列表中的数字序号。")

def sanitize_filename(filename):
    """过滤掉文件名中的非法字符，防止创建文件失败"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)


def ms_to_time_str(ms):
    """将毫秒转换为 MM:SS 格式"""
    try:
        total_seconds = int(ms) // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    except Exception as e:
        print(e)
        return "00:00"


def fetch_video_list(canvas_course_id, headers):
    """第一步：根据课程的 Canvas ID 获取全学期所有视频的列表"""
    print(f"📡 正在获取课程 '{canvas_course_id}' 的全学期视频列表...")
    url = "https://v.sjtu.edu.cn/jy-application-canvas-sjtu/directOnDemandPlay/findVodVideoList"

    # 该接口使用 application/x-www-form-urlencoded 格式，用 data 参数传递
    payload = {"canvasCourseId": canvas_course_id}
    headers["Content-Type"] = "application/json"
    try:
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        json_data = resp.json()
        # 只要 code 是 "0" 或 "200"，或者 success 字段为 True，都算成功，兼容交大Canvas的0
        if str(json_data.get('code')) not in ['0', '200'] and not json_data.get('success'):
            return None

        video_list = json_data.get('data', {}).get('records', [])
        return video_list
    except Exception as e:
        print(f"❌ 获取视频列表失败: {e}")
        return None


def get_mp4_video(video_info, save_dir, headers):
    """请求视频真实地址，支持多视角(讲台/PPT)直接下载大文件"""
    session_name = sanitize_filename(video_info.get('videoName', '未知节次'))
    video_id = video_info.get('videoId')

    print(f"🎬 正在解析视频真实地址: {session_name}")
    url = "https://v.sjtu.edu.cn/jy-application-canvas-sjtu/directOnDemandPlay/getVodVideoInfos"

    # 使用 files 参数格式构造 multipart/form-data，格式为: "字段名": (文件名, "值")。这里不需要传文件，所以文件名写 None
    multipart_data = {
        "playTypeHls": (None, "true"),
        "isAudit": (None, "true"),
        "id": (None, video_id)
    }

    try:
        req_headers = headers.copy()
        # 必须把它删掉，让 requests 底层自动生成带有 Boundary 的 Content-Type
        if "Content-Type" in req_headers:
            del req_headers["Content-Type"]

        # 发送请求时，使用 files=multipart_data
        resp = requests.post(url, headers=req_headers, files=multipart_data)
        resp.raise_for_status()
        json_resp = resp.json()
        data = json_resp.get('data') or {} # 防御null
        streams = data.get('videoPlayResponseVoList', [])

        if not streams:
            msg = json_resp.get('message')
            print(f"  -> ❌ 未找到视频流数据 (服务器返回: {msg})")
            return

        # 遍历所有视角（通常一个是老师，一个是电脑屏幕）
        for idx, stream in enumerate(streams):
            # 优先获取高清(Hdv)，没有就拿流畅(Fluency)
            mp4_url = stream.get('rtmpUrlHdv') or stream.get('rtmpUrlFluency')
            if not mp4_url:
                continue

            # 如果有多个视角，加个后缀区分，避免文件名冲突
            suffix = f"_视角{idx + 1}" if len(streams) > 1 else ""
            mp4_filepath = os.path.join(save_dir, f"{session_name}{suffix}.mp4")

            # 防重复下载
            if os.path.exists(mp4_filepath):
                print(f"  -> ⏭️ 视频已存在，跳过: {os.path.basename(mp4_filepath)}")
                continue

            print(f"  -> ⬇️ 正在下载视频流 {idx + 1}/{len(streams)} ...")
            # 不要带 Token，不要带复杂的 Cookie，只带浏览器标识和播放页面的来源证明
            cdn_headers = {
                "User-Agent": USER_AGENT,
                "Referer": "https://v.sjtu.edu.cn/"  # 告诉 CDN：我是从交大视频网点进来的
            }

            # 记录开始时间，用于计算网速
            start_time = time.time()

            # 使用 stream=True 流式下载大文件，防止撑爆内存
            with requests.get(mp4_url, headers=cdn_headers, stream=True) as r:
                r.raise_for_status()
                # 获取文件总大小（字节），用来计算进度
                total_size = int(r.headers.get('content-length', 0))
                downloaded_size = 0
                with open(mp4_filepath, 'wb') as f:
                    # 每次拉取 1MB 的数据块写入硬盘
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)

                            elapsed_time = time.time() - start_time
                            # 计算速度 (MB/s)
                            speed = (downloaded_size / 1048576) / elapsed_time if elapsed_time > 0 else 0

                            if total_size > 0:
                                mb_down = downloaded_size / 1048576
                                mb_total = total_size / 1048576
                                percent = (downloaded_size / total_size) * 100
                                # 使用 \r 回到行首，使用 flush=True 强制刷新屏幕
                                print(f"\r     ... 进度: {mb_down:.1f} MB / {mb_total:.1f} MB ({percent:.1f}%) | 速度: {speed:.1f} MB/s",
                                    end="", flush=True)
                            else:
                                mb_down = downloaded_size / 1048576
                                print(f"\r     ... 已下载: {mb_down:.1f} MB | 速度: {speed:.1f} MB/s",
                                      end="",flush=True)

                # 这里的 \n 会把光标推到下一行，保留最后 100% 的进度条记录，并打印成功提示
                print(f"\n  -> ✅ 视频保存成功: {os.path.basename(mp4_filepath)}")

    except Exception as exc:
        print(f"  -> ❌ 视频下载失败: {exc}")

def get_voice_transcript(video_info, save_dir, headers):
    """为单个视频下载语音文本"""
    session_name = sanitize_filename(video_info.get('videoName', '未知节次'))

    # 提前构建最终文件名，用于检查
    text_file_path = os.path.join(save_dir, f"{session_name}.txt")

    # 检查文件是否存在
    if os.path.exists(text_file_path):
        print(f"📄 文件已存在，跳过字幕下载: {session_name}.txt")
        return

    course_id = video_info.get('courId')

    print(f"🎤 正在下载语音字幕: {session_name}")
    url = "https://v.sjtu.edu.cn/jy-application-canvas-sjtu/transfer/translate/detail"
    headers["Content-Type"] = "application/json"
    payload = {"courseId": course_id, "platform": 1}

    try:
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        json_resp = resp.json()
        data = json_resp.get('data') or {} # 防御null
        transcript_list = data.get('afterAssemblyList', [])
        if not transcript_list:
            print("  -> ⚠️ 本节次暂无语音识别数据")
            return
        with open(text_file_path, "w", encoding="utf-8") as f:
            for item in transcript_list:
                start_ms, text = item.get('bg', 0), item.get('res', '')
                if text.strip():
                    f.write(f"[{ms_to_time_str(start_ms)}] {text}\n\n")
        print(f"  -> ✅ 字幕保存成功")
    except Exception as e:
        print(f"  -> ❌ 字幕下载失败: {e}")


def get_ppt_and_make_pdf(video_info, save_dir, headers):
    """为单个视频下载PPT并合成PDF"""
    session_name = sanitize_filename(video_info.get('videoName', '未知节次'))
    # 提前构建最终文件名，用于检查
    pdf_filepath = os.path.join(save_dir, f"{session_name}.pdf")

    # 检查文件是否存在
    if os.path.exists(pdf_filepath):
        print(f"📄 文件已存在，跳过PPT下载: {session_name}.pdf")
        return
    course_id = video_info.get('courId')

    print(f"🖼️ 正在下载并合成PPT: {session_name}")
    url = f"https://v.sjtu.edu.cn/jy-application-canvas-sjtu/directOnDemandPlay/vod-analysis/query-ppt-slice-es?ivsVideoId={course_id}"
    temp_img_dir = os.path.join(save_dir, f".temp_imgs_{course_id}")
    os.makedirs(temp_img_dir, exist_ok=True)

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        json_resp = resp.json()
        ppt_list = json_resp.get('data') or [] # 防御null

        if not ppt_list:
            print("  -> ⚠️ 该节次没有PPT。")
            return

        image_objects = []
        for index, item in enumerate(ppt_list):
            if img_url := item.get('pptImgUrl'):
                img_data = requests.get(img_url).content
                img = Image.open(io.BytesIO(img_data)).convert('RGB')
                image_objects.append(img)

        if image_objects:
            image_objects[0].save(pdf_filepath, "PDF", save_all=True, append_images=image_objects[1:])
            print(f"  -> ✅ PDF 合成成功")

    except Exception as e:
        print(f"  -> ❌ PPT处理失败: {e}")
    finally:
        if os.path.exists(temp_img_dir):
            shutil.rmtree(temp_img_dir)


def download_course_materials():
    # 步骤 1：加载初始凭证
    creds = load_credentials()
    global_cookie = creds.get("global_cookie", "")
    base_headers = {"User-Agent": USER_AGENT, "Cookie": global_cookie}

    # 步骤 2：尝试获取课程列表
    try:
        course_list = get_course_list(base_headers)
    except Exception as e:
        print(f"⚠️ Canvas 主站访问失败 (Cookie可能已过期): {e}")
        print("🔄 正在自动呼叫嗅探器刷新全局凭证...")
        # 没有 short_id，仅刷新全局 Cookie
        auto_sniff_credentials()
        creds = load_credentials()
        base_headers["Cookie"] = creds.get("global_cookie", "")
        course_list = get_course_list(base_headers)
    # 选择课程
    selected_course = cli_select_course(course_list)
    if not selected_course:
        exit("退出程序")

    short_id = selected_course['id']
    print(f"\n🎯 锁定目标: {selected_course['name']} (Canvas ID: {short_id})")
    # 动态组装你想抓取的视频平台跳转 URL
    target_video_url = f"https://oc.sjtu.edu.cn/courses/{short_id}/external_tools/8329?display=borderless"
    # 获取课程的所有视频列表
    course_data = creds.get("courses", {}).get(short_id)
    course_video_list = None

    # 如果本地 JSON 里已经存了这门课的 Token 和长 Hash，直接尝试请求
    if course_data:
        req_headers = base_headers.copy()
        req_headers["token"] = course_data["token"]
        # 传入长 Hash (hash_id) 而不是短 ID
        course_video_list = fetch_video_list(course_data["hash_id"], req_headers)

    # 如果本地没有这门课的记录，或者旧 Token 请求失败了，就去重新嗅探
    if not course_video_list:
        print("⚠️ 视频权限缺失或已失效，正在为您获取专属授权...")
        # 注意：这里把 short_id 传进去了，这样嗅探器就知道存到 JSON 的哪里
        auto_sniff_credentials(target_video_url, short_id)

        # 重新读取刚刚更新的 JSON
        creds = load_credentials()
        course_data = creds.get("courses", {}).get(short_id)

        if course_data:
            req_headers = base_headers.copy()
            req_headers["token"] = course_data["token"]
            print("🔄 凭证已刷新，重新请求视频列表...")
            # 再次使用长 Hash 请求
            course_video_list = fetch_video_list(course_data["hash_id"], req_headers)

    if not course_video_list:
        print("❌ 依然无法获取视频列表。可能这门课尚未录制视频。程序退出。")
        exit()

    # 步骤 4：环境准备与目录创建 (与之前逻辑一致)
    first_video_info = course_video_list[0]
    base_course_name = sanitize_filename(selected_course['name'].split('(研)')[0])
    teacher_name = sanitize_filename(first_video_info.get('userName', '未知教师'))

    course_dir = os.path.join(BASE_SAVE_DIR, f"{base_course_name}_{teacher_name}")
    os.makedirs(course_dir, exist_ok=True)
    print(f"\n📁 资源准备就绪，所有文件将保存在: {course_dir}")

    # 提前准备好带有正确 Token 的 Headers
    final_headers = base_headers.copy()
    final_headers["token"] = course_data["token"]

    # 步骤 5：执行下载任务
    for i, video in enumerate(course_video_list):
        course_session_name = sanitize_filename(video.get('videoName'))
        print("\n" + "=" * 60)
        print(f"⏳ 开始处理第 {i + 1}/{len(course_video_list)} 个视频: {course_session_name}")
        print("=" * 60)

        get_mp4_video(video, course_dir, final_headers)
        get_voice_transcript(video, course_dir, final_headers)
        get_ppt_and_make_pdf(video, course_dir, final_headers)

        time.sleep(1)

    print(f"\n🎉🎉🎉 课程【{base_course_name}】所有可用的课件与字幕已同步完毕！ 🎉🎉🎉")


if __name__ == "__main__":
    download_course_materials()