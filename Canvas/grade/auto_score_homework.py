import os
import io
import re
import time
import zipfile
import urllib.parse
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from canvasapi import Canvas
from zai import ZhipuAiClient

import docx
import fitz
import rarfile
import openpyxl
import json
import base64

# 环境配置
load_dotenv()
OC_URL = os.getenv("SJTU_URL", "")
OC_KEY = os.getenv("SJTU_TOKEN", "")
ZHIPU_API = os.getenv("ZHIPU_API", "")

rarfile.UNRAR_TOOL = "../lib/UnRAR.exe"
EXCEL_FILE = "grades.xlsx"
ai_client = ZhipuAiClient(api_key=ZHIPU_API)
# 计分规则
SCORE_ON_TIME = 100
SCORE_HALF = 50
SCORE_BLANK = 0
LATE_MULTIPLIER = 0.8



def log_ai_interaction(task_name: str, prompt: str, response: str):
    """将 AI 输入输出以 JSON 格式追加保存，方便 Debug"""
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "task": task_name,
        "input": prompt,
        "output": response
    }
    try:
        # 使用 jsonl (JSON Lines) 格式追加，每行一个 JSON，不会破坏文件结构
        with open("../ai_debug_log.jsonl", "a", encoding="utf-8") as f:
            json.dump(log_entry, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        print(f"    ⚠️ 日志写入失败: {e}")


def format_canvas_time(utc_time_str: str) -> str:
    """将 Canvas 的 UTC 时间转换为北京时间 (UTC+8)"""
    if not utc_time_str:
        return "无限制"
    try:
        dt_utc = datetime.strptime(str(utc_time_str), "%Y-%m-%dT%H:%M:%SZ")
        dt_bj = dt_utc + timedelta(hours=8)
        return dt_bj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        _ = e
        return str(utc_time_str)


def evaluate_vision_with_glm(assignment_context: str, student_text: str, student_images: list):
    """多模态阶段：如果纯文本无法判断，则连同图片一并发送给 GLM-4.6v-Flash 进行评阅"""
    print(f"      ☁️ 正在打包 {len(student_images)} 张图像，调用 GLM 视觉引擎复核...")

    prompt = f"""
【角色】    
你是一位严谨、客观、认真的高校助教，不需要讨好学生。

【作业题目要求说明】
{assignment_context}

【学生提交作答】（如果为空说明只有【学生提交图片】）
{student_text}

【任务】
请先概括【学生提交图片】的大致内容。
请严格核对学生的提交内容，并必须按照以下顺序输出你的思考过程和最终结论：
1. 简答题核对
分析学生是否对简答题进行了实质性作答。
如果学生仅仅抄录了题目，但下面空白或答非所问，必须判定为“未作答”；否则判定为“已作答”。
具体的计算过程、正确与否、结果数值等的缺失或错误，均不算做遗漏。
2. 实验任务核对
分析学生是否提交了实验代码或相关说明。
完全没有实验内容或内容与实验要求无关，必须判定为“未作答”；否则判定为“已作答”。
实验截图、选做内容的遗漏，均不算作遗漏。
3. 最终判定
若1和2均判定为“已作答”，则输出标签：[完全作答]
若1和2中有且仅有一个为“未作答”，输出标签：[部分作答]
若1和2均为“未作答”，或内容与课程完全无关，输出标签：[白卷]
若未给出具体题目细节导致无法核对，输出标签：[需人工复核]
请确保在回复的结尾，必须包含上述带方括号的标签之一。
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            content_list = []
            for img in student_images:
                img_base64 = base64.b64encode(img["bytes"]).decode("utf-8")
                content_list.append({"type": "image_url", "image_url": {"url": img_base64}})

            content_list.append({"type": "text", "text": prompt})

            response = ai_client.chat.completions.create(
                model="glm-4.6v-flash",
                messages=[{"role": "user", "content": content_list}],
                thinking={"type": "enabled"},
                temperature=0.1
            )

            result = response.choices[0].message.content.strip() if response.choices else ""
            log_ai_interaction("Evaluate_Vision_GLM", f"[附带 {len(student_images)} 张图片] 学生文本:\n{student_text}", result)
            print("      ✅ GLM 多模态复核成功！")

            matches = re.findall(r'\[(完全作答|部分作答|白卷|需人工复核)\]', result)
            status_tag = f"[{matches[-1]}]" if matches else "[需人工复核]"
            reason = result.replace('\n', ' | ')
            return status_tag, reason

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "1302" in error_msg:
                wait_time = (attempt + 1) * 30
                print(
                    f"      ⏳ 触发视觉模型速率限制(429)，等待 {wait_time} 秒后重试 (第 {attempt + 1}/{max_retries} 次)...")
                time.sleep(wait_time)
            else:
                print(f"      ❌ GLM 视觉模型调用失败: {e}")
                return "[需人工复核]", f"多模态评卷 API 调用异常: {e}"

    return "[需人工复核]", "多模态 API 触发速率限制，多次重试失败"


def extract_text_from_memory(file_bytes: io.BytesIO, filename: str, image_list: list) -> str:
    """在内存中解析不同格式的文件，将提取到的图片放入 image_list 队列备用"""
    clean_filename = urllib.parse.unquote(str(filename)).lower()
    ext = os.path.splitext(clean_filename)[1]
    text = ""

    # noinspection PyBroadException
    try:
        if ext == '.zip':
            print(f"      📦 发现 ZIP 压缩包 {clean_filename}，尝试内存解压...")
            try:
                with zipfile.ZipFile(file_bytes) as z:
                    for zip_info in z.infolist():
                        # 跳过目录条目和隐藏文件
                        if zip_info.is_dir() or zip_info.filename.startswith('__MACOSX') or zip_info.filename.startswith('.'):
                            continue
                        with z.open(zip_info) as f:
                            inner_bytes = io.BytesIO(f.read())
                            text += extract_text_from_memory(inner_bytes, zip_info.filename, image_list) + "\n"
            except zipfile.BadZipFile:
                return "[NEEDS_MANUAL_REVIEW: ZIP_ERROR]"

        elif ext == '.rar':
            print(f"      📦 发现 RAR 压缩包 {clean_filename}，尝试调用 unrar...")
            try:
                temp_rar = f"temp_{int(time.time())}.rar"
                with open(temp_rar, 'wb') as temp_f:
                    temp_f.write(file_bytes.read())
                with rarfile.RarFile(temp_rar) as rf:
                    for rf_info in rf.infolist():
                        # 跳过 RAR 中的目录条目
                        if rf_info.isdir() or rf_info.filename.startswith('__MACOSX'):
                            continue
                        with rf.open(rf_info) as f:
                            inner_bytes = io.BytesIO(f.read())
                            text += extract_text_from_memory(inner_bytes, rf_info.filename, image_list) + "\n"
                os.remove(temp_rar)
            except Exception as e:
                print(f"      ⚠️ RAR解压失败: {e}")
                return "[NEEDS_MANUAL_REVIEW: RAR_ERROR]"

        elif ext == '.docx':
            try:
                doc = docx.Document(file_bytes)
                text = "\n".join([para.text for para in doc.paragraphs])
                img_count = 0
                for rel in doc.part.rels.values():
                    if "image" in rel.target_ref:
                        if img_count < 10:  # 限制提取前10张防内存爆炸
                            image_list.append({"ext": ".png", "bytes": rel.target_part.blob})
                        img_count += 1
                if img_count > 0:
                    print(f"      📷 DOCX内检测到 {img_count} 张嵌入图片，已加入多模态备审队列。")
            except Exception:
                return "[NEEDS_MANUAL_REVIEW: DOCX_ERROR]"

        elif ext == '.doc':
            print(f"      ⚠️ 老版本 .doc 无法直接解析，标记人工复核。")
            return "[NEEDS_MANUAL_REVIEW: DOC_FORMAT]"

        elif ext == '.pdf':
            img_count = 0
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text()
                    img_count += len(page.get_images())
                # 如果是扫描版 PDF，把前3页截图丢进待测图片队列
                if img_count > 0:
                    print(f"      📷 PDF内检测到图表元素，提取前 {min(5, len(doc))} 页图像加入多模态备审队列。")
                    for i in range(len(doc)):
                        pix = doc[i].get_pixmap(dpi=150)
                        image_list.append({"ext": ".png", "bytes": pix.tobytes("png")})

        elif ext in ['.png', '.jpg', '.jpeg']:
            image_list.append({"ext": ext, "bytes": file_bytes.read()})

        elif ext in ['.txt', '.md', '.py', '.c', '.cpp', '.java']:
            text = file_bytes.read().decode('utf-8', errors='ignore')

        return text.strip()
    except Exception as e:
        print(f"      ❌ 解析 {clean_filename} 发生内部错误: {e}")
        return "[NEEDS_MANUAL_REVIEW: PARSE_ERROR]"


def download_and_extract(url: str, filename: str, image_list: list, headers=None) -> str:
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        file_bytes = io.BytesIO(response.content)
        return extract_text_from_memory(file_bytes, filename, image_list)
    except Exception as e:
        print(f"    ❌ 下载附件失败: {e}")
        return "[NEEDS_MANUAL_REVIEW: DOWNLOAD_FAILED]"


def extract_assignment_context(assignment, course) -> str:
    raw_desc = assignment.description if assignment.description else ""
    soup = BeautifulSoup(str(raw_desc), "html.parser")
    context_text = soup.get_text(separator="\n").strip()

    links = soup.find_all('a', href=True)

    for a in links:
        href = str(a['href'])
        if '/files/' in href.lower():
            # 通过正则提取真正的文件 ID
            match = re.search(r'/files/(\d+)', href)
            if match:
                file_id = match.group(1)
                print(f"    🔗 尝试通过 Canvas API 解析文件ID {file_id} 的真实地址...")
                try:
                    # 使用 canvasapi 获取真正的底层下载直链
                    file_obj = course.get_file(file_id)
                    real_download_url = file_obj.url

                    # 获取 Canvas 系统中真实的附件文件名（如果获取不到再兜底）
                    real_filename = getattr(file_obj, 'filename', f"assignment_req_{file_id}.pdf")

                    req_images = []
                    # 传入真实的文件名，让底层解析器根据正确的扩展名去处理 (.py, .docx, .pdf 等)
                    extracted_text = download_and_extract(real_download_url, real_filename, req_images)

                    if extracted_text and not extracted_text.startswith("[NEEDS"):
                        context_text += f"\n\n【作业附件 {real_filename} 内容解析】:\n" + extracted_text
                        print(f"    ✅ 成功将作业附件 {real_filename} 提取为 AI 上下文！")
                except Exception as e:
                    print(f"    ⚠️ 无法提取题目附件(ID: {file_id}): {e}")

    if not context_text:
        context_text = "（老师未在此作业页面填写具体描述，请根据普遍常理判断）"

    return context_text


def evaluate_text_with_glm(assignment_context: str, student_text: str):
    """纯文本阶段：使用 GLM-4.7-Flash 判定纯文本的内容"""
    system_prompt = f"""
【角色】    
你是一位严谨、客观、认真的高校助教，绝对不能讨好学生或自行脑补任何内容，完全根据我所提供的材料进行事实性判断。
【作业题目要求说明】
{assignment_context}
【任务】
请严格核对学生的提交内容，并必须按照以下顺序输出你的思考过程和最终结论：
1. 简答题核对
分析学生是否对简答题进行了实质性作答。
如果学生仅仅抄录了题目，但下面空白或答非所问，必须判定为“未作答”；否则判定为“已作答”。
具体的计算过程、正确与否、结果数值等的缺失或错误，均不算做遗漏。
2. 实验任务核对
分析学生是否提交了实验代码或相关说明。
完全没有实验内容或内容与实验要求无关，必须判定为“未作答”；否则判定为“已作答”。
实验截图、选做内容的遗漏，均不算作遗漏。
3. 最终判定
若1和2均判定为“已作答”，则输出标签：[完全作答]
若1和2中有且仅有一个为“未作答”，输出标签：[部分作答]
若1和2均为“未作答”，或内容与课程完全无关，输出标签：[白卷]
若未给出具体题目细节导致无法核对，输出标签：[需人工复核]
请确保在回复的结尾，必须包含上述带方括号的标签之一。
"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = ai_client.chat.completions.create(
                model="glm-4.7-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"【学生提交作答】\n{student_text}"}
                ],
                thinking={"type": "disabled"},
                temperature=0.1
            )
            result = response.choices[0].message.content.strip() if response.choices else ""
            log_ai_interaction("Evaluate_Text_GLM", f"学生文本({len(student_text)}字):\n{student_text}", result)
            matches = re.findall(r'\[(完全作答|部分作答|白卷|需人工复核)\]', result)
            status_tag = f"[{matches[-1]}]" if matches else "[需人工复核]"
            reason = result.replace('\n', ' | ')
            return status_tag, reason

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "1302" in error_msg or "1305" in error_msg:
                wait_time = (attempt + 1) * 60  # 依次等待 60秒, 120秒, 180秒
                print(
                    f"      ⏳ {e}，等待 {wait_time} 秒后重试 (第 {attempt + 1}/{max_retries} 次)...")
                time.sleep(wait_time)
            else:
                print(f"      ❌ GLM 文本调用失败: {e}")
                return "[需人工复核]", f"API 调用异常: {e}"

    return "[需人工复核]", "API 触发速率限制，多次重试失败"


def load_excel_mapping(ws, target_col_idx):
    """加载 Excel 中所有学生的当前分数，方便快速查找跳过"""
    mapping = {}
    for row in range(2, ws.max_row + 1):
        name = str(ws.cell(row=row, column=1).value or "").strip()
        score = ws.cell(row=row, column=target_col_idx).value
        mapping[name] = {"row": row, "score": score}
    return mapping


def main():
    print("正在连接交大 OC (Canvas) API...")
    canvas = Canvas(OC_URL, OC_KEY)

    courses = list(canvas.get_courses(enrollment_state='active'))
    print("\n【请选择你要批改的课程】:")
    for i, course in enumerate(courses):
        print(f"[{i}] {getattr(course, 'name', '未知课程')} (ID: {course.id})")

    course_idx = int(input("请输入课程编号: "))
    selected_course = courses[course_idx]

    assignments = list(selected_course.get_assignments())
    print("\n【请选择你要批改的作业】:")
    for i, assignment in enumerate(assignments):
        print(f"[{i}] {assignment.name} (ID: {assignment.id})")

    assign_idx = int(input("请输入作业编号: "))
    selected_assignment = assignments[assign_idx]

    # --- 新增：自动匹配章节序号逻辑 ---
    cn_to_num = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
                 '十': '10'}

    # 尝试匹配 "第一章" 或 "第1章"
    match_cn = re.search(r'第([一二三四五六七八九十])章', selected_assignment.name)
    match_ar = re.search(r'第(\d+)章', selected_assignment.name)

    target_excel_col_number = None
    if match_cn:
        target_excel_col_number = cn_to_num.get(match_cn.group(1))
    elif match_ar:
        target_excel_col_number = match_ar.group(1)

    if target_excel_col_number:
        print(f"\n💡 自动识别到章节：匹配为 Excel 中的 [作业{target_excel_col_number}] 列")
        target_excel_col_name = "作业" + target_excel_col_number
    else:
        # 如果选了类似“大作业提交”或“课堂小测1”这种没有“第X章”的，自动回退到手动输入
        target_excel_col_number = input(
            f"\n未能从名称 '{selected_assignment.name}' 自动识别章节序号，请手动输入对应Excel的列序号: ")
        target_excel_col_name = "作业" + target_excel_col_number

    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb['Sheet1']

    target_col_idx = -1
    for col in range(1, ws.max_column + 1):
        if ws.cell(row=1, column=col).value == target_excel_col_name:
            target_col_idx = col
            break

    if target_col_idx == -1:
        print(f"❌ Excel 中未找到列名 '{target_excel_col_name}'！")
        return

    student_mapping = load_excel_mapping(ws, target_col_idx)

    print(f"\n🚀 开始批改: {selected_assignment.name}")
    print("自动跳过已经评为满分的学生...")
    print("正在解析作业要求作为 AI 上下文...")
    assignment_context = extract_assignment_context(selected_assignment, selected_course)
    print(f"📄 提取到的上下文: {assignment_context} ")

    raw_due = getattr(selected_assignment, 'due_at', None)
    due_at_bj = format_canvas_time(str(raw_due) if raw_due else "")
    print(f"⏰ 系统截止时间: {due_at_bj}")
    print("-" * 50)

    submissions = selected_assignment.get_submissions(include=['user', 'submission_comments'])

    for sub in submissions:
        student_name = sub.user.get('name', '未知')

        # 👑 静默跳过已经是 100 分的同学
        if student_name in student_mapping:
            current_score = student_mapping[student_name]['score']
            if str(current_score) == "100" or current_score == 100.0:
                continue

        if sub.workflow_state == 'unsubmitted':
            print(f"[{student_name}] 未提交 -> Excel 填 0")
            if student_name in student_mapping:
                ws.cell(row=student_mapping[student_name]['row'], column=target_col_idx).value = 0
            continue

        is_late = getattr(sub, 'late', False)
        raw_submitted = getattr(sub, 'submitted_at', None)
        submitted_at_bj = format_canvas_time(str(raw_submitted) if raw_submitted else "")

        print(
            f"[{student_name}] 状态: 已提交 | 提交时间: {submitted_at_bj} | 逾期标记: {'是 ⚠️' if is_late else '否 ✅'}")

        combined_text = str(sub.body) + "\n" if hasattr(sub, 'body') and sub.body else ""
        student_images = []

        # 1. 抓取主提交区的附件
        attachments = getattr(sub, 'attachments', [])
        for att in attachments:
            clean_filename = urllib.parse.unquote(str(att.filename))
            print(f"    📥 正在拉取主附件: {clean_filename}")
            combined_text += download_and_extract(att.url, clean_filename, student_images) + "\n"

        # 2. 抓取评论区的留言文本与附件
        needs_review = False
        comments = getattr(sub, 'submission_comments', [])
        for comment in comments:
            # 提取留言文字
            msg = str(comment.get('comment', ''))
            if msg:
                combined_text += f"\n【学生评论区留言】: {msg}\n"
                # 检查豁免关键字
                if any(kw in msg for kw in ['晚交', '逾期', '补交', '修改', '不要算', '不算逾期']):
                    needs_review = True
                    print(f"    💬 豁免留言: {msg}")

            # 💡 提取留言区的附件（比如翁文豪补交的PDF）
            comment_attachments = comment.get('attachments', [])
            for c_att in comment_attachments:
                # Canvas API 的 comment.attachments 返回的是字典
                c_att_filename = urllib.parse.unquote(
                    str(c_att.get('display_name', c_att.get('filename', 'comment_attachment'))))
                c_att_url = c_att.get('url', '')
                if c_att_url:
                    print(f"    📥 正在拉取评论区附件: {c_att_filename}")
                    combined_text += download_and_extract(c_att_url, c_att_filename, student_images) + "\n"

        # 预检异常格式
        if "[NEEDS_MANUAL_REVIEW" in combined_text:
            status_tag, ai_reason = "[需人工复核]", "文件格式暂不支持自动读取或损坏"
            print(f"    ⚠️ 预检拦截: {ai_reason}")
        elif len(combined_text.strip()) < 10 and not student_images:
            status_tag, ai_reason = "[白卷]", "文本内容为空且无图片"
            print(f"    ⚠️ 预检拦截: {ai_reason}")
        else:
            # 👑 阶段一：先用 GLM 纯文本大模型判定
            status_tag, ai_reason = evaluate_text_with_glm(assignment_context, combined_text)

            # 👑 阶段二：如果文本判定不过关（白卷），且存在图片/扫描件，启动多模态复核！
            if any(tag in status_tag for tag in ["[白卷]", "[部分作答]", "[需人工复核]"]) and student_images:
                print(
                    f"    ⚠️ 文本判定为 {status_tag}，但检测到有 {len(student_images)} 张待审图片/扫描件页。启动多模态复核...")
                status_tag, ai_reason = evaluate_vision_with_glm(assignment_context, combined_text, student_images)
                print(f"    🤖 GLM 多模态复核返回 -> 标签: {status_tag} | 理由: {ai_reason}")
            else:
                print(f"    🤖 GLM 文本大模型返回 -> 标签: {status_tag} | 理由: {ai_reason}")

        if "[需人工复核]" in status_tag:
            final_score = "需人工复核"
        elif needs_review:
            final_score = "需复核 (豁免申请)"
        elif "[白卷]" in status_tag:
            final_score = SCORE_BLANK
        else:
            # 1. 先定基础分
            if "[部分作答]" in status_tag:
                base_score = SCORE_HALF
            else:
                base_score = SCORE_ON_TIME

            # 2. 如果逾期，在此基础上打 8折
            if is_late:
                final_score = int(base_score * LATE_MULTIPLIER)
                print(f"    ⚠️ 检测到作业逾期，基础分 {base_score} -> 折算为 {final_score}")
            else:
                final_score = base_score

        print(f"    👉 最终处理动作: Excel 填入 -> {final_score}")
        if student_name in student_mapping:
            ws.cell(row=student_mapping[student_name]['row'], column=target_col_idx).value = final_score
        else:
            print(f"    ❌ 警告：Excel中未找到该学生姓名！")

        print("-" * 50)
        time.sleep(3)

    wb.save(EXCEL_FILE)
    print(f"\n🎉 批改全部完成！结果已存至 {EXCEL_FILE}")


if __name__ == "__main__":
    main()