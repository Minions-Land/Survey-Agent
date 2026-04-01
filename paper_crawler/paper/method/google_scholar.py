#import scholarly
from scholarly import scholarly
from scholarly import ProxyGenerator

pg = ProxyGenerator()
pg.FreeProxies()
scholarly.use_proxy(pg)

class GoogleScholar:
    def __init__(self):
        pass

    @staticmethod
    def search_google_scholar(title, authors):
        """在Google Scholar上搜索论文并尝试找到PDF链接"""
        query = f"{title} {' '.join(authors) if authors else ''}"
        print(f"  [INFO] 正在搜索 Google Scholar: {query[:50]}...")
        try:
            search_query = scholarly.search_pubs(query)
            publication = next(search_query, None)
            if publication and 'pub_url' in publication: # 有时直接是PDF链接
                if publication['pub_url'].lower().endswith('.pdf'):
                    print(f"  [INFO] Google Scholar 找到直接PDF链接: {publication['pub_url']}")
                    return publication['pub_url']
            if publication and 'eprint_url' in publication: # eprint_url 通常是PDF
                print(f"  [INFO] Google Scholar 找到 eprint 链接: {publication['eprint_url']}")
                return publication['eprint_url']
        except Exception as e:
            print(f"  [WARN] Google Scholar 搜索失败: {e}")
        return None