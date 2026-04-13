import datetime
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

driver = webdriver.Chrome()
driver.get('https://passport.jd.com/uc/login')
driver.find_element(By.XPATH, '//*[@id="content"]/div[2]/div[1]/div/div[2]/a').click()
time.sleep(10)
driver.get('https://cart.jd.com/cart_index')
time.sleep(2)

buy_time = datetime.datetime.strptime('2023-08-25 10:00:00', '%Y-%m-%d %H:%M:%S')
prepare_time = buy_time - datetime.timedelta(seconds=2)

# 等待进入准备时间
while True:
    current_time = datetime.datetime.now()
    print(current_time.strftime('%Y-%m-%d %H:%M:%S'))
    if current_time >= prepare_time:
        break
    time.sleep(1)

print("开始准备抢购...")
# 去结算页面
while 'https://cart.jd.com/cart_index' in driver.current_url:
    try:
        # 全选，去结算，点掉提示；去结算可能因为加入商品导致按钮顺序下移
        (driver
         .find_element(By.XPATH, '//*[@id="cart-body"]/div[2]/div[3]/div[1]/div/input')
         .click())
        (driver
         .find_element(By.XPATH, '//*[@id="cart-body"]/div[2]/div[5]/div/div[2]/div/div/div/div[2]/div[2]/div/div['
                                 '1]/a/b')
         .click())
        time.sleep(2) # 系统不能请求响应太快，否则会被封号。
        if '#none' in driver.current_url:
            driver.find_element(By.XPATH, '/html/body/div[9]/div[1]/div/div/div/p/a').click()
    except Exception as e:
        # 其他异常可以记录下来，但不中断循环
        print(f"发生异常: {e}")
    print(driver.current_url)
    time.sleep(0.5)
print("购物结算...")
# 提交订单页面
while 'https://trade.jd.com/shopping/order/getOrderInfo.action' == driver.current_url:
    try:
        print(driver.current_url)
        # 尝试点击按钮
        driver.find_element(By.ID, 'order-submit').click()
    except NoSuchElementException:
        # 如果找不到元素，可能页面已经跳转，退出循环
        break
    except Exception as e:
        # 其他异常可以记录下来，但不中断循环
        print(f"发生异常: {e}")
print("提交订单...")
print("抢购完成.")
