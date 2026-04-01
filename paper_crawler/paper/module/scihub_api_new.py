# -*- coding: utf-8 -*-

import threading
import time
import requests
from urllib.parse import urlparse
from lxml import etree
from enum import Enum, unique
from pathlib import Path


@unique
class SciHubAPIError(Enum):
    # 未知错误
    UNKNOWN = 0
    
    # 找不到有效的PDF
    NO_VALID_PDF = 1
    
    # 被验证码阻止
    BLOCKED_BY_CAPTCHA = 2
    
    # 验证码错误
    WRONG_CAPTCHA = 3


class SciHubAPI:
    def __init__(self, scihub_url="https://sci-hub.se"):
        self.scihub_url = scihub_url
        self.sess = requests.Session()
        self.sess.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def search(self, query):
        """
        使用DOI搜索论文并返回PDF链接
        
        参数:
            doi: 论文的DOI
            
        返回:
            (pdf_url, error): PDF链接和错误信息的元组
        """
        print(f'使用Sci-Hub URL: {self.scihub_url}')
        print(f'搜索: {query}')
        
        pdf_url = query
        err = None
        
        try:
            print('获取PDF URL...')
            
            # 发送请求到Sci-Hub
            pdf_url_response = self.sess.post(
                self.scihub_url, 
                data={'request': query}, 
                verify=False,
                timeout=30
            )
            
            if pdf_url_response.status_code != 200:
                print(f'错误 {pdf_url_response.status_code}')
                print('您可能需要手动检查。')
                err = SciHubAPIError.UNKNOWN
            else:
                # 解析HTML响应
                html = etree.HTML(pdf_url_response.content)
                
                # 尝试找到PDF嵌入元素
                article = \
                    html.xpath('//div[@id="article"]/embed[1]') or \
                    html.xpath('//div[@id="article"]/iframe[1]') if \
                    html is not None else None
                
                if article and len(article) > 0:
                    # 提取PDF URL
                    pdf_url = urlparse(article[0].attrib['src'])
                    response_url = urlparse(pdf_url_response.url)
                    
                    # 确保URL有完整的scheme和netloc
                    if pdf_url.scheme == '':
                        pdf_url = pdf_url._replace(scheme=response_url.scheme)
                    
                    if pdf_url.netloc == '':
                        pdf_url = pdf_url._replace(netloc=response_url.netloc)
                    
                    pdf_url = pdf_url.geturl()
                    print(f'获取到PDF URL: {pdf_url}')
                else:
                    # 检查是否有验证码
                    captcha_check = html.xpath('//img[@id="captcha"]')
                    if captcha_check and len(captcha_check) > 0:
                        print('遇到验证码!')
                        err = SciHubAPIError.BLOCKED_BY_CAPTCHA
                        # 这里需要处理验证码
                        # TODO: 处理验证码的代码将在此处添加
                    else:
                        err = SciHubAPIError.NO_VALID_PDF
                        print('无法获取PDF URL!')
                        print('您可能需要手动检查。')
        except Exception as e:
            err = SciHubAPIError.UNKNOWN
            print('获取PDF URL失败!')
            print('您可能需要手动检查。')
            print(f'错误: {str(e)}')
        
        return pdf_url, err
    
    def get_captcha_info(self, pdf_captcha_response):
        """
        从验证码响应中提取验证码ID和图片URL
        
        参数:
            pdf_captcha_response: 包含验证码的响应
            
        返回:
            (captcha_id, captcha_img_url): 验证码ID和图片URL的元组
        """
        captcha_id, captcha_img_url = None, None
        
        html = etree.HTML(pdf_captcha_response.content)
        imgs = html.xpath('//img[@id="captcha"]')
        ids = html.xpath('//input[@name="id"]')
        
        if len(imgs) > 0 and len(ids) > 0:
            captcha_id = ids[0].attrib['value']
            captcha_img_url = urlparse(imgs[0].attrib['src'])
            response_url = urlparse(pdf_captcha_response.url)
            
            if captcha_img_url.scheme == '':
                captcha_img_url = captcha_img_url._replace(scheme=response_url.scheme)
            
            if captcha_img_url.netloc == '':
                captcha_img_url = captcha_img_url._replace(netloc=response_url.netloc)
            
            captcha_img_url = captcha_img_url.geturl()
        
        return captcha_id, captcha_img_url
    
    def fetch_pdf(self, pdf_url):
        """
        获取PDF内容
        
        参数:
            pdf_url: PDF的URL
            
        返回:
            (pdf_content, error): PDF内容和错误信息的元组
        """
        print('获取PDF...')
        
        pdf, err = None, None
        
        try:
            pdf_response = self.sess.get(
                pdf_url, 
                verify=False,
                timeout=30
            )
            
            if pdf_response.status_code != 200:
                print(f'错误 {pdf_response.status_code}')
                print('您可能需要手动检查。')
                err = SciHubAPIError.UNKNOWN
            elif pdf_response.headers['Content-Type'] == 'application/pdf':
                pdf = pdf_response.content
                print('成功获取PDF内容')
            elif pdf_response.headers['Content-Type'].startswith('text/html'):
                print('遇到验证码!')
                err = SciHubAPIError.BLOCKED_BY_CAPTCHA
                pdf = pdf_response
                # 这里需要处理验证码
                # TODO: 处理验证码的代码将在此处添加
            else:
                print('未知的PDF Content-Type!')
                print('您可能需要手动检查。')
                err = SciHubAPIError.UNKNOWN
        except Exception as e:
            err = SciHubAPIError.UNKNOWN
            print('获取PDF失败!')
            print('您可能需要手动检查。')
            print(f'错误: {str(e)}')
        
        return pdf, err
    
    def solve_captcha(self, captcha_response):
        """
        处理验证码
        
        参数:
            captcha_response: 包含验证码的响应
            
        返回:
            (pdf_content, error): 解决验证码后的PDF内容和错误信息的元组
        """
        # 获取验证码信息
        captcha_id, captcha_img_url = self.get_captcha_info(captcha_response)
        
        if not captcha_id or not captcha_img_url:
            print('无法获取验证码信息')
            return None, SciHubAPIError.UNKNOWN
        
        print(f'验证码ID: {captcha_id}')
        print(f'验证码图片URL: {captcha_img_url}')
        
        # TODO: 这里需要实现验证码识别或手动输入验证码的逻辑
        # 暂时返回错误，表示需要处理验证码
        return None, SciHubAPIError.BLOCKED_BY_CAPTCHA
    
    def save_pdf(self, pdf_content, filename, save_dir='.'):
        """
        保存PDF文件
        
        参数:
            pdf_content: PDF内容
            filename: 文件名
            save_dir: 保存目录
        """
        if not pdf_content:
            print('没有PDF内容可保存')
            return
        
        # 确保文件名有.pdf后缀
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        
        # 构建保存路径
        save_path = Path(save_dir) / filename
        
        # 保存PDF
        with open(save_path, 'wb') as f:
            f.write(pdf_content)
        
        print(f'PDF已保存为: {save_path.absolute()}')


# 示例用法
if __name__ == "__main__":
    # 创建SciHubAPI实例
    api = SciHubAPI()
    
    # 搜索DOI
    doi = "10.1038/s41586-020-2649-2"  # 示例DOI
    pdf_url, err = api.search(doi)
    
    if err == SciHubAPIError.BLOCKED_BY_CAPTCHA:
        print("需要解决验证码才能继续")
    elif err:
        print(f"搜索出错: {err}")
    else:
        # 获取PDF
        pdf_content, err = api.fetch_pdf(pdf_url)
        
        if err == SciHubAPIError.BLOCKED_BY_CAPTCHA:
            print("需要解决验证码才能继续")
        elif err:
            print(f"获取PDF出错: {err}")
        else:
            # 保存PDF
            api.save_pdf(pdf_content, f"paper_{doi.replace('/', '_')}") 