import os
import re
import time
import requests
# pyrefly: ignore [missing-import]
from bs4 import BeautifulSoup

WIKI_API = "https://genshin-impact.fandom.com/api.php"
BASE_DIR = "genshin_wiki_full_tree"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

WIKI_TREE = {
    "Characters/Playable": ["Category:Playable Characters"],
    "Characters/NPCs": ["Category:NPCs"],
    "Characters/Factions": ["Category:Factions"],
    "Items/Weapons": ["Category:Weapons"],
    "Items/Artifacts": ["Category:Artifacts"],
    "Items/Materials": ["Category:Materials", "Category:Character Ascension Materials", "Category:Talent Level-Up Materials"],
    "Lore/Quests": ["Category:Quests"],
    "Lore/Books_and_Letters": ["Category:Books"]
}

def sanitize_filename(name):
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean.strip()[:90]

def parse_html_with_tables_and_images(raw_html):
    if not raw_html:
        return ""
    
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # 1. Bỏ sạch mục lục ToC (mấy cái 1.1, 1.2 vô dụng) và các script/style
    for trash in soup.find_all(["script", "style", "nav", "aside", "noscript", "div#toc", "ul.toc"]):
        trash.decompose()
    for toc in soup.find_all(class_=re.compile(r"toc|navigation|mw-jump-link")):
        toc.decompose()
        
    # 2. Thay thế toàn bộ <img> bằng text trong 'alt' hoặc 'title' (để lấy tên Mora, Item, Icon...)
    for img in soup.find_all("img"):
        item_name = img.get("alt") or img.get("data-image-name") or img.get("title") or ""
        # Dọn đuôi file .png, .jpg nếu có
        item_name = re.sub(r"\.(png|jpg|jpeg|webp)$", "", item_name, flags=re.I).strip()
        if item_name and not any(x in item_name.lower() for x in ["icon", "ui", "site"]):
            img.replace_with(f" [{item_name}] ")
        else:
            img.decompose()
            
    # 3. Format lại thẻ table thành dạng text dễ đọc cho LLM
    for table in soup.find_all("table"):
        rows_text = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(separator=" ").strip() for c in tr.find_all(["th", "td"])]
            cells = [re.sub(r"\s+", " ", c) for c in cells if c]
            if cells:
                rows_text.append(" | ".join(cells))
        if rows_text:
            table_block = "\n" + "\n".join(rows_text) + "\n"
            table.replace_with(table_block)
            
    # 4. Thay thẻ ngắt dòng
    for br in soup.find_all(["br", "p", "h1", "h2", "h3", "h4", "li"]):
        br.replace_with(f"\n{br.get_text().strip()}")
        
    text = soup.get_text()
    # Dọn khoảng trắng dư thừa
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def get_pages_from_category(cat_title, session):
    pages = []
    cm_continue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": cat_title,
            "cmlimit": "100",
            "cmnamespace": "0",
            "format": "json"
        }
        if cm_continue:
            params["cmcontinue"] = cm_continue
            
        try:
            res = session.get(WIKI_API, params=params, headers=HEADERS, timeout=15)
            data = res.json()
            members = data.get("query", {}).get("categorymembers", [])
            for m in members:
                pages.append(m["title"])
                
            if "continue" in data and "cmcontinue" in data["continue"]:
                cm_continue = data["continue"]["cmcontinue"]
                time.sleep(0.2)
            else:
                break
        except Exception as e:
            print(f"Lỗi fetch {cat_title}: {e}")
            break
    return pages

def crawl_rich_data():
    session = requests.Session()
    session.headers.update(HEADERS)
    os.makedirs(BASE_DIR, exist_ok=True)
    
    total = 0
    for sub_path, categories in WIKI_TREE.items():
        folder = os.path.join(BASE_DIR, sub_path)
        os.makedirs(folder, exist_ok=True)
        
        print(f"\n[*] Đang cào: {sub_path}...")
        all_titles = set()
        for cat in categories:
            all_titles.update(get_pages_from_category(cat, session))
            
        print(f" -> Có {len(all_titles)} bài.")
        for idx, title in enumerate(all_titles, 1):
            file_name = f"{sanitize_filename(title)}.txt"
            file_path = os.path.join(folder, file_name)
            
            try:
                parse_params = {
                    "action": "parse",
                    "page": title,
                    "prop": "text|langlinks",
                    "format": "json"
                }
                res = session.get(WIKI_API, params=parse_params, timeout=15)
                if res.status_code != 200:
                    continue
                    
                data = res.json().get("parse", {})
                raw_html = data.get("text", {}).get("*", "")
                
                # Bóc tách giữ cả table + tên icon
                content_text = parse_html_with_tables_and_images(raw_html)
                if len(content_text) < 50:
                    continue
                    
                langlinks = data.get("langlinks", [])
                vi_name = "N/A"
                for ll in langlinks:
                    if ll.get("lang") == "vi":
                        vi_name = ll.get("*", "")
                        break
                        
                full_doc = (
                    f"Title: {title}\n"
                    f"Vietnamese Name: {vi_name}\n"
                    f"Category: {sub_path}\n"
                    f"{'='*50}\n\n"
                    f"{content_text}"
                )
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(full_doc)
                    
                total += 1
                if idx % 10 == 0 or idx == len(all_titles):
                    print(f"   [{idx}/{len(all_titles)}] Đã lưu: {title}")
                time.sleep(0.3)
            except Exception as e:
                print(f"Lỗi bài {title}: {e}")
                time.sleep(1)

    print(f"\n[DONE] Đã cào xong {total} bài đầy đủ chỉ số & nguyên liệu!")

if __name__ == "__main__":
    crawl_rich_data()