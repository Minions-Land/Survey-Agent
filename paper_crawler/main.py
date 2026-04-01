import os
import sys
import time

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from paper.filter_agent import FilterAgent
from paper.method.arxiv import Arxiv
from paper.method.unpaywall import Unpaywall
from paper.utils.download import Download
from paper.utils.files import Files

# BIB_FILE_PATH = "./reference.bib"
# DOWNLOAD_FOLDER = "downloaded_papers"


def paper_crawler(BIB_FILE_PATH: str, DOWNLOAD_FOLDER: str):
    downloaded_paper_title_list = []
    downloaded_paper_key_list = []
    downloaded_paper_information = {}
    downloaded_paper_information_bib = {}
    api_parsing_method = ''
    all_paper_num = None
    batch_paper_id = None
    batch_downloaded_paper_list = None
    batch_paper_title_list = None

    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    tmp_id = []  # Store IDs for successfully downloaded papers.
    tmp_paper = []  # Store paper objects for successfully downloaded papers.

    try:
        with open(BIB_FILE_PATH, 'r', encoding='utf-8') as bibtex_file:
            bib_database = bibtexparser.load(bibtex_file)
            all_paper_num = len(bib_database.entries)
    except FileNotFoundError:
        print(f"[ERROR] BibTeX file not found: {BIB_FILE_PATH}")
        return
    except Exception as e:
        print(f"[ERROR] Failed to parse BibTeX file: {e}")
        return

    print(f"Found {len(bib_database.entries)} entries in total.")
    download_count = 0
    failed_downloads = []

    # Start numbering from the current amount of downloaded papers.
    start_num = len(downloaded_paper_title_list)

    for i, entry in enumerate(bib_database.entries):
        print(f"\n--- Processing entry {i + 1}/{len(bib_database.entries)}: {entry.get('ID', 'Unknown ID')} ---")
        title = entry.get('title', '')
        authors_raw = entry.get('author', '')
        authors = [name.strip() for name in authors_raw.split(' and ')] if authors_raw else []
        doi = entry.get('doi')
        url_bib = entry.get('url')  # URL field from the BibTeX entry.
        file_key = entry.get('ID', Files.sanitize_filename(title[:50] if title else 'untitled'))

        print(f"  Title: {title[:70]}..." if title else "  Title: Not provided")
        print(
            f"  Authors: {', '.join(authors[:2])}{' et al.' if len(authors) > 2 else ''}"
            if authors else "  Authors: Not provided"
        )
        print(f"  DOI: {doi}" if doi else "  DOI: Not provided")
        print(f"  URL (from bib): {url_bib}" if url_bib else "  URL (from bib): Not provided")

        pdf_found_and_downloaded = False

        if url_bib and url_bib.lower().endswith('.pdf'):
            print("  [ATTEMPT] Trying the direct PDF URL from BibTeX...")
            if (api_parsing_method == 'file') or (not api_parsing_method):
                if Download.download_pdf(url_bib, f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                    pdf_found_and_downloaded = True
            else:
                if Download.download_zip(url_bib, f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                    pdf_found_and_downloaded = True

        if not pdf_found_and_downloaded and (title or entry.get('elogging.info')):
            print("  [ATTEMPT] Trying arXiv search...")
            arxiv_pdf_url = Arxiv.search_arxiv_and_download(entry)
            if arxiv_pdf_url:
                if (api_parsing_method == 'file') or (not api_parsing_method):
                    if Download.download_pdf(arxiv_pdf_url, f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                        pdf_found_and_downloaded = True
                else:
                    if Download.download_zip(arxiv_pdf_url, f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                        pdf_found_and_downloaded = True

        if not pdf_found_and_downloaded and doi:
            print("  [ATTEMPT] Trying the Unpaywall API...")
            unpaywall_pdf_url = Unpaywall.get_unpaywall_url_by_doi(doi)
            if unpaywall_pdf_url:
                if (api_parsing_method == 'file') or (not api_parsing_method):
                    if Download.download_pdf(unpaywall_pdf_url, f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                        pdf_found_and_downloaded = True
                else:
                    if Download.download_zip(unpaywall_pdf_url, f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                        pdf_found_and_downloaded = True

            time.sleep(1)

        if not pdf_found_and_downloaded and title and not doi:
            import json

            print("  [ATTEMPT] Trying Unpaywall title search...")
            filter_agent = FilterAgent()

            data = Unpaywall.get_unpaywall_search_result_by_title(title)

            res = json.loads(filter_agent.run(entry, data))
            if res['status']:
                if (api_parsing_method == 'file') or (not api_parsing_method):
                    if Download.download_pdf(res['value'], f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                        pdf_found_and_downloaded = True
                else:
                    if Download.download_zip(res['value'], f"paper_{(start_num + download_count):03}", DOWNLOAD_FOLDER):
                        pdf_found_and_downloaded = True
            time.sleep(1)

        # if not pdf_found_and_downloaded and title and False:
        #     print("  [ATTEMPT] Trying Google Scholar search...")
        #     scholar_pdf_url = GoogleScholar.search_google_scholar(title, authors)
        #     if scholar_pdf_url:
        #         if Download.download_pdf(scholar_pdf_url, title, DOWNLOAD_FOLDER):
        #             pdf_found_and_downloaded = True
        #     time.sleep(2)

        if pdf_found_and_downloaded:
            if batch_paper_title_list:
                downloaded_paper_title_list.append(batch_paper_title_list[i])
            else:
                downloaded_paper_title_list.append(title)

            downloaded_paper_key_list.append(file_key)

            if batch_paper_id:
                tmp_id.append(batch_paper_id[i])

            if batch_downloaded_paper_list:
                tmp_paper.append(batch_downloaded_paper_list[i])

            # Store full BibTeX info for locally downloaded files.
            db = BibDatabase()
            db.entries = [entry]
            writer = BibTexWriter()
            downloaded_paper_information[f"paper_{(start_num + download_count):03}.pdf"] = writer.write(db)

            # Store filtered BibTeX info for citation/database usage.
            tmp_dict = {}
            for key in entry.keys():
                if key in ['ENTRYTYPE', 'ID', 'author', 'title', 'year', 'volume', 'publisher', 'pages', 'number', 'journal', 'booktitle', 'organization', 'isbn']:
                    tmp_dict[key] = entry[key]

            db = BibDatabase()
            db.entries = [tmp_dict]
            writer = BibTexWriter()
            downloaded_paper_information_bib[f"paper_{(start_num + download_count):03}.pdf"] = writer.write(db)

            download_count += 1  # Increase the successful download counter.

            if len(downloaded_paper_title_list) >= all_paper_num:
                print("The expected number of papers has been downloaded.")
                break

        else:
            print(f"  [FAIL] Could not download paper: {file_key} ({title[:50]}...)")
            failed_downloads.append(f"{file_key} ({title[:50]}...) - DOI: {doi if doi else 'N/A'}")

        print("-" * 30)
        time.sleep(1)  # Pause briefly between requests to avoid sending them too frequently.

    # Keep only the IDs and papers that were actually downloaded.
    if batch_paper_id:
        for idx, paper_id in enumerate(batch_paper_id):
            if paper_id not in tmp_id:
                del batch_paper_id[idx]

    if batch_downloaded_paper_list:
        for idx, paper in enumerate(batch_downloaded_paper_list):
            if paper not in tmp_paper:
                del batch_downloaded_paper_list[idx]

    print("\n--- Download summary ---")
    print(f"Successfully downloaded {download_count} papers.")
    if failed_downloads:
        print(f"Failed to download {len(failed_downloads)} papers:")
        for item in failed_downloads:
            print(f"  - {item}")
        return
    else:
        print("All available download attempts have been completed.")
        return



if __name__ =='__main__':
    paper_crawler("./reference.bib",
                  "./output")