from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import os

app = Flask(__name__)
app.secret_key = "super-secret-key-2281337"  # обязательно поменяй в реальном проекте!
socketio = SocketIO(app, cors_allowed_origins="*")

# Временное хранилище (всё в памяти — при перезапуске теряется)
users = {}  # username → {'sid': socket_id, 'online': bool}
messages = {}  # (user1, user2) → список сообщений
online_users = set()


def get_room_key(u1, u2):
    return tuple(sorted([u1.lower(), u2.lower()]))


# ─── Routes ──────────────────────────────────────────────────

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('chat'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if username and 3 <= len(username) <= 20:
            session['username'] = username
            return redirect(url_for('chat'))
        else:
            return render_template('login.html', error="Ник от 3 до 20 символов")
    return render_template('login.html')


@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']

    # Собираем всех, с кем был диалог + кто онлайн
    friends = set()
    for (u1, u2) in messages:
        if u1 == username:
            friends.add(u2)
        elif u2 == username:
            friends.add(u1)

    for u in online_users:
        if u != username:
            friends.add(u)

    return render_template('chat.html',
                           username=username,
                           friends=sorted(friends),
                           online=online_users)


@app.route('/chat/@<friend>')
def chat_with(friend):
    if 'username' not in session:
        return redirect(url_for('login'))

    me = session['username']
    if me.lower() == friend.lower():
        return "Нельзя писать самому себе", 400

    room = get_room_key(me, friend)
    msgs = messages.get(room, [])

    return render_template('chat_room.html',
                           me=me,
                           friend=friend,
                           messages=msgs)


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


# ─── SocketIO ────────────────────────────────────────────────

@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        username = session['username']
        users[username] = {'sid': request.sid, 'online': True}
        online_users.add(username)
        emit('user_status', {'username': username, 'online': True}, broadcast=True)
        print(f"[connect] {username}")


@socketio.on('disconnect')
def handle_disconnect():
    for username, data in list(users.items()):
        if data['sid'] == request.sid:
            online_users.discard(username)
            emit('user_status', {'username': username, 'online': False}, broadcast=True)
            print(f"[disconnect] {username}")
            break


@socketio.on('message')
def handle_message(data):
    me = session.get('username')
    if not me:
        return

    friend = data.get('to')
    text = data.get('text', '').strip()

    if not friend or not text or len(text) > 2000:
        return

    room_tuple = get_room_key(me, friend)
    msg = {
        'from': me,
        'text': text,
        # 'time': datetime.now().strftime('%H:%M')
    }

    messages.setdefault(room_tuple, []).append(msg)

    # Отправляем обоим
    for u in room_tuple:
        if u in users:
            emit('new_message', {
                'from': me,
                'to': friend,
                'text': text,
                'room': f"@{friend}" if u == me else f"@{me}"
            }, room=users[u]['sid'])


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)