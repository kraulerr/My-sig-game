from flask import Flask, render_template, request, url_for
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Хранилище игроков: { 'id_сокета': {'name': 'Имя', 'avatar': '1.png', 'score': 0} }
PLAYERS = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/lobby')
def lobby():
    return render_template('lobby.html')

# --- СОБЫТИЯ SOCKET.IO ---

@socketio.on('join_request')
def handle_join(data):
    player_name = data['name']
    player_avatar = data['avatar']
    
    PLAYERS[request.sid] = {
        'name': player_name, 
        'avatar': player_avatar,
        'score': 0
    }
    
    print(f"Подключился: {player_name}. Всего: {len(PLAYERS)}")
    
    # Отправляем редирект ТОЛЬКО если запрос пришел НЕ со страницы лобби
    # Но так как мы не знаем откуда, просто отправим 'redirect', 
    # а клиент сам решит (в index.html он слушает это событие, а в lobby.html - НЕТ).
    emit('redirect', {'url': url_for('lobby')}, to=request.sid)
    
    # И сразу всем обновляем список (чтобы в лобби появились иконки)
    emit('update_player_list', PLAYERS, broadcast=True)
    
@socketio.on('get_players')
def handle_get_players():
    # Отправляем всем (broadcast=True) список игроков, чтобы они увидели новенького
    emit('update_player_list', PLAYERS, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in PLAYERS:
        name = PLAYERS[request.sid]['name']
        del PLAYERS[request.sid]
        print(f"Отключился: {name}")
        # Обновляем список у всех, кто остался
        emit('update_player_list', PLAYERS, broadcast=True)

if __name__ == '__main__':
    socketio.run(app) 
