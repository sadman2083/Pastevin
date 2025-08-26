from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from pytz import timezone

import base64
import json
import os
import threading
import time
import requests
import random
from datetime import datetime
from urllib.parse import unquote
from dotenv import load_dotenv

load_dotenv()  # Load .env values


def get_random_marker():
    return random.choice(['🔵', '🟣', '🟢', '🔴', '🟡', '🟠',
        '⚫', '⚪', '✨',
        '🟥', '🟧', '🟨', '🟩', '🟦', '🟪'])

def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


app = Flask(__name__)
NOTES_FILE = 'notes.json'
GLOBAL_PASSWORD = os.getenv("GLOBAL_PASSWORD")

app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# checklist
CHECKLIST_FILE = 'checklist_data.json'


def load_checklist():
    if os.path.exists(CHECKLIST_FILE):
        with open(CHECKLIST_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_checklist(data):
    with open(CHECKLIST_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# telegram
def check_unfinished_tasks():
    while True:
        tz = timezone('America/Toronto')  # or your timezone
        today = datetime.now(tz).strftime("%Y-%m-%d")

        data = load_checklist()
        unfinished = []

        if today in data:
            for task in data[today]:
                if not task['done']:
                    unfinished.append(f"- {task['text']}")

        if unfinished:
            current_time = datetime.now(tz).strftime("%I:%M %p")
            marker = get_random_marker()
            msg = f"{marker} Unfinished Tasks at {current_time} \n\n" + "\n\n".join(unfinished) + "\n\n➡️ Open Checklist: https://mypastebin.duckdns.org/checklist"
            send_telegram_message(msg)
          

        time.sleep(3600) 


# telegram

# Load existing notes
if os.path.exists(NOTES_FILE):
    with open(NOTES_FILE, 'r') as f:
        try:
            notes = json.load(f)
        except json.JSONDecodeError:
            notes = {}
else:
    notes = {}


# checklist
@app.route('/checklist')
def checklist_page():
    return render_template('checklist.html')


@app.route('/api/tasks/<date>', methods=['GET'])
def get_tasks_by_date(date):
    data = load_checklist()
    return data.get(date, [])


@app.route('/api/add_task', methods=['POST'])
def add_task():
    payload = request.get_json()
    date = payload.get('date')
    text = payload.get('text')
    if not date or not text:
        return {"error": "Missing data"}, 400

    tz = timezone('America/Toronto')  # Use your region
    created_at = datetime.now(tz).strftime(" %I:%M %p %A %B %d")

    data = load_checklist()
    data.setdefault(date, []).append({
        "text": text,
        "done": False,
        "note": "",
        "created_at": created_at
    })
    save_checklist(data)
    return {"status": "ok"}

    save_checklist(data)
    return {"status": "ok"}


@app.route('/api/update_task', methods=['POST'])
def update_task():
    payload = request.get_json()
    date = payload.get('date')
    index = payload.get('index')
    data = load_checklist()
    if date in data and 0 <= index < len(data[date]):
        data[date][index]['done'] = not data[date][index]['done']
        save_checklist(data)
        return {"status": "ok"}
    return {"error": "Invalid task"}, 400


@app.route('/api/delete_task', methods=['POST'])
def delete_task():
    payload = request.get_json()
    date = payload.get('date')
    index = payload.get('index')
    data = load_checklist()
    if date in data and 0 <= index < len(data[date]):
        data[date].pop(index)
        save_checklist(data)
        return {"status": "ok"}
    return {"error": "Invalid task"}, 400


@app.route('/view_task/<date>/<int:index>', methods=['GET', 'POST'])
def view_task(date, index):
    data = load_checklist()
    if date not in data or index >= len(data[date]):
        return "Task not found", 404

    if request.method == 'POST':
        note = request.form.get('note', '').strip()
        data[date][index]['note'] = note
        save_checklist(data)
        return redirect(url_for('checklist_page'))

    task = data[date][index]
    return render_template('view_task.html',
                           date=date,
                           index=index,
                           note=task.get("note", ""),
                           created_at=task.get("created_at", ""))


@app.route('/edit_task/<date>/<int:index>', methods=['GET', 'POST'])
def edit_task(date, index):
    data = load_checklist()
    if date not in data or index >= len(data[date]):
        return "Task not found", 404

    if request.method == 'POST':
        note = request.form.get('note', '').strip()
        data[date][index]['note'] = note
        save_checklist(data)
        return redirect(url_for('checklist_page', date=date))

    task = data[date][index]
    return render_template('edit_task.html',
                           date=date,
                           index=index,
                           note=task.get("note", ""))


# checklist


@app.template_filter('b64encode')
def b64encode_filter(s):
    if isinstance(s, str):
        s = s.encode('utf-8')
    return base64.b64encode(s).decode('utf-8')


@app.context_processor
def utility_processor():

    def get_unique_folders(notes):
        folder_set = set()
        for key in notes:
            if '/' in key:
                folder_name = key.split('/')[0]
                folder_set.add(folder_name)
        return sorted(folder_set)

    return dict(get_unique_folders=get_unique_folders)


@app.route('/')
def home():
    files = [
        f for f in os.listdir(app.config['UPLOAD_FOLDER'])
        if os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], f))
    ]
    return render_template('index.html',
                           notes=dict(reversed(list(notes.items()))),
                           files=files,
                           pin_code=GLOBAL_PASSWORD)


