import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

driver = webdriver.Chrome()
# 吾爱破解
driver.get('https://www.52pojie.cn/')
time.sleep(100)
driver.find_element(By.XPATH, '//*[@id="um"]/p[2]/a[1]').click()
