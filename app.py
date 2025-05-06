from flask import Flask, jsonify, render_template, request, send_from_directory
import requests
import brotli
import json
import re
import os

app = Flask(__name__, static_folder='.')

api_key = 'ts-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjbGllbnQiOiJwaXQiLCJ2aXAiOmZhbHNlLCJjbGllbnRfdHlwZXMiOlsibmZsX25jYWEiXSwiaWF0IjoxNzQ2MjAzNzUxLCJleHAiOjE3NDY1NDkzNTEsImlkIjoiNjgxNGY0Njc1NzFkNDQ1ODE2YTVkYzUxIn0.KALaez4Ac3IxIiuEcJGCvo4A4w-qfprqat8Yl11tCUI'

# Serve your HTML file
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# Proxy for schedules
@app.route('/api/schedule')
def get_schedule():
    season = request.args.get('season')
    url = f"https://wire.telemetry.fm/ncaa/schedules/by-season?season={season}"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    r = requests.get(url, headers=headers)
    if r.headers.get("Content-Encoding") == "br":
        decoded = brotli.decompress(r.content)
        return jsonify(json.loads(decoded))
    return jsonify(r.json())



# Proxy for game plays
@app.route('/api/game')
def get_game():
    game_id = request.args.get('game_id')
    print(f"HERE: gameID = {game_id}")
    
    url = "https://wire.telemetry.fm/ncaa/plays/game-id"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    params = {'game_id': game_id}

    try:
        from io import BytesIO

        stream = BytesIO()
        chunk_size = 1024 * 5  # 5KB

        with requests.get(url, params=params, headers=headers, stream=True) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=chunk_size):
                stream.write(chunk)

        stream.seek(0)
        data = json.load(stream)
        
        return jsonify(data)

    except requests.RequestException as e:
        return jsonify({'error': 'Request failed', 'details': str(e)}), 500
    except json.JSONDecodeError as e:
        return jsonify({'error': 'Invalid JSON response', 'details': str(e)}), 502



# Extract data from the game data to display
def extract_play_overview(row):
    custom = row.get('custom', {})
    pff    = custom.get('pff', {}) if custom else {}

    return {
        "Play Number": row.get('play_number'),
        "Quarter":     row.get('quarter'),
        "Game Clock":  row.get('game_clock')  or  pff.get('clock'),
        "Down":        pff.get('down'),
        "Yards to Go": row.get('yards_to_go') or pff.get('distance'),
        "Play Type":   row.get('play_type'),
        "Scoring":     row.get('is_scoring') if row.get('is_scoring') is not None else "No",
        "Offense":     row.get('offense')      or  pff.get('offense'),
        "Defense":     row.get('defense')      or  pff.get('defense'),
    }



@app.route('/get_game_details')
def get_game_details():
    game_id = request.args.get('game_id')
    if not game_id:
        return "Missing 'game_id' parameter", 400

    
    os.makedirs('Downloaded_Games', exist_ok=True)
    file_path = os.path.join('Downloaded_Games', f'{game_id}.json')

    if os.path.exists(file_path):
        # Read data from the file
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    else:
        # Fetch data from the API
        try:
            resp = requests.get(f"http://localhost:5000/api/game?game_id={game_id}")
            resp.raise_for_status()
            raw_data = resp.json()
        except requests.RequestException as e:
            return f"Error fetching game details: {e}", 500

        # Ensure it’s actually a list
        if not isinstance(raw_data, list):
            return "Unexpected data format from API", 500

        # Write raw data to a file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=4)

    # Transform each play into the flat overview form
    overview_list = [extract_play_overview(play) for play in raw_data]

    overview_list.sort(
        key=lambda p: (
            p["Quarter"],
            -clock_to_seconds(p["Game Clock"])
        )
    )

    # Pass the flattened list to the template
    return render_template(
        'display_game_details.html',
        game_id=game_id,
        data=overview_list
    )


# New report‐creation stub
@app.route('/api/report', methods=['POST'])
def create_report():
    data = request.get_json()
    game_id   = data.get('game_id')
    play_id   = data.get('play_id')
    player_id = data.get('player_id')

    # Debug print
    print(f"CREATE REPORT CALLED → game_id:{game_id}, play_id:{play_id}, player_id:{player_id}")

    # Placeholder response
    return jsonify({"status": "ok", "received": data}), 200



def clock_to_seconds(clock_str):
    """
    Convert a string "MM:SS" (or "M:SS") into total seconds as an integer.
    If clock_str is None or malformed, return -1 so it sorts last.
    """
    if not clock_str or not re.match(r'^\d+:\d\d$', clock_str):
        return -1
    minutes, seconds = map(int, clock_str.split(':'))
    return minutes * 60 + seconds


if __name__ == '__main__':
    app.run(debug=True)
