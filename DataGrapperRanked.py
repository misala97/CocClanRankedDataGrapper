from seleniumbase import SB
from bs4 import BeautifulSoup
import concurrent.futures
import requests
import re
import time
import os
import csv
from datetime import datetime, timedelta

# ==========================================
# EINSTELLUNGEN
# ==========================================
clan_url = "https://clashspot.net/en/clan/2QRC8998U/view"

# Das Datum für die ClashSpot URL (Format: YYYY-MM-DD)
url_date = "2026-05-25"

# --- Automatische Dateinamen-Generierung ---
parsed_date = datetime.strptime(url_date, "%Y-%m-%d")
start_date_obj = parsed_date - timedelta(days=7)

start_datum = start_date_obj.strftime("%d_%m_%Y")
end_datum = parsed_date.strftime("%d_%m_%Y")

filename = f"Ranked_Data_{start_datum}-{end_datum}.csv"
print(f"ℹ️ Zieldatei für diesen Lauf: {filename}")
# ==========================================

def get_weekly_attacks(league_string: str) -> int:
    league_name = league_string.lower().strip()
    if "legend" in league_name:
        if "iii" in league_name or "3" in league_name: return 24
        elif "ii" in league_name or "2" in league_name: return 30
        else: return 56 

    attack_limits = {
        "skeleton": 6, "barbarian": 6, "archer": 8, "wizard": 8, 
        "valkyrie": 10, "witch": 10, "golem": 12, "p.e.k.k.a": 12, 
        "pekka": 12, "titan": 12, "dragon": 14, "electro": 18
    }

    for league, limit in attack_limits.items():
        if league in league_name: return limit
    return 0

# --- Hilfsfunktionen für BeautifulSoup ---
def find_season_stats(soup):
    header = soup.find('h2', class_='o-text-center', string=re.compile("Season"))
    return header.find_next_sibling('p', class_=re.compile('container-row')) if header else None

def find_attack_stats(soup):
    headers = soup.find_all('h3', class_='o-show-flex o-content-v-center o-content-h-sb')
    return headers[0].find_next_sibling('div') if len(headers) > 0 else None

def find_defense_stats(soup):
    headers = soup.find_all('h3', class_='o-show-flex o-content-v-center o-content-h-sb')
    return headers[1].find_next_sibling('div') if len(headers) > 1 else None

def get_stat_value(container, selector_type, selector_val, is_img=False):
    if not container: return 0
    elem = container.find('img', src=re.compile(selector_val)) if is_img else container.find('span', class_=selector_val)
    if elem:
        wrapper = elem.find_parent('span', class_='label')
        if wrapper:
            val = wrapper.find('span', class_='value').get_text(strip=True)
            return int(val) if val.isnumeric() else 0
    return 0

def find_season_stats(soup):
     # 1. Find the main heading for the season
        season_header = soup.find('h2', class_='o-text-center', string=re.compile("Season"))

        if season_header:
            # 2. Find the stats container directly below that header
            # It uses 'container-row' which holds the League, Rank, and Trophies
            stats_container = season_header.find_next_sibling('p', class_=re.compile('container-row'))
            
            if stats_container:
                 return stats_container
            
def find_attack_stats(soup):
     # 1. Find the main heading for the season
        attack_header = soup.find_all('h3',  class_='o-show-flex o-content-v-center o-content-h-sb')[0]

        if attack_header:
            # 2. Find the stats container directly below that header
            # It uses 'container-row' which holds the League, Rank, and Trophies
            stats_container = attack_header.find_next_sibling('div')
            
            if stats_container:
                 return stats_container
            
def find_defense_stats(soup):
     # 1. Find the main heading for the season
        def_header = soup.find_all('h3',  class_='o-show-flex o-content-v-center o-content-h-sb')[1]

        if def_header:
            # 2. Find the stats container directly below that header
            # It uses 'container-row' which holds the League, Rank, and Trophies
            stats_container = def_header.find_next_sibling('div')
            
            if stats_container:
                 return stats_container

def find_total_star_attack_amount(soup):
    attack_containter  = find_attack_stats(soup)
    star_container = attack_containter.find('img', src=re.compile(r'stars\.png'))
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')
        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0

def find_0_star_attack_amount(soup):
    attack_containter  = find_attack_stats(soup)
    star_container = attack_containter.find('span', class_='stars-0')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0

def find_1_star_attack_amount(soup):
    attack_containter  = find_attack_stats(soup)
    star_container = attack_containter.find('span', class_='stars-1')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0
    
def find_2_star_attack_amount(soup):
    attack_containter  = find_attack_stats(soup)
    star_container = attack_containter.find('span', class_='stars-2')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0
    
def find_3_star_attack_amount(soup):
    attack_containter  = find_attack_stats(soup)
    star_container = attack_containter.find('span', class_='stars-3')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0
    
def find_total_star_defense_amount(soup):
    defense_containter  = find_defense_stats(soup)
    star_container = defense_containter.find('img', src=re.compile(r'stars-defense\.png'))
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0

def find_0_star_defense_amount(soup):
    defense_containter  = find_defense_stats(soup)
    star_container = defense_containter.find('span', class_='stars-0')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0

def find_1_star_defense_amount(soup):
    defense_containter  = find_defense_stats(soup)
    star_container = defense_containter.find('span', class_='stars-1')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0
    
def find_2_star_defense_amount(soup):
    defense_containter  = find_defense_stats(soup)
    star_container = defense_containter.find('span', class_='stars-2')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret = wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0
    
def find_3_star_defense_amount(soup):
    defense_containter  = find_defense_stats(soup)
    star_container = defense_containter.find('span', class_='stars-3')
    
    if star_container:
        wrapper_span = star_container.find_parent('span', class_='label')

        ret =  wrapper_span.find('span', class_='value').contents[0].get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0
    
def find_trophies(soup):
    stats_container = find_season_stats(soup)
    trophy_img = stats_container.find('img', src=re.compile(r'trophies\.png'))
    
    if trophy_img:
        wrapper_span = trophy_img.find_parent('span', class_='label')
        ret =  wrapper_span.find('span', class_='value').get_text(strip=True)
        return int(ret) if ret.isnumeric() else 0
    
def find_league_name(soup):
    stats_container = find_season_stats(soup)
    league_img = stats_container.find('img', src=re.compile(r'HomeVillage/League'))
    
    if league_img:
        wrapper_span = league_img.find_parent('span', class_='label')
        ret =  wrapper_span.find('span', class_='value').get_text(strip=True)
        if(ret == "Legend League"):
            league_img = stats_container.find('img', src=re.compile(r'misc/settings'))
            if league_img:
                wrapper_span = league_img.find_parent('span', class_='label')
                ret =  wrapper_span.find('span', class_='value').get_text(strip=True)
        return ret



def find_attacks(soup):
    stats_container = find_season_stats(soup)
    trophy_img = stats_container.find('img', src=re.compile(r'attack\.png'))
    
    if trophy_img:
        wrapper_span = trophy_img.find_parent('span', class_='label')
        ret =  wrapper_span.find('span', class_='value').get_text(strip=True)  
        return int(ret) if ret.isnumeric() else 0   


def find_defs(soup):
    stats_container = find_season_stats(soup)
    trophy_img = stats_container.find('img', src=re.compile(r'defense\.png'))
    
    if trophy_img:
        wrapper_span = trophy_img.find_parent('span', class_='label')
        ret =  wrapper_span.find('span', class_='value').get_text(strip=True)    
        return int(ret) if ret.isnumeric() else 0

def find_current_rank(soup):
    stats_container = find_season_stats(soup)
    i = stats_container.find('i', class_=('fa-ranking-star'))
    
    if i:
        wrapper_span = i.find_parent('span', class_='label')
        ret =  wrapper_span.find('span', class_='value').get_text(strip=True)  
        return int(ret) if ret.isnumeric() else 0                  

def find_attack_table(soup):
    attack_table = soup.find_all('table', class_='table-break-600 table-break-600-c1')[0]

    if attack_table:
        return attack_table

def find_possible_attacks(soup, league):
    return get_weekly_attacks(league)

def find_defense_table(soup):
    def_table = soup.find_all('table', class_='table-break-600 table-break-600-c1')[1]

    if def_table:
        return def_table

def find_possible_defense(soup, league):
    return get_weekly_attacks(league)

