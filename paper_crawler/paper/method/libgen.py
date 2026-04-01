from libgen_api import LibgenSearch
s = LibgenSearch()

class SciHUB:
    def __init__(self):
        pass
        
    @staticmethod
    def get_libgen_pdf_url_by_title(query):
        """尝试通过SCIHUB API查找PDF URL"""
        try:
            results = s.search_title(query)
            print(results)
            for paper in results['papers']:
                return paper['url']
        except Exception as e:
            print(f"  [WARN] SCIHUB响应失败: {e}")
        return None