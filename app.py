#I wrote this script to check the latest PUBG matches for a specific player and posts the results to a Discord channel.    
import requests
import time
import pytz
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
PUBG_API_KEY = os.getenv("PUBG_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

POSTED_MATCHES_FILE = "posted_matches.txt"
# This file keeps track of matches that have already been posted to avoid duplicates.

# === CONFIG ===
TRACKED_PLAYERS = ["Fransbertil", "yooun05", "Dr_StYv", "Fatalityh", "bOYKA2y", "Sibbesinnes", "andreasbeast79", "50-KENT", "Iimp101", "TurboPotat0"]
PLAYER_IDS = {}
PLATFORM = "steam"

HEADERS = {
    "Authorization": f"Bearer {PUBG_API_KEY}",
    "Accept": "application/vnd.api+json"
}

last_match_id = None

def get_player_id(name):
    url = f"https://api.pubg.com/shards/{PLATFORM}/players?filter[playerNames]={name}"
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code != 200:
        raise Exception(f"Failed to fetch player ID for {name}. Status code:  {resp.status_code}, Response: {resp.text}")
    
    data = resp.json()
    return data['data'][0]['id']


def get_recent_matches(player_id, count=5):
    url = f"https://api.pubg.com/shards/{PLATFORM}/players/{player_id}"
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()
    matches = data['data']['relationships']['matches']['data']
    return [m['id'] for m in matches[:count]]


def get_match_info(match_id):
    url = f"https://api.pubg.com/shards/{PLATFORM}/matches/{match_id}"
    resp = requests.get(url, headers=HEADERS)
    data = resp.json()
    return data['data']['attributes']

def get_players_stats(match_id):
    url = f"https://api.pubg.com/shards/{PLATFORM}/matches/{match_id}"
    resp = requests.get(url, headers=HEADERS)
    match_data = resp.json()

    stats_by_name = {}
    for item in match_data['included']:
        if item['type'] == 'participant':
            name = item['attributes']['stats']['name']
            if name in TRACKED_PLAYERS:
                stats_by_name[name] = item['attributes']['stats']
    return stats_by_name


def load_posted_matches():
    try:
        with open(POSTED_MATCHES_FILE, "r") as f:
            # read lines and extract match IDs, ignoring empty lines,otherwise it will post matches that have already been posted
            return set(line.split("|")[0].strip() for line in f if "|" in line)
    except FileNotFoundError:
        return set()   


def save_posted_match(match_id, players_stats, is_win):
    from_zone = pytz.utc
    to_zone = pytz.timezone('Europe/Stockholm')

    # Get local time from match info
    match_info = get_match_info(match_id)
    utc_time = datetime.strptime(match_info['createdAt'], "%Y-%m-%dT%H:%M:%SZ")
    local_time = utc_time.replace(tzinfo=from_zone).astimezone(to_zone)
    formatted_time = local_time.strftime('%Y-%m-%d %H:%M')

    # Gather names of participating tracked players
    participating = [name for name in TRACKED_PLAYERS if name in players_stats]

    outcome = "WIN" if is_win else "LOSS"
    line = f"{match_id} | {formatted_time} | {outcome} -----players -> {', '.join(participating)}\n"

    with open(POSTED_MATCHES_FILE, "a") as f:
        f.write(line)



def post_image_and_stats(match_id, match_info, players_stats):
    from_zone = pytz.utc
    to_zone = pytz.timezone('Europe/Stockholm')

    utc_time = datetime.strptime(match_info['createdAt'], "%Y-%m-%dT%H:%M:%SZ")
    local_time = utc_time.replace(tzinfo=from_zone).astimezone(to_zone)

    with open("battlegrounds.jpg", "rb") as img:
        files = {"file": img}
        requests.post(DISCORD_WEBHOOK_URL, files=files)

    lines = [
        f"**🏆 Winner Winner Chicken Dinner!**",
        f"Match ID: `{match_id}`",
        f"Map: `{match_info['mapName']}`",
        f"Duration: `{match_info['duration'] // 60}:{match_info['duration'] % 60:02d}`",
        f"Mode: `{match_info['gameMode']}`",
        f"Date: `{local_time.strftime('%Y-%m-%d')} at {local_time.strftime('%H:%M')}`"
    ]

   

    participating_stats = []
    for name in TRACKED_PLAYERS:
        stats = players_stats.get(name)
        if stats:
            participating_stats.append((name, stats))

    #sort by kills desc
    participating_stats.sort(key=lambda x: x[1]['kills'], reverse=True)

    #headr row
    header = f"{'Player':>15}  {'Kills':<7} {'Assists':<8} {'Damage':<8}"        
    lines.append("```" + header)
    
    #stats row
    for name, stats in participating_stats:
        line = f"{name:>15}  {stats['kills']:<7} {stats['assists']:<8} {int(stats['damageDealt']):<8}"
        lines.append(line)

    lines.append("```")    


    message = "\n".join(lines)
    requests.post(DISCORD_WEBHOOK_URL, json={"content": message})

def main_loop():
    print("🔄 Tracker started. Monitoring players for Chicken Dinners...")
    global last_match_id
    for name in TRACKED_PLAYERS:
        PLAYER_IDS[name] = get_player_id(name)
        time.sleep(1.7) 

    #last_checked_matches = set()
    posted_matches = load_posted_matches()


    while True:
        try:
            # Get each player's latest match
           recent_match_ids = set()
           for name in TRACKED_PLAYERS:
                match_ids = get_recent_matches(PLAYER_IDS[name])
                for match_id in match_ids:
                    recent_match_ids.add(match_id)
        

            # Check each unique match only once
           for match_id in recent_match_ids:
                if match_id in posted_matches:
                    continue  # already posted or checked

                match_info = get_match_info(match_id)
                players_stats = get_players_stats(match_id)

                # Check if any tracked player won this match
                winner_found = False
                for name, stats in players_stats.items():
                    if stats and stats['winPlace'] == 1:
                        winner_found = True
                        break

                if winner_found:
                    print(f"🏆 Posting match {match_id} - someone won!")
                    post_image_and_stats(match_id, match_info, players_stats)
                else:
                    print(f"Match {match_id} checked — no winner among tracked players.")

                # Record that we’ve already checked this match
                save_posted_match(match_id, players_stats, winner_found)
                posted_matches.add(match_id)


           time.sleep(60)

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        print(f" Script crashed before or during execution: {e}")
        input("Press Enter to close...")


