from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests
import time
import re

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
# 禁用自动化检测标志
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)
driver = webdriver.Chrome(options=chrome_options)
# 修改navigator.webdriver属性
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    })
    """
})
base_url = "https://sci-hub.se"

class SciHub:
    def __init__(self):
        pass
    
    @staticmethod
    def download_scihub_by_title(query, output_path):
        """尝试通过SCIHUB API查找下载PDF"""
        driver.get(base_url)
        try:
            text_element = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "request"))
            )
            text_element.send_keys(query)
        except Exception as e:
            print("等待元素超时:", driver.page_source)
            return False

        try:
            button_element = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#enter > button"))
            )
            button_element.click()
            try:
                button_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#pdf"))
                )
                pdf_url= button_element.get_attribute("src")

                all_cookies = driver.get_cookies()
                cookies_dict = {cookie['name']: cookie['value'] for cookie in all_cookies}
                print(cookies_dict)

                print(f"{pdf_url}")
                response = requests.get(
                    f"{pdf_url}",
                    cookies=cookies_dict
                )
                
                if response.headers['Content-Type'] == 'application/pdf':
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    return True
                else:
                    print("页面格式不是PDF")
                    print("页面源码:", driver.page_source)
            except Exception as e:
                if driver.current_url == base_url:
                    print("未找到PDF")
        except Exception as e:
            print("等待元素超时:", driver.page_source)
        return False
    
    @staticmethod
    def quit():
        driver.quit()

SciHub.download_scihub_by_title('Breaking Long-Tailed Learning Bottlenecks: A Controllable Paradigm with Hypernetwork-Generated Diverse Experts', "title.pdf")