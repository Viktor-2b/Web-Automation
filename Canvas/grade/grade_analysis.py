import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde

# 解决图表中的中文显示问题
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


def plot_last_year_curve():
    file_path = '成绩导入表(2024-2025-2)-CS3611-02_计算机网络.xlsx'
    try:
        df = pd.read_excel(file_path)
    except FileNotFoundError:
        print(f"❌ 找不到文件: {file_path}")
        return

    # 智能寻找总分列
    total_col = None
    for col in df.columns:
        if '总分' in str(col) or '总评' in str(col):
            total_col = col
            break

    if not total_col:
        print("❌ 未找到包含'总分'或'总评'的列名，请检查Excel表头")
        return

    # 清洗数据：过滤无效值
    df[total_col] = pd.to_numeric(df[total_col], errors='coerce')
    valid_scores = df[total_col].dropna().values

    # 统计数据
    mean_score = np.mean(valid_scores)
    std_score = np.std(valid_scores)

    print(f"📊 成功读取去年成绩：共 {len(valid_scores)} 条有效数据。")
    print(f"   均值 (μ): {mean_score:.2f}")
    print(f"   标准差 (σ): {std_score:.2f}")

    # ================= 开始画图 =================
    plt.figure(figsize=(10, 6))

    # 构建 X 轴区间 (横跨 50 到 105 分)
    x = np.linspace(50, 105, 500)

    # 1. 绘制【真实成绩分布密度曲线】(KDE) -> 取代柱状图
    # bw_method=0.4 用于控制曲线的平滑程度，数值越大越平滑
    kde = gaussian_kde(valid_scores, bw_method=0.4)
    y_real = kde(x)

    plt.plot(x, y_real, color='royalblue', linewidth=2.5, label='去年真实成绩曲线')
    plt.fill_between(x, y_real, alpha=0.3, color='royalblue')

    # 2. 绘制【理想正态拟合曲线】
    # 标准高斯概率密度公式
    y_norm = (1 / (std_score * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean_score) / std_score) ** 2)

    # 注意这里使用 \\mu 和 \\sigma 防止语法警告
    plt.plot(x, y_norm, color='crimson', linestyle='--', linewidth=2,
             label=f'标准正态拟合 ($\\mu={mean_score:.1f}, \\sigma={std_score:.1f}$)')

    # 添加参考分界线
    plt.axvline(85, color='green', linestyle=':', linewidth=1.5, label='A- 分界线 (85分)')
    plt.axvline(90, color='orange', linestyle=':', linewidth=1.5, label='A 分界线 (90分)')

    # 完善图表细节
    plt.title('2024-2025-2 计算机网络 成绩真实分布与正态拟合', fontsize=16)
    plt.xlabel('最终总评分数', fontsize=12)
    plt.ylabel('分布密度', fontsize=12)
    plt.legend(fontsize=11, loc='upper left')
    plt.grid(axis='y', alpha=0.3)

    # 设置X轴刻度更密集
    plt.xticks(np.arange(50, 105, 5))

    # 保存并显示
    output_img = '去年成绩分布双曲线图.png'
    plt.savefig(output_img, dpi=300, bbox_inches='tight')
    print(f"📈 图表已保存为 '{output_img}'，正在打开显示界面...")
    plt.show()


def analyze_last_year_grades():
    file_path = '成绩导入表(2024-2025-2)-CS3611-02_计算机网络.xlsx'
    try:
        # 读取 Excel 数据
        df = pd.read_excel(file_path)
    except FileNotFoundError:
        print(f"❌ 找不到文件: {file_path}")
        return

    # 1. 智能寻找“总分”所在的列
    total_col = None
    for col in df.columns:
        if '总分' in str(col) or '总评' in str(col):
            total_col = col
            break

    if not total_col:
        print("❌ 未找到包含'总分'的列名，请检查Excel表头")
        return

    # 2. 清洗数据：过滤掉退课或没有成绩的行
    df[total_col] = pd.to_numeric(df[total_col], errors='coerce')
    valid_df = df.dropna(subset=[total_col]).copy()

    # 3. 定义评级函数（严格按照你之前的对照表）
    def get_grade(score):
        if score >= 95:
            return 'A+'
        elif score >= 90:
            return 'A'
        elif score >= 85:
            return 'A-'
        elif score >= 80:
            return 'B+'
        elif score >= 75:
            return 'B'
        elif score >= 70:
            return 'B-'
        elif score >= 67:
            return 'C+'
        elif score >= 65:
            return 'C'
        elif score >= 62:
            return 'C-'
        elif score >= 60:
            return 'D'
        else:
            return 'F'

    # 应用评级并在末尾新增一列
    valid_df['等级'] = valid_df[total_col].apply(get_grade)

    # 4. 统计各项比例
    total_valid = len(valid_df)
    mean_score = valid_df[total_col].mean()

    grade_counts = valid_df['等级'].value_counts()

    a_plus = grade_counts.get('A+', 0)
    a = grade_counts.get('A', 0)
    a_minus = grade_counts.get('A-', 0)

    a_and_above = a_plus + a
    a_minus_and_above = a_and_above + a_minus

    # 5. 打印震撼的结果
    print("=" * 55)
    print("📊 去年（2024-2025-2）计网成绩真实揭秘")
    print("=" * 55)
    print(f"✅ 有效出分人数: {total_valid} 人")
    print(f"📈 真实平均分:   {mean_score:.2f} 分")
    print("-" * 55)
    print(f"🏅 A+  人数: {a_plus:2d} 人 | 占比: {(a_plus / total_valid) * 100:.1f}%")
    print(f"🥇 A   人数: {a:2d} 人 | 占比: {(a / total_valid) * 100:.1f}%")
    print(f"🥈 A-  人数: {a_minus:2d} 人 | 占比: {(a_minus / total_valid) * 100:.1f}%")
    print("-" * 55)
    print(f"🚨 A及以上 (>=90) 真实占比: {(a_and_above / total_valid) * 100:.1f}%")
    print(f"🚨 A-及以上 (>=85) 真实占比: {(a_minus_and_above / total_valid) * 100:.1f}%")
    print("=" * 55)

    # 6. 保存带有等级的新文件
    output_file = '去年成绩分析_带等级.xlsx'
    valid_df.to_excel(output_file, index=False)
    print(f"\n📁 带有绩点等级的明细表已保存至: {output_file}")


if __name__ == '__main__':
    analyze_last_year_grades()
    plot_last_year_curve()