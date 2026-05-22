import requests
import csv
import os

# ==========================================
# DEINE EINSTELLUNGEN HIER EINTRAGEN
# ==========================================
API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6ImEyNDBjMzU0LWJhYmItNGQwMy04NmYzLWE1MGQzOWJhNWU2ZSIsImlhdCI6MTc3ODk3NDE2Mywic3ViIjoiZGV2ZWxvcGVyL2Y4ZDhiMGI5LTM4NDUtODRiMy05OWJiLTBmNDA4Zjc0ZTcyMCIsInNjb3BlcyI6WyJjbGFzaCJdLCJsaW1pdHMiOlt7InRpZXIiOiJkZXZlbG9wZXIvc2lsdmVyIiwidHlwZSI6InRocm90dGxpbmcifSx7ImNpZHJzIjpbIjg0LjE0Ny4xMTUuMjE0Il0sInR5cGUiOiJjbGllbnQifV19.6XGUWHQORvW76e70lrR-EQPwnvlalrJ_ecfM3eaP4LwP8c-60KCpS7iD-FcEELkM4BPuDJdmwUYa3UBHCfn2Sg"
CLAN_TAG = "#2QRC8998U"  # Ersetze das mit dem Tag deines Clans (inklusive #)
# ==========================================

def format_coc_date(date_string):
    # CoC API gibt Daten im Format "20260515T070000.000Z" zurück
    # Wir wandeln das in "15_05_2026" um
    year = date_string[0:4]
    month = date_string[4:6]
    day = date_string[6:8]
    return f"{day}_{month}_{year}"

def fetch_raid_data():
    safe_tag = CLAN_TAG.replace("#", "%23")
    url = f"https://api.clashofclans.com/v1/clans/{safe_tag}/capitalraidseasons"
    
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Accept": "application/json"
    }

    print(f"Frage Raid-Daten für Clan {CLAN_TAG} ab...")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"❌ Fehler bei der API-Abfrage: Code {response.status_code}")
        print(response.text)
        return

    data = response.json()
    
    if 'items' not in data or len(data['items']) == 0:
        print("❌ Keine Raid-Historie für diesen Clan gefunden.")
        return

    seasons = data['items']
    print(f"Gefundene Raid-Wochenenden in der API: {len(seasons)}")
    
    new_files_created = 0

    # Gehe durch ALLE gefundenen Wochenenden (die API liefert meist ca. 20 historische Einträge)
    for season in seasons:
        start_date = format_coc_date(season['startTime'])
        end_date = format_coc_date(season['endTime'])
        filename = f"Raid_Data_{start_date}-{end_date}.csv"
        
        # 1. PRÜFUNG: Gibt es die CSV für diese Woche schon?
        if os.path.exists(filename):
            print(f"⏩ Überspringe '{filename}' (existiert bereits)")
            continue # Springt direkt zur nächsten Woche in der Schleife

        # 2. Falls nicht vorhanden, Daten verarbeiten
        members = season.get('members', [])
        
        if not members:
            print(f"ℹ️ Überspringe '{filename}' (keine Angriffe getätigt)")
            continue

        # 3. Neue CSV Datei erstellen und speichern
        with open(filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            # Kopfzeile schreiben
            writer.writerow(['name', 'tag', 'attacks_done', 'possible_attacks', 'gold_looted'])
            
            # Spieler-Daten schreiben
            for member in members:
                name = member.get('name', 'Unbekannt')
                tag = member.get('tag', '')
                
                attacks_done = member.get('attacks', 0)
                attack_limit = member.get('attackLimit', 5)
                bonus_limit = member.get('bonusAttackLimit', 0)
                possible_attacks = attack_limit + bonus_limit
                
                gold_looted = member.get('capitalResourcesLooted', 0)
                
                writer.writerow([name, tag, attacks_done, possible_attacks, gold_looted])

        print(f"✅ Neu erstellt: '{filename}' ({len(members)} Spieler)")
        new_files_created += 1

    print(f"\n🎉 Fertig! {new_files_created} neue CSV-Dateien wurden heruntergeladen.")

if __name__ == "__main__":
    fetch_raid_data()