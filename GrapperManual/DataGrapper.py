from seleniumbase import SB
from bs4 import BeautifulSoup
import pickle
import re
import time
import os
import csv

url = "https://clashspot.net/en/clan/2QRC8998U/view"
date = "2026-04-20"
filename = "Ranked_Data_13_04_2026-20_04_2026.csv"


def get_weekly_attacks(league_string: str) -> int:
    league_name = league_string.lower().strip()
    
    if "legend" in league_name:
        if "iii" in league_name or "3" in league_name:
            return 24
        elif "ii" in league_name or "2" in league_name:
            return 30
        else:
            return 56 

    attack_limits = {
        "skeleton": 6,     # Leagues 1-3
        "barbarian": 6,    # Leagues 4-6 
        "archer": 8,       # Leagues 7-9
        "wizard": 8,       # Leagues 10-12 
        "valkyrie": 10,    # Leagues 13-15
        "witch": 10,       # Leagues 16-18 
        "golem": 12,       # Leagues 19-21
        "p.e.k.k.a": 12,   # Leagues 22-24
        "pekka": 12,       # Alternate spelling just in case
        "titan": 12,       # Leagues 25-27 
        "dragon": 14,      # Leagues 28-30
        "electro": 18      # Leagues 31-33
    }

    for league, limit in attack_limits.items():
        if league in league_name:
            return limit

    # Fallback if no league is matched
    return 0



def load_url(sb, url, seconds):
    print(f"Loading {url}...")
    sb.driver.get(url)
    sb.sleep(seconds)
    html = sb.get_page_source()
    
    if "clashspot" in html.lower() and "access denied" not in html.lower():
        print("Successfully bypassed Cloudflare!")
        
        # Parse with BeautifulSoup just like before
        soup = BeautifulSoup(html, 'html.parser')
        print(f"Page Title: {soup.title.text}")
        return soup
    else:
        print("Failed to bypass. Cloudflare is winning today.")
        return -1

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

def find_possible_attacks(soup):
    return get_weekly_attacks(player.league_name)

def find_defense_table(soup):
    def_table = soup.find_all('table', class_='table-break-600 table-break-600-c1')[1]

    if def_table:
        return def_table

def find_possible_defense(soup):
    return get_weekly_attacks(player.league_name)

class PlayerData:
    name = ""
    id = ""
    url = ""
    sb = None
    was_active = False
    total_attacks = 0
    league_name = ""
    total_defenses  = 0
    trophies = 0
    current_rank = 0
    attack_0_star = 0
    attack_1_star = 0
    attack_2_star = 0
    attack_3_star = 0
    #attack_total_star = 0
    defense_0_star = 0
    defense_1_star = 0
    defense_2_star = 0
    defense_3_star = 0
    #defense_total_star = 0
    soup_page = ""
    possible_attacks = 0
    possible_defense = 0
    attack_avg = 0
    defense_avg = 0

    def __init__(self, name, id, sb):
        self.name = name
        self.id = id
        self.was_active = False
        self.url = "https://clashspot.net/en/player/"+ self.id+"/ranked/group/" + date
        self.sb = sb
        self.load_soup_real()
        #self.load_soup_fake()

    def load_soup_real(self):
        self.soup_page = load_url(self.sb, self.url, 0)

    def load_soup_fake(self):
        with open('soup_player_page.pickle', 'rb') as f:
            self.soup_page = pickle.load(f)

    def load_data(self):
        if("Page not found" in self.soup_page.title.text):
             self.was_active  = False
             return
        self.was_active = True
        self.league_name = find_league_name(self.soup_page);
        self.trophies = find_trophies(self.soup_page);  
        self.total_attacks = find_attacks(self.soup_page)
        self.total_defenses = find_defs(self.soup_page)
        self.current_rank = find_current_rank(self.soup_page)
        self.attack_0_star = find_0_star_attack_amount(self.soup_page)
        self.attack_1_star = find_1_star_attack_amount(self.soup_page)
        self.attack_2_star = find_2_star_attack_amount(self.soup_page)
        self.attack_3_star = find_3_star_attack_amount(self.soup_page)
        #self.attack_total_star = find_total_star_attack_amount(self.soup_page)
        self.defense_0_star = find_0_star_defense_amount(self.soup_page)
        self.defense_1_star = find_1_star_defense_amount(self.soup_page)
        self.defense_2_star = find_2_star_defense_amount(self.soup_page)
        self.defense_3_star = find_3_star_defense_amount(self.soup_page)
        #self.defense_total_star = find_total_star_defense_amount(self.soup_page)
        self.possible_attacks = find_possible_attacks(self.soup_page)
        self.possible_defense = find_possible_defense(self.soup_page)
        self.attack_avg = 0 if self.total_attacks == 0 else self.attack_total_star / self.total_attacks
        self.defense_avg = 0 if self.total_defenses == 0 else self.defense_total_star / self.total_defenses

    def log_to_csv(self):
        headers = [
            "League Name", "name", "id", "was_active", "total_attacks", "total_defenses", 
            "trophies", "current_rank", "attack_0_star", "attack_1_star", 
            "attack_2_star", "attack_3_star","defense_0_star", "defense_1_star", "defense_2_star", 
            "defense_3_star", "possible_attacks", "possible_defense","attack_avg", "defense_avg"
        ]
        
        row_data = [
            self.league_name, self.name, self.id, self.was_active, self.total_attacks, self.total_defenses,
            self.trophies, self.current_rank, self.attack_0_star, self.attack_1_star,
            self.attack_2_star, self.attack_3_star, self.attack_total_star,
            self.defense_0_star, self.defense_1_star, self.defense_2_star,
            self.defense_3_star, self.defense_total_star,
            self.possible_attacks, self.possible_defense, self.attack_judge,
            self.defense_judge, self.attack_avg, self.defense_avg
        ]
        

        file_exists = os.path.isfile(filename)
        
        with open(filename, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow(headers)
                
            writer.writerow(row_data)








# The 'uc=True' flag tells it to use Undetected mode to bypass Cloudflare
# Set headless=True if you want it to run invisibly in the background
with SB(uc=True, headless=True) as sb:
    soup_clan_page = load_url(sb, url, 10)

    print(soup_clan_page.title.text)

    player_links = soup_clan_page.find_all('a', href=re.compile(r'/en/player/'))

    t0 = time.time()

    for player in player_links:
        player = PlayerData(player.get_text(strip=True), player.get('href').split('/')[-2], sb)
        

        player.load_data()

        print("--------------")
        print("Name: " + player.name)
        print("Active: " + str(player.was_active))
        print("Rank: " + str(player.current_rank))
        print("League Name: " + player.league_name)
        print(get_weekly_attacks(player.league_name))
        
        player.log_to_csv();


    
    t1 = time.time()
    print("Time: " + str(t1-t0))