import json, os, time
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ny2025-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

PLAYERS = {} # name -> {sid, avatar, team_id, is_admin}
TEAMS = {} # team_id -> {members: [names], score}
DISABLED_CELLS = set()
ACTIVE_QUESTION = {'category': None, 'price': 0, 'team_id': None}

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/lobby')
def lobby(): 
    return render_template('lobby.html')

@app.route('/game')
def game(): 
    return render_template('board.html')

@app.route('/questions')
def get_questions():
    try:
        with open('questions.json', 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    except: 
        return jsonify({"categories": []})

def get_all_admin_sids():
    """Возвращает список всех SID админов"""
    return [p['sid'] for p in PLAYERS.values() if p.get('is_admin')]

def broadcast_lobby():
    teams_data = {}
    for tid, t in TEAMS.items():
        teams_data[tid] = {
            'members': t['members'],
            'score': t['score']
        }
    
    players_data = {}
    for name, p in PLAYERS.items():
        players_data[name] = {
            'avatar': p['avatar'],
            'team_id': p.get('team_id'),
            'is_admin': p.get('is_admin', False)
        }
    
    socketio.emit('lobby_update', {
        'players': players_data,
        'teams': teams_data,
        'admin_sids': get_all_admin_sids()
    })

def broadcast_game():
    """Отправляет данные на игровое поле"""
    teams_data = {}
    for tid, t in TEAMS.items():
        team_name, team_avatar = get_team_name_and_avatar(tid)
        teams_data[tid] = {
            'name': team_name,
            'avatar': team_avatar,
            'score': t['score']
        }
    
    admins_data = []
    for name, p in PLAYERS.items():
        if p.get('is_admin'):
            admins_data.append({
                'name': name,
                'avatar': p['avatar']
            })
    
    socketio.emit('game_update', {
        'teams': teams_data,
        'admins': admins_data,
        'disabled_cells': list(DISABLED_CELLS),
        'admin_sids': get_all_admin_sids()
    })

def get_team_name_and_avatar(team_id):
    """Определяет название и аватар команды по преобладающему аватару игроков"""
    team = TEAMS[team_id]
    avatars = [PLAYERS[n]['avatar'] for n in team['members'] if not PLAYERS[n].get('is_admin')]
    
    if not avatars:
        return f'Команда {team_id[-1]}', 'team_default.png'
    
    counts = {}
    for av in avatars:
        counts[av] = counts.get(av, 0) + 1
    most_common = max(counts, key=counts.get)
    
    if most_common == '1.png':
        return 'Дикие кошки', 'team_cats.png'
    elif most_common == '2.png':
        return 'Хитрые змеи', 'team_snakes.png'
    else:
        return 'Пернатое содружество', 'team_birds.png'

@socketio.on('join_lobby')
def handle_join(data):
    name = data.get('name')
    if name in PLAYERS:
        PLAYERS[name]['sid'] = request.sid
    else:
        PLAYERS[name] = {
            'sid': request.sid,
            'avatar': data.get('avatar', '1.png'),
            'team_id': None,
            'is_admin': len(PLAYERS) == 0
        }
    broadcast_lobby()

@socketio.on('join_game')
def handle_join_game(data):
    """Специальное событие для подключения к игровому полю"""
    name = data.get('name')
    if name in PLAYERS:
        PLAYERS[name]['sid'] = request.sid
    broadcast_game()

@socketio.on('create_team')
def handle_create_team():
    tid = f"team_{len(TEAMS) + 1}"
    TEAMS[tid] = {
        'members': [],
        'score': 0
    }
    broadcast_lobby()

@socketio.on('assign_to_team')
def handle_assign(data):
    player_name = data['player_name']
    team_id = data['team_id']
    
    old_team = PLAYERS[player_name].get('team_id')
    if old_team and old_team in TEAMS:
        TEAMS[old_team]['members'].remove(player_name)
    
    PLAYERS[player_name]['team_id'] = team_id
    if team_id:
        TEAMS[team_id]['members'].append(player_name)
    
    broadcast_lobby()

@socketio.on('make_admin')
def handle_make_admin(data):
    """Назначение нового админа"""
    player_name = data['player_name']
    if player_name in PLAYERS:
        PLAYERS[player_name]['is_admin'] = True
        old_team = PLAYERS[player_name].get('team_id')
        if old_team and old_team in TEAMS:
            TEAMS[old_team]['members'].remove(player_name)
        PLAYERS[player_name]['team_id'] = None
        broadcast_lobby()

@socketio.on('start_game')
def handle_start():
    socketio.emit('redirect_to_game', {'url': '/game'})

@socketio.on('select_question')
def handle_select(data):
    # Загружаем полные данные вопроса из questions.json
    try:
        with open('questions.json', 'r', encoding='utf-8') as f:
            questions_data = json.load(f)
        
        question = None
        for cat in questions_data['categories']:
            if cat['name'] == data['category']:
                for q in cat['questions']:
                    if q['price'] == int(data['price']):
                        question = q
                        break
        
        ACTIVE_QUESTION.update({
            'category': data['category'],
            'price': int(data['price']),
            'team_id': None
        })
        
        # Отправляем вопрос с медиа-данными
        socketio.emit('question_opened', {
            'category': data['category'],
            'price': int(data['price']),
            'text': question.get('text', ''),
            'media_type': question.get('media_type', 'text'),
            'media_url': question.get('media_url')
        })
    
    except Exception as e:
        print(f"Error loading question: {e}")

@socketio.on('toggle_cell')
def handle_toggle(data):
    cell = (data['category'], int(data['price']))
    if cell in DISABLED_CELLS:
        DISABLED_CELLS.remove(cell)
    else:
        DISABLED_CELLS.add(cell)
    broadcast_game()

@socketio.on('start_team_answer')
def handle_team_answer(data):
    ACTIVE_QUESTION['team_id'] = data['team_id']
    socketio.emit('timer_start', {'team_id': data['team_id'], 'duration': 30})

@socketio.on('submit_answer')
def handle_submit(data):
    """Обработка ответа команды"""
    team_id = ACTIVE_QUESTION['team_id']
    price = ACTIVE_QUESTION['price']
    
    if team_id and team_id in TEAMS:
        if data['correct']:
            # Правильный ответ → +баллы + закрываем вопрос
            TEAMS[team_id]['score'] += price
            print(f"✅ Команда {team_id} получила +{price} баллов")
            
            # Закрываем ячейку
            cell = (ACTIVE_QUESTION['category'], price)
            DISABLED_CELLS.add(cell)
            
            # Сбрасываем активный вопрос
            ACTIVE_QUESTION.update({'category': None, 'price': 0, 'team_id': None})
        else:
            # Неправильный ответ → только сбрасываем команду
            print(f"❌ Команда {team_id} ответила неправильно")
            
            # Сбрасываем только текущую команду (вопрос остается активным)
            ACTIVE_QUESTION['team_id'] = None
    
    # Останавливаем таймер
    socketio.emit('timer_stop', {})
    
    # Закрываем модалку с вопросом
    socketio.emit('close_question_modal', {})
    
    # Обновляем данные на доске
    broadcast_game()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