@app.route('/create_folder', methods=['POST'])
def create_folder():
    global notes
    count = 1
    while f"Folder {count}/" in notes:
        count += 1
    folder_name = f"Folder {count}"
    notes[f"{folder_name}/"] = ""
    with open(NOTES_FILE, 'w') as f:
        json.dump(notes, f)
    return redirect(url_for('home'))


@app.route('/delete_file/<folder_name>/<filename>', methods=['POST'])
def delete_file_from_folder(folder_name, filename):
    password = request.form.get('password', '')
    if password != GLOBAL_PASSWORD:
        return "Invalid password", 403

    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    filepath = os.path.join(folder_path, filename)

    if os.path.exists(filepath):
        os.remove(filepath)

    return redirect(url_for('view_folder', folder_name=folder_name) + "#files")


@app.route('/upload/<folder_name>', methods=['POST'])
def upload_file_to_folder(folder_name):
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    os.makedirs(folder_path, exist_ok=True)

    uploaded_files = request.files.getlist('files')
    for file in uploaded_files:
        if file.filename:
            file.save(os.path.join(folder_path, file.filename))

    return redirect(
        url_for('view_folder', folder_name=folder_name) + "#upload-files")


@app.route('/uploads/<folder_name>/<filename>')
def uploaded_file_from_folder(folder_name, filename):
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    return send_from_directory(folder_path, filename)


@app.route('/view_folder/<folder_name>')
def view_folder(folder_name):
    folder_notes = {
        k: v
        for k, v in notes.items() if k.startswith(f"{folder_name}/")
    }

    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    uploaded_files = os.listdir(folder_path) if os.path.exists(
        folder_path) else []

    return render_template('folder.html',
                           folder_name=folder_name,
                           notes=dict(reversed(list(folder_notes.items()))),
                           files=uploaded_files,
                           pin_code=GLOBAL_PASSWORD)


@app.route('/rename_folder/<folder_name>', methods=['POST'])
def rename_folder(folder_name):
    global notes
    new_name = request.form.get('new_name', '').strip()

    if not new_name or f"{new_name}/" in notes:
        return redirect(url_for('view_folder', folder_name=folder_name))

    # Update notes keys
    updated_notes = {}
    for key, value in notes.items():
        if key.startswith(f"{folder_name}/"):
            new_key = key.replace(f"{folder_name}/", f"{new_name}/")
            updated_notes[new_key] = value
        elif key != f"{folder_name}/":
            updated_notes[key] = value
    notes = updated_notes

    # Rename the actual folder in the uploads directory
    old_folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    new_folder_path = os.path.join(app.config['UPLOAD_FOLDER'], new_name)
    if os.path.exists(old_folder_path):
        os.rename(old_folder_path, new_folder_path)

    with open(NOTES_FILE, 'w') as f:
        json.dump(notes, f)

    return redirect(url_for('view_folder', folder_name=new_name))


