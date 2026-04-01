import arxiv
import re
import json

class Arxiv:
    def __init__(self):
        pass

    @staticmethod
    def search_arxiv_and_download(entry):
        """
        尝试从arXiv搜索并下载论文。
        首先检查eprint字段，然后尝试通过标题和作者搜索。
        """
        arxiv_id = None
        # 检查 BibTeX 条目中是否直接提供了 arXiv ID
        if entry.get('archiveprefix', '').lower() == 'arxiv' and entry.get('eprint'):
            arxiv_id = entry['eprint']
            print(f"  [INFO] 从BibTeX条目中找到arXiv ID: {arxiv_id}")
        elif entry.get('eprint') and 'arxiv' in entry.get('eprint', '').lower(): # 有些条目直接在eprint里写 arXiv:xxxx
            match = re.search(r'arxiv[:\s]*([\d\.]+v?\d*)', entry['eprint'], re.IGNORECASE)
            if match:
                arxiv_id = match.group(1)
                print(f"  [INFO] 从BibTeX eprint字段中解析到arXiv ID: {arxiv_id}")

        title = entry.get('title', '')

        if arxiv_id:
            search_term = arxiv_id
            print(f"  [INFO] 使用arXiv ID进行搜索: {search_term}")
            try:
                # 使用 id_list 参数进行精确搜索
                search = arxiv.Search(id_list=[search_term], max_results=1)
                paper = next(search.results(), None)
            except Exception as e:
                print(f"  [WARN] arXiv ID搜索失败: {e}")
                paper = None
        elif title:
            # 如果没有直接的ID，则组合标题和作者进行搜索
            query = f'ti:"{title}"'

            year = entry.get('year', '')
            if year:
                start_date_str = f"{year}01010000" # 年月日时分
                end_date_str = f"{year}12312359"   # 年月日时分
                query += f" AND submittedDate:[{start_date_str} TO {end_date_str}]"

            search_term = query
            print(f"  [INFO] 使用标题在arXiv上搜索: {search_term[:70]}...")
            try:
                search = arxiv.Search(query=search_term, max_results=3) # 获取前几个结果，选择最匹配的
                # 简单的匹配逻辑：选择第一个结果。更复杂的可能需要比较标题相似度。
                paper = next(search.results(), None)
                if paper and title.lower() not in paper.title.lower(): # 基本的标题匹配检查
                    print(f"  [WARN] arXiv返回的第一个结果标题 '{paper.title}' 与目标标题 '{title}' 差异较大，可能不匹配。")
            except Exception as e:
                print(f"  [WARN] arXiv API 搜索失败: {e}")
                paper = None
        else:
            print("  [INFO] 缺少arXiv ID和标题，无法在arXiv上搜索。")
            return False

        if paper and paper.pdf_url:
            print(f"  [INFO] arXiv找到PDF链接: {paper.pdf_url} (标题: {paper.title})")
            
            return paper.pdf_url
        elif paper:
            print(f"  [WARN] arXiv找到论文 '{paper.title}' 但未找到PDF链接。")
        else:
            print("  [INFO] 未在arXiv上找到匹配的论文。")
        return False

    @staticmethod
    def get_arxiv_list_by_title(title):
        """
        尝试从arXiv搜索并下载论文。
        首先检查eprint字段，然后尝试通过标题和作者搜索。
        """
        search_term = f'ti:"{title}"'
        print(f"  [INFO] 使用标题在arXiv上搜索: {search_term[:70]}...")
        try:
            # 使用 id_list 参数进行精确搜索
            search = arxiv.Search(query=search_term, max_results=3)
            paper = next(search.results(), None)
        except Exception as e:
            print(f"  [WARN] arXiv ID搜索失败: {e}")
            paper = None

        results = []

        if paper:
            for paper in search.results():
                paper_dict = {
                    "entry_id": paper.entry_id,
                    "updated": str(paper.updated),
                    "published": str(paper.published),
                    "title": paper.title,
                    "authors": [author.name for author in paper.authors],
                    "doi": paper.doi,
                    "links": [link.href for link in paper.links],
                    "pdf_url": paper.pdf_url
                }
                results.append(paper_dict)

                results_json = json.dumps(results, indent=4)
                return results_json
        else:
            print("  [INFO] 未在arXiv上找到匹配的论文。")
        return None

    @staticmethod
    def get_arxiv_pdf(id):
        """
        尝试从arXiv搜索并下载论文。
        首先检查eprint字段，然后尝试通过标题和作者搜索。
        """
        search_term = id
        print(f"  [INFO] 使用arXiv ID进行搜索: {search_term}")
        try:
            # 使用 id_list 参数进行精确搜索
            search = arxiv.Search(id_list=[search_term], max_results=1)
            paper = next(search.results(), None)
        except Exception as e:
            print(f"  [WARN] arXiv ID搜索失败: {e}")
            paper = None

        if paper and paper.pdf_url:
            print(f"  [INFO] arXiv找到PDF链接: {paper.pdf_url} (标题: {paper.title})")
            
            return paper.pdf_url
        elif paper:
            print(f"  [WARN] arXiv找到论文 '{paper.title}' 但未找到PDF链接。")
        else:
            print("  [INFO] 未在arXiv上找到匹配的论文。")
        return False