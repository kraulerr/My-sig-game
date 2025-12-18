# =================================================================
#                 app.py - ГЛАВНЫЙ ФАЙЛ СЕРВЕРА
# =================================================================
from flask import Flask, render_template, request, url_for
from flask_socketio import SocketIO, emit
import time

# --- НАСТРОЙКА ПРИЛОЖЕНИЯ ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- ХРАНИЛИЩЕ ДАННЫХ ИГРЫ ---
# PLAYERS[sid] = {'name': 'Имя', 'avatar': '1.png', 'score': 0,
#                 'is_ready': False, 'is_admin': False}
PLAYERS = {}

# =================================================================
#                   ЛОГИКА СТРАНИЦ (HTML)
# =================================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/lobby')
def lobby():
    return render_template('lobby.html')

@app.route('/game')
def game():
    return render_template('board.html')

# =================================================================
#          ЛОГИКА ОБРАТНОГО ОТСЧЕТА (Фоновая задача)
# =================================================================
def start_game_countdown():
    """Фоновый таймер на 10 секунд перед стартом игры."""
    print("[ТАЙМЕР]: Запущен обратный отсчет 10 секунд...")
    time.sleep(10)

    with app.app_context():
        # Перепроверяем, все ли ещё готовы
        if PLAYERS and all(p.get('is_ready') for p in PLAYERS.values()):
            print("[ТАЙМЕР]: Все ещё готовы. Стартуем игру!")
            socketio.emit('redirect_to_game', {'url': url_for('game')}, broadcast=True)
        else:
            print("[ТАЙМЕР]: Кто-то стал не готов. Старт отменён.")
            socketio.emit('stop_timer_signal', broadcast=True)

# =================================================================
#                ЛОГИКА ИГРЫ (События Socket.IO)
# =================================================================

@socketio.on('connect')
def on_connect():
    """Просто факт подключения сокет-клиента."""
    print(f"[SocketIO]: клиент подключился, sid = {request.sid}")

@socketio.on('join_request')
def handle_join(data):
    """Игрок заходит в игру (после нажатия кнопки на index.html)."""
    print("[join_request]: получены данные от клиента:", data)

    player_name = data.get('name')
    player_avatar = data.get('avatar')

    if not player_name or not player_avatar:
        print("[join_request]: ПУСТЫЕ данные, игнорируем.")
        return

    # Первый зашедший становится админом
    is_admin = not PLAYERS

    PLAYERS[request.sid] = {
        'name': player_name,
        'avatar': player_avatar,
        'score': 0,
        'is_ready': False,
        'is_admin': is_admin
    }

    print(f"[Игрок]: '{player_name}' подключился. Всего игроков: {len(PLAYERS)}.")

    # Сообщаем клиенту, что можно переходить в лобби
    emit('redirect', {'url': url_for('lobby')}, to=request.sid)
    # Обновляем список игроков у всех
    emit('update_player_list', PLAYERS, broadcast=True)

@socketio.on('toggle_ready')
def handle_toggle_ready():
    """Игрок нажимает кнопку 'Готов / Не готов'."""
    if request.sid not in PLAYERS:
        print("[toggle_ready]: неизвестный sid, игнорируем.")
        return

    PLAYERS[request.sid]['is_ready'] = not PLAYERS[request.sid]['is_ready']
    all_ready = all(p.get('is_ready') for p in PLAYERS.values())

    if len(PLAYERS) > 1 and all_ready:
        print("[toggle_ready]: все готовы, запускаем фоновый таймер.")
        socketio.start_background_task(target=start_game_countdown)
        emit('start_timer_signal', {'seconds': 10}, broadcast=True)
    else:
        print("[toggle_ready]: не все готовы, останавливаем таймер (если был).")
        emit('stop_timer_signal', broadcast=True)

    emit('update_player_list', PLAYERS, broadcast=True)

@socketio.on('kick_player')
def handle_kick_player(data):
    """Админ выгоняет игрока из лобби."""
    requester_sid = request.sid
    target_sid = data.get('target_id')

    if PLAYERS.get(requester_sid, {}).get('is_admin') and target_sid in PLAYERS:
        kicked_name = PLAYERS[target_sid]['name']
        print(f"[Админ]: кикнул игрока '{kicked_name}'.")
        emit('redirect', {'url': url_for('index')}, to=target_sid)
        socketio.disconnect(sid=target_sid)

@socketio.on('force_start')
def handle_force_start():
    """Принудительный старт игры (только для админа)."""
    if PLAYERS.get(request.sid, {}).get('is_admin'):
        print("[Админ]: принудительный старт игры.")
        emit('redirect_to_game', {'url': url_for('game')}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Игрок закрыл вкладку или был кикнут."""
    if request.sid in PLAYERS:
        player_name = PLAYERS[request.sid]['name']
        del PLAYERS[request.sid]
        print(f"[Игрок]: '{player_name}' отключился. Осталось игроков: {len(PLAYERS)}.")

        # Если админ вышел — назначаем нового, если есть игроки
        if PLAYERS and not any(p.get('is_admin') for p in PLAYERS.values()):
            new_admin_sid = next(iter(PLAYERS))
            PLAYERS[new_admin_sid]['is_admin'] = True
            print(f"[Сервер]: новый админ — '{PLAYERS[new_admin_sid]['name']}'.")

        emit('update_player_list', PLAYERS, broadcast=True)

# =================================================================
#                          ЗАПУСК СЕРВЕРА
# =================================================================
if __name__ == '__main__':
    print("------------------------------------------------------")
    print("           ЗАПУСК ИГРОВОГО СЕРВЕРА")
    print("------------------------------------------------------")
    try:
        print("Сервер работает локально на: http://localhost:5000")
        print("Чтобы остановить, нажмите Ctrl+C.")
        print("------------------------------------------------------")
        socketio.run(app, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n------------------------------------------------------")
        print("           СЕРВЕР ОСТАНОВЛЕН")
        print("------------------------------------------------------")