# --- Spieler Klasse ---
class PlayerData:
    def __init__(self, name, player_id):
        self.name = name
        self.id = player_id
        self.url = f"https://clashspot.net/en/player/{self.id}/ranked/group/{url_date}"
        self.was_active = False
        self.league_name = "-"
        self.trophies = 0
        self.current_rank = 0
        self.total_attacks = 0
        self.total_defenses = 0
        self.attack_0_star = self.attack_1_star = self.attack_2_star = self.attack_3_star = 0
        self.defense_0_star = self.defense_1_star = self.defense_2_star = self.defense_3_star = 0
        self.attack_total_star = self.defense_total_star = 0
        self.possible_attacks = self.possible_defense = 0
        self.attack_avg = self.defense_avg = 0
        self.attack_judge = self.defense_judge = "" 

    def parse_html(self, html_content):
        soup_page = BeautifulSoup(html_content, 'html.parser')
        if("Page not found" in soup_page.title.text):
             self.was_active  = False
             return
        self.was_active = True
        self.league_name = find_league_name(soup_page);
        self.trophies = find_trophies(soup_page);  
        self.total_attacks = find_attacks(soup_page)
        self.total_defenses = find_defs(soup_page)
        self.current_rank = find_current_rank(soup_page)
        self.attack_0_star = find_0_star_attack_amount(soup_page)
        self.attack_1_star = find_1_star_attack_amount(soup_page)
        self.attack_2_star = find_2_star_attack_amount(soup_page)
        self.attack_3_star = find_3_star_attack_amount(soup_page)
        self.attack_total_star = find_total_star_attack_amount(soup_page)
        self.defense_0_star = find_0_star_defense_amount(soup_page)
        self.defense_1_star = find_1_star_defense_amount(soup_page)
        self.defense_2_star = find_2_star_defense_amount(soup_page)
        self.defense_3_star = find_3_star_defense_amount(soup_page)
        self.defense_total_star = find_total_star_defense_amount(soup_page)
        self.possible_attacks = find_possible_attacks(soup_page, self.league_name)
        self.possible_defense = find_possible_defense(soup_page,  self.league_name)
        self.attack_avg = 0 if self.total_attacks == 0 else self.attack_total_star / self.total_attacks
        self.defense_avg = 0 if self.total_defenses == 0 else self.defense_total_star / self.total_defenses

    # Diese Funktion liefert nun nur noch die Datenliste zurück, anstatt selbst zu speichern
    def get_row_data(self):
        return [
            self.league_name, self.name, self.id, self.was_active, self.total_attacks, self.total_defenses,
            self.trophies, self.current_rank, self.attack_0_star, self.attack_1_star,
            self.attack_2_star, self.attack_3_star, self.attack_total_star,
            self.defense_0_star, self.defense_1_star, self.defense_2_star,
            self.defense_3_star, self.defense_total_star,
            self.possible_attacks, self.possible_defense, self.attack_judge,
            self.defense_judge, self.attack_avg, self.defense_avg
        ]

# --- Multithreading Fetcher Funktion ---
def fetch_and_parse_player(player_obj, session):
    try:
        response = session.get(player_obj.url, timeout=10)
        
        if response.status_code == 200:
            player_obj.parse_html(response.text)
            print(f"✅ Geladen: {player_obj.name}")
            
        elif response.status_code == 404:
            player_obj.was_active = False
            print(f"💤 Inaktiv: {player_obj.name} (404 Page Not Found)")
            
        else:
            print(f"❌ Fehler bei {player_obj.name}: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Timeout/Fehler bei {player_obj.name}: {e}")

# ==========================================
# HAUPT-SKRIPT
# ==========================================
if __name__ == "__main__":
    
    t0 = time.time()
    
    # 1. Selenium holt sich den Cloudflare-Passierschein
    print("Starte Browser für Cloudflare-Bypass...")
    with SB(uc=True, headless=False) as sb:
        sb.driver.get(clan_url)
        sb.sleep(10) # Warten bis CF gelöst ist
        
        html = sb.get_page_source()
        if "clashspot" not in html.lower() or "access denied" in html.lower():
            print("Konnte Cloudflare nicht umgehen. Bitte Skript neu starten.")
            exit()
            
        print("✅ Cloudflare erfolgreich umgangen!")
        
        # 2. Cookies & User-Agent klauen
        selenium_cookies = sb.driver.get_cookies()
        user_agent = sb.driver.execute_script("return navigator.userAgent;")
        
        soup_clan_page = BeautifulSoup(html, 'html.parser')
        player_links = soup_clan_page.find_all('a', href=re.compile(r'/en/player/'))
        
        players_to_scrape = []
        for link in player_links:
            name = link.get_text(strip=True)
            p_id = link.get('href').split('/')[-2]
            players_to_scrape.append(PlayerData(name, p_id))

    print(f"Fange an, {len(players_to_scrape)} Spieler herunterzuladen...")

    # 3. Requests Session mit Selenium Daten füttern
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'])

    # 4. MULTITHREADING (Der Turbo-Modus)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_and_parse_player, p, session) for p in players_to_scrape]
        concurrent.futures.wait(futures)

    # 5. ALLE DATEN AUF EINMAL IN DIE CSV SCHREIBEN (ÜBERSCHREIBEN-MODUS)
    print(f"\nSpeichere Daten in '{filename}' (Alte Daten werden überschrieben)...")
    
    headers = [
        "League Name", "name", "id", "was_active", "total_attacks", "total_defenses", 
        "trophies", "current_rank", "attack_0_star", "attack_1_star", 
        "attack_2_star", "attack_3_star", "attack_total_star", "defense_0_star", 
        "defense_1_star", "defense_2_star", "defense_3_star", "defense_total_star",
        "possible_attacks", "possible_defense", "attack_judge", "defense_judge", 
        "attack_avg", "defense_avg"
    ]
    
    # mode='w' bedeutet "Write" (Überschreiben) statt 'a' für "Append" (Anhängen)
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers) # Header immer zuerst schreiben
        
        # Gehe durch alle gesammelten Spieler und schreibe deren Zeile
        for p in players_to_scrape:
            writer.writerow(p.get_row_data())

    t1 = time.time()
    print(f"🎉 FERTIG! Dauer: {round(t1-t0, 2)} Sekunden.")