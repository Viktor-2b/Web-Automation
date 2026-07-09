import pandas as pd
from openpyxl import load_workbook


def update_attendance_inplace():
    # 1. 使用 pandas 读取并计算分数
    # 注：请确保此处的 csv 文件名与你实际的文件名一致（你这里写的是 出勤.csv）
    try:
        attend_df = pd.read_csv('出勤.csv', encoding='utf-8-sig')  # 如果你改名了，请把这里换成 '出勤.csv'
    except UnicodeDecodeError:
        attend_df = pd.read_csv('出勤.csv', encoding='gbk')
    except FileNotFoundError:
        print("❌ 找不到文件，请检查是 '签到.csv' 还是 '出勤.csv'")
        return

    # 添加断言，告诉 PyCharm 这是一个 DataFrame，彻底消除黄色的下划线警告
    assert isinstance(attend_df, pd.DataFrame)

    attend_df['学号'] = attend_df['学号'].astype(str).str.strip()
    date_columns = attend_df.columns[2:16]

    def calculate_attendance_score(row):
        x_count = 0
        for col in date_columns:
            val = str(row[col]).strip().upper()
            if val == 'X':
                x_count += 1
        return 100 - (x_count * 1)

    attend_df['出勤得分'] = attend_df.apply(calculate_attendance_score, axis=1)
    attend_map = dict(zip(attend_df['学号'], attend_df['出勤得分']))

    # 2. 使用 openpyxl 直接修改原文件
    filename = '平时分.xlsx'
    try:
        wb = load_workbook(filename)
    except FileNotFoundError:
        print(f"❌ 找不到文件: {filename}")
        return

    ws = wb.active  # 默认读取第一个工作表

    # 动态获取表头，强制转为字符串并去除所有看不见的空格（解决你报错第32行和填不进去的问题）
    headers = {}
    for idx, cell in enumerate(ws[1]):
        if cell.value is not None:
            # 清理表头名称，避免空格干扰
            clean_key = str(cell.value).strip()
            headers[clean_key] = idx

    print(f"🔍 成功识别到的 Excel 表头: {list(headers.keys())}")

    col_id = headers.get('学号')
    col_attend = headers.get('出勤')

    if col_id is None:
        print("❌ 写入失败：未在第一行找到名为 '学号' 的列！")
        return
    if col_attend is None:
        print("❌ 写入失败：未在第一行找到名为 '出勤' 的列！")
        return

    # 3. 开始向已有列写入分数
    update_count = 0
    for row in ws.iter_rows(min_row=2):  # 从第二行开始遍历
        # 读取表格中的学号
        raw_val = row[col_id].value
        student_id = str(raw_val).strip() if raw_val else None

        if student_id:
            if student_id in attend_map:
                row[col_attend].value = attend_map[student_id]
                update_count += 1
            else:
                row[col_attend].value = 100  # 签到表没有这人的，默认满分防漏

    # 直接保存覆盖原文件
    wb.save(filename)
    print(f"✅ 【出勤】数据更新完毕！共更新了 {update_count} 条记录。请打开 {filename} 查看。")


if __name__ == "__main__":
    update_attendance_inplace()