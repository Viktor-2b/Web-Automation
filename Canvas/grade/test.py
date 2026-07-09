from decimal import Decimal, ROUND_HALF_UP

a = 59
b = 96
c = 100

# 1. 权重必须以字符串的形式传给 Decimal，杜绝底层的 0.30000000000000004 精度污染
weight_a = Decimal('0.3')
weight_b = Decimal('0.3')
weight_c = Decimal('0.4')

# 2. 将原始分数转换为 Decimal 进行高精度计算
d = Decimal(str(a)) * weight_a + Decimal(str(b)) * weight_b + Decimal(str(c)) * weight_c

print("精确计算结果 d =", d)  # 结果是: 86.5

# 3. 使用 ROUND_HALF_UP 执行传统数学上的“四舍五入”（逢 0.5 向上进位）
final_score = int(d.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

print("真正的四舍五入结果 =", final_score) # 结果是: 87