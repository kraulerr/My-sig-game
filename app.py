# =================================================================
#                 app.py - ГЛАВНЫЙ ФАЙЛ СЕРВЕРА
# =================================================================
from flask import Flask, render_template, request, url_for
from flask_socketio import SocketIO, emit
import time

# --- НАСТРОЙКА ПРИЛОЖЕНИЯ ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-key' # Можете поменять на любую фразу
socketio = SocketIO(app, cors_allowed_origins="*")

# --- ХРАНИЛИЩЕ ДАННЫХ ИГРЫ ---
# Здесь мы храним всех игроков и их статусы.
# Ключ - это уникальный ID сессии (request.sid)
# PLAYERS[sid] = {'name': 'Имя', 'avatar': '1.png', 'score': 0, 'is_ready': False, 'is_admin': False}
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
    """
    Эта функция запускается в фоне, ждет 10 секунд и стартует игру,
    если все игроки ВСЁ ЕЩЁ готовы.
    """
    print("[Сервер]: Фоновый таймер на 10 секунд запущен...")
    time.sleep(10)
    
    # Чтобы использовать emit и url_for в фоне, нужен "контекст приложения"
    with app.app_context():
        # Перепроверяем, все ли еще готовы
        if PLAYERS and all(p.get('is_ready') for p in PLAYERS.values()):
            print("[Сервер]: Таймер завершен. Начинаем игру!")
            socketio.emit('redirect_to_game', {'url': url_for('game')}, broadcast=True)
        else:
            print("[Сервер]: Старт отменен, кто-то передумал.")
            socketio.emit('stop_timer_signal', broadcast=True)

# =================================================================
#                ЛОГИКА ИГРЫ (События Socket.IO)
# =================================================================

@socketio.on('join_request')
def handle_join(data):
    """Игрок заходит на сайт (с главной или из лобби)."""
    player_name = data.get('name')
    player_avatar = data.get('avatar')
    
    if not player_name or not player_avatar:
        return # Игнорируем пустые запросы

    # Первый вошедший становится Админом
    is_admin = not PLAYERS
    
    PLAYERS[request.sid] = {
        'name': player_name, 
        'avatar': player_avatar,
        'score': 0,
        'is_ready': False,
        'is_admin': is_admin
    }
    
    print(f"[Игрок]: '{player_name}' подключился. Всего игроков: {len(PLAYERS)}.")
    
    # Отправляем обновленный список всем
    emit('update_player_list', PLAYERS, broadcast=True)

@socketio.on('toggle_ready')
def handle_toggle_ready():
    """Игрок нажимает кнопку 'Готов' / 'Не готов'."""
    if request.sid in PLAYERS:
        PLAYERS[request.sid]['is_ready'] = not PLAYERS[request.sid]['is_ready']
        
        all_ready = all(p.get('is_ready') for p in PLAYERS.values())
        
        # Запускаем таймер, если игроков больше одного и ВСЕ готовы
        if len(PLAYERS) > 1 and all_ready:
            socketio.start_background_task(target=start_game_countdown)
            emit('start_timer_signal', {'seconds': 10}, broadcast=True)
        else:
            # Если кто-то "передумал", отменяем таймер
            emit('stop_timer_signal', broadcast=True)
            
        emit('update_player_list', PLAYERS, broadcast=True)

@socketio.on('kick_player')
def handle_kick_player(data):
    """Админ выгоняет игрока."""
    requester_sid = request.sid
    target_sid = data.get('target_id')
    
    # Проверяем, что команду послал админ, и цель существует
    if PLAYERS.get(requester_sid, {}).get('is_admin') and target_sid in PLAYERS:
        kicked_name = PLAYERS[target_sid]['name']
        print(f"[Админ]: Выгоняет игрока '{kicked_name}'.")
        
        # Отправляем жертве команду на редирект
        emit('redirect', {'url': url_for('index')}, to=target_sid)
        # Отключаем сокет жертвы
        socketio.disconnect(sid=target_sid)

@socketio.on('force_start')
def handle_force_start():
    """Админ принудительно запускает игру."""
    if PLAYERS.get(request.sid, {}).get('is_admin'):
        print("[Админ]: Принудительный старт игры.")
        emit('redirect_to_game', {'url': url_for('game')}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Игрок закрыл вкладку или был кикнут."""
    if request.sid in PLAYERS:
        player_name = PLAYERS[request.sid]['name']
        del PLAYERS[request.sid]
        print(f"[Игрок]: '{player_name}' отключился. Осталось: {len(PLAYERS)}.")
        
        # Если админ вышел, назначаем нового
        if PLAYERS and not any(p.get('is_admin') for p in PLAYERS.values()):
            new_admin_sid = next(iter(PLAYERS)) # Берем первого в списке
            PLAYERS[new_admin_sid]['is_admin'] = True
            print(f"[Сервер]: Назначен новый админ: '{PLAYERS[new_admin_sid]['name']}'.")

        # Обновляем список у всех оставшихся
        emit('update_player_list', PLAYERS, broadcast=True)

# =================================================================
#                          ЗАПУСК СЕРВЕРА
# =================================================================
if __name__ == '__main__':
    print("------------------------------------------------------")
    print("           ЗАПУСК ИГРОВОГО СЕРВЕРА")
    print("------------------------------------------------------")
    try:
        print(f"Сервер работает! Локальный адрес: http://localhost:5000")
        print("Чтобы остановить, нажмите Ctrl+C в этом окне.")
        print("------------------------------------------------------")
        print("Жду подключений игроков...")
        
        socketio.run(app, host='0.0.0.0', port=5000)
        
    except KeyboardInterrupt:
        print("\n------------------------------------------------------")
        print("           СЕРВЕР ОСТАНОВЛЕН")
        print("------------------------------------------------------")
