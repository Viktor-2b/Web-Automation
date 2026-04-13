import requests
import pandas as pd
from utils.get_cookie import get_browser_cookies

# 配置信息
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
COURSE_ID = "88697"

COOKIE, _ = get_browser_cookies()
BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Cookie": COOKIE,
    "Accept": "application/json"
}


def fetch_all_students():
    """循环请求 API 获取所有页面的学生数据"""
    students_data = []
    # 初始 URL
    url = f"https://oc.sjtu.edu.cn/api/v1/courses/{COURSE_ID}/users"
    params = {
        "include[]": ["enrollments", "email"],
        "per_page": 50,
        "include_inactive": "true"
    }

    print(f"🚀 开始抓取课程的成员信息...")

    while url:
        try:
            response = requests.get(url, headers=BASE_HEADERS, params=params if "?" not in url else None)
            response.raise_for_status()

            users = response.json()
            for user in users:
                # 提取身份 (取第一个 enrollment 的 type)
                enrollments = user.get("enrollments", [{}])
                role_type = enrollments[0].get("type", "Unknown")

                # 映射身份名称
                role_map = {
                    "StudentEnrollment": "学生",
                    "TeacherEnrollment": "教师",
                    "TaEnrollment": "助教"
                }

                students_data.append({
                    "姓名": user.get("name"),
                    "学号": user.get("login_id"),
                    "身份": role_map.get(role_type, role_type),
                    "邮箱": user.get("email")
                })

            # 处理分页：检查 Response Headers 中的 Link 字段是否有 next
            # Link 格式通常为: <url>; rel="next", <url>; rel="last"
            next_link = response.links.get("next")
            if next_link:
                url = next_link.get("url")
                print("  -> 正在加载下一页...")
            else:
                url = None

        except Exception as e:
            print(f"❌ 抓取失败: {e}")
            break

    return students_data


def save_to_excel(data, filename="students.xlsx"):
    if not data:
        print("⚠️ 没有数据可以保存")
        return

    df = pd.DataFrame(data)

    # 按照要求添加空白列
    df["作业1"] = ""
    df["作业2"] = ""
    df["作业3"] = ""
    df["作业4"] = ""
    df["作业5"] = ""
    df["请假"] = ""

    # 调整列顺序
    cols = ["姓名", "学号", "身份", "邮箱", "请假", "作业1", "作业2", "作业3", "作业4", "作业5"]
    df = df[cols]

    try:
        df.to_excel(filename, index=False, engine='openpyxl')
        print(f"\n✅ 成功保存到: {filename}")
        print(f"📊 共计导出 {len(df)} 条记录")
    except Exception as e:
        print(f"❌ 保存 Excel 失败: {e}")


if __name__ == "__main__":
    # 1. 抓取数据
    all_users = fetch_all_students()

    # 2. 保存文件
    save_to_excel(all_users)