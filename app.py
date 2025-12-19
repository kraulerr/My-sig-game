from flask import Flask, render_template, request, url_for, jsonify
from flask_socketio import SocketIO, emit
import json, os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# PLAYERS[sid] = {
#   'name': ...,
#   'avatar': ...,
#   'score': 0,
#   'is_ready': False,
#   'is_admin': False
# }
PLAYERS = {}


# ----------------- ROUTES -----------------

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
    path = os.path.join(os.path.dirname(__file__), 'questions.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"categories": []}
    return jsonify(data)


# ----------------- HELPERS -----------------

def broadcast_players():
    """Отправляет всем список игроков и id админа."""
    admin_sid = None
    for sid, pdata in PLAYERS.items():
        if pdata.get('is_admin'):
            admin_sid = sid
            break

    socketio.emit('update_player_list', {
        'players': PLAYERS,
        'admin_id': admin_sid
    })


# ----------------- SOCKET.IO EVENTS -----------------

@socketio.on('connect')
def on_connect():
    print(f"[SocketIO]: клиент подключился, sid = {request.sid}")


@socketio.on('join_request')
def handle_join(data):
    """Игрок заходит в лобби (вызывается из lobby.html)."""
    print("[join_request]:", data)
    name = data.get('name')
    avatar = data.get('avatar')
    if not name or not avatar:
        return

    is_admin = not PLAYERS  # первый зашедший — админ

    PLAYERS[request.sid] = {
        'name': name,
        'avatar': avatar,
        'score': 0,
        'is_ready': False,
        'is_admin': is_admin
    }
    print(f"[Игрок]: '{name}' подключился. Всего игроков: {len(PLAYERS)}.")
    broadcast_players()


@socketio.on('request_players')
def handle_request_players():
    broadcast_players()


@socketio.on('toggle_ready')
def handle_toggle_ready():
    """Игрок нажимает кнопку 'ГОТОВ / НЕ ГОТОВ'."""
    if request.sid not in PLAYERS:
        print("[toggle_ready]: неизвестный sid")
        return

    PLAYERS[request.sid]['is_ready'] = not PLAYERS[request.sid]['is_ready']
    state = "готов" if PLAYERS[request.sid]['is_ready'] else "не готов"
    print(f"[toggle_ready]: {PLAYERS[request.sid]['name']} теперь {state}")

    # Все готовы и игроков больше одного?
    all_ready = len(PLAYERS) > 1 and all(p.get('is_ready') for p in PLAYERS.values())

    if all_ready:
        print("[toggle_ready]: все готовы, запускаем таймер на клиентах")
        emit('start_timer_signal', {'seconds': 10}, broadcast=True)
    else:
        print("[toggle_ready]: не все готовы, останавливаем таймер")
        emit('stop_timer_signal', broadcast=True)

    broadcast_players()


@socketio.on('kick_player')
def handle_kick_player(data):
    """Админ выгоняет игрока из лобби."""
    requester_sid = request.sid
    target_sid = data.get('target_id')

    if not PLAYERS.get(requester_sid, {}).get('is_admin'):
        print("[kick_player]: неадмин, игнорируем")
        return

    if target_sid == requester_sid:
        print("[kick_player]: попытка кикнуть самого себя")
        return

    if target_sid in PLAYERS:
        kicked_name = PLAYERS[target_sid]['name']
        print(f"[Админ]: кикнул '{kicked_name}'")
        emit('redirect', {'url': url_for('index')}, to=target_sid)
        socketio.disconnect(sid=target_sid)
    else:
        print("[kick_player]: целевой sid не найден")


@socketio.on('force_start')
def handle_force_start():
    """Принудительный старт игры (только для админа)."""
    if PLAYERS.get(request.sid, {}).get('is_admin'):
        print("[Админ]: принудительный старт игры.")
        socketio.emit('redirect_to_game', {'url': url_for('game')})
    else:
        print("[force_start]: неадмин, игнорируем")


@socketio.on('disconnect')
def handle_disconnect(reason=None):
    if request.sid in PLAYERS:
        name = PLAYERS[request.sid]['name']
        was_admin = PLAYERS[request.sid]['is_admin']
        del PLAYERS[request.sid]
        print(f"[Игрок]: '{name}' отключился. Осталось: {len(PLAYERS)}.")

        if was_admin and PLAYERS and not any(p.get('is_admin') for p in PLAYERS.values()):
            new_admin_sid = next(iter(PLAYERS))
            PLAYERS[new_admin_sid]['is_admin'] = True
            print(f"[Сервер]: новый админ — '{PLAYERS[new_admin_sid]['name']}'")

        broadcast_players()


if __name__ == '__main__':
    print("Запуск на http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000)