@app.route('/delete_folder/<folder_name>', methods=['POST'])
def delete_folder(folder_name):
    global notes

    password = request.form.get('password', '')
    if password != GLOBAL_PASSWORD:
        return "Invalid password", 403

    keys_to_delete = [
        key for key in notes
        if key.startswith(f"{folder_name}/") or key == f"{folder_name}/"
    ]

    for key in keys_to_delete:
        del notes[key]

    with open(NOTES_FILE, 'w') as f:
        json.dump(notes, f)

    return redirect(url_for('home'))


@app.route('/save', methods=['POST'])
def save():
    global notes
    folder = request.form.get('folder', '').strip()
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    if not content:
        return redirect(url_for('home'))
    if not title:
        base_title = f"Untitled - {datetime.now().strftime('%Y-%m-%d')}"
        count = 1
        if folder:
            while f"{folder}/{base_title} ({count})" in notes:
                count += 1
            title = f"{base_title} ({count})"
            key = f"{folder}/{title}"
        else:
            while f"{base_title} ({count})" in notes:
                count += 1
            title = f"{base_title} ({count})"
            key = title
    else:
        key = f"{folder}/{title}" if folder else title
    notes[key] = content
    with open(NOTES_FILE, 'w') as f:
        json.dump(notes, f)
    return redirect(
        url_for('view_folder', folder_name=folder
                ) if folder else url_for('home'))


@app.route('/view/<path:key>')
def view_note(key):
    key = unquote(key)
    note = notes.get(key, '')
    if note:
        return render_template('view.html', key=key, note=note)
    return "Note not found", 404


@app.route('/delete/<path:key>', methods=['POST'])
def delete_note(key):
    global notes
    key = unquote(key)
    password = request.form.get('password', '')
    if password != GLOBAL_PASSWORD:
        return "Invalid password", 403
    folder_name = key.split('/')[0] if '/' in key else None
    if key in notes:
        del notes[key]
        with open(NOTES_FILE, 'w') as f:
            json.dump(notes, f)
    if folder_name:
        return redirect(
            url_for('view_folder', folder_name=folder_name) + "#notes")
    else:
        return redirect(url_for('home') + "#notes-section")


@app.route('/upload', methods=['POST'])
def upload_file():
    uploaded_files = request.files.getlist('files')
    for file in uploaded_files:
        if file.filename:
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
    return redirect(url_for('home'))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/delete_file/<filename>', methods=['POST'])
def delete_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    return redirect(url_for('home'))


@app.route('/edit/<path:key>', methods=['GET'])
def edit_note(key):
    key = unquote(key)
    note = notes.get(key, '')
    if note:
        return render_template('edit.html', key=key, note=note)
    return "Note not found", 404


@app.route('/update/<path:key>', methods=['POST'])
def update_note(key):
    global notes
    key = unquote(key)
    content = request.form.get('content', '').strip()
    password = request.form.get('password', '')
    if password != GLOBAL_PASSWORD:
        return "Invalid password", 403
    if key in notes:
        notes[key] = content
        with open(NOTES_FILE, 'w') as f:
            json.dump(notes, f)
        return '''
            <html>
                <head>
                    <meta http-equiv="refresh" content="2;url=/view/{}">
                </head>
                <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                    <h2>✅ Note updated successfully!</h2>
                    <p>Redirecting back to note...</p>
                </body>
            </html>
        '''.format(key)
    else:
        return "Note not found", 404


if __name__ == '__main__':
    threading.Thread(target=check_unfinished_tasks, daemon=True).start()
    app.run(debug=False)
