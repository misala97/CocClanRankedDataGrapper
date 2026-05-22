import time
import os
from seleniumbase import SB
from bs4 import BeautifulSoup
import re

url = "https://clashspot.net/en/clan/2QRC8998U/war/271658145"

# ==========================================
# HAUPT-SKRIPT
# ==========================================
if __name__ == "__main__":
    
    t0 = time.time()
    
    # 1. Selenium holt sich den Cloudflare-Passierschein
    print("Starte Browser für Cloudflare-Bypass...")
    #with SB(uc=True, headless=True) as sb:
       # sb.driver.get(url)
        #sb.sleep(3) # Etwas länger warten, damit JavaScript die Tabelle lädt
        
        #html = sb.get_page_source()
        
        #if "clashspot" not in html.lower() or "access denied" in html.lower():
            #print("Konnte Cloudflare nicht umgehen. Bitte Skript neu starten.")
           # exit()
            
        #print("✅ Cloudflare erfolgreich umgangen!")
        
        # HTML in eine temporäre Datei schreiben
        #file_path = "clashspot_temp.html"
        #with open(file_path, "w", encoding="utf-8") as f:
        #    f.write(html)
            
        #print(f"💾 HTML wurde erfolgreich in '{file_path}' gespeichert.")
        
        #t1 = time.time()
        #print(f"🎉 FERTIG! Dauer: {round(t1-t0, 2)} Sekunden.")

        # HTML laden
    with open("clashspot_temp.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

        # Suche nach den relevanten Zeilen in der Kriegstabelle
        # ClashSpot nutzt oft 'war-member' Klassen für die Spieler-Container
        players = soup.find_all(class_="members-position")

        for player in players:
            player = player.find(class_="clan1")
            name = player.find(class_="members-position-name").get_text(strip=True)
            th_level = player.find(class_="th-level").get_text(strip=True)
            # Extraktion der Angriffsdaten innerhalb des Containers
            attacks = player.find_all(class_="attack-result")
            
            print(f"Spieler: {name} (TH{th_level})")
            for atk in attacks:
                print(f" - Sterne: {atk.find(class_='stars').text}, Zerstörung: {atk.find(class_='pct').text}")