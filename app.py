from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPREADSHEET_ID = '1f7aU-pG1vPcPveJ2GslP0PLJs5zio2bF4j6PNevCuTw'
SHEET_NAME = 'Персонажи'
LOG_SHEET_NAME = 'Логи'

def get_google_sheet():
    try:
        if os.path.exists('character-sheets-bot.json'):
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                'character-sheets-bot.json', scope
            )
        else:
            json_key = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
            if not json_key:
                raise Exception("GOOGLE_SHEETS_CREDENTIALS не найдена")
            creds_dict = json.loads(json_key)
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                creds_dict, scope
            )
        
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        logger.error(f"Ошибка подключения к Google Sheets: {e}")
        raise
        
        
def log_action(action, character_name, details=""):
    """Запись действия в лог"""
    try:
        log_sheet = client.open_by_key(SPREADSHEET_ID).worksheet(LOG_SHEET_NAME)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_sheet.append_row([timestamp, action, character_name, details])
    except Exception as e:
        logger.error(f"Ошибка записи в лог: {e}")
        
try:
    if os.path.exists('character-sheets-bot.json'):
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            'character-sheets-bot.json', scope
        )
    else:
        json_key = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if json_key:
            creds_dict = json.loads(json_key)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                creds_dict, scope
            )
        else:
            creds = None
    
    if creds:
        client = gspread.authorize(creds)
    else:
        client = None
        logger.warning("Не удалось авторизоваться в Google Sheets")
except Exception as e:
    logger.error(f"Ошибка инициализации клиента: {e}")
    client = None

@app.route('/')
def index():
    """Главная страница - создание анкеты"""
    return render_template('index.html')

@app.route('/list')
def list_characters():
    """Страница со списком всех анкет"""
    return render_template('list.html')
    
@app.route('/api/characters', methods=['GET'])

def get_characters():
    """API: получить список всех персонажей"""
    try:
        if not client:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        records = sheet.get_all_records()
        
        characters = []
        for i, record in enumerate(records, start=2):  
            if record.get('name'):
                characters.append({
                    'row_number': i,
                    'id': record.get('id', ''),
                    'name': record.get('name', ''),
                    'race': record.get('race', ''),
                    'profession': record.get('profession', ''),
                    'timestamp': record.get('timestamp', ''),
                    'location': record.get('location', ''),
                    'status': record.get('status', '')
                })
        
        return jsonify({
            'characters': characters,
            'count': len(characters)
        }), 200
        
    except Exception as e:
        logger.error(f"Ошибка получения списка: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/character/<int:row_number>', methods=['GET'])
def get_character(row_number):
    """API: получить конкретного персонажа по номеру строки"""
    try:
        if not client:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        row = sheet.row_values(row_number)
        headers = sheet.row_values(1)
        
        character = dict(zip(headers, row))
        
        return jsonify(character), 200
        
    except Exception as e:
        logger.error(f"Ошибка получения персонажа: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/character/check', methods=['POST'])
def check_character_name():
    """API: проверить, существует ли персонаж с таким именем"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'exists': False, 'message': 'Имя не указано'}), 200
        
        if not client:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        records = sheet.get_all_records()
        
        for i, record in enumerate(records, start=2):
            if record.get('name', '').strip().lower() == name.lower():
                return jsonify({
                    'exists': True,
                    'row_number': i,
                    'character': record
                }), 200
        
        return jsonify({'exists': False}), 200
        
    except Exception as e:
        logger.error(f"Ошибка проверки имени: {e}")
        return jsonify({'error': str(e)}), 500
        
@app.route('/api/character/save', methods=['POST'])
def save_character():
    """API: сохранить нового персонажа"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Нет данных'}), 400
        
        name = data.get('name', '').strip()
        if not name:
            sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
            records = sheet.get_all_records()
            unnamed_count = sum(1 for r in records if not r.get('name', '').strip())
            name = f"Без имени {unnamed_count + 1}"
            
        overwrite = data.get('overwrite', False)
        existing_row = data.get('existing_row')
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        
        row_data = [
            timestamp,                           # timestamp
            record_id,                           # id
            name,                                # name
            data.get('race', ''),                # race
            data.get('profession', ''),          # profession
            data.get('status', ''),              # status
            data.get('current_time', ''),        # current_time
            data.get('location', ''),            # location
            data.get('inventory', ''),           # inventory
            data.get('birth_date', ''),          # birth_date
            data.get('birth_place', ''),         # birth_place
            data.get('lifespan', ''),            # lifespan
            data.get('star_sign', ''),           # star_sign
            data.get('first_appearance', ''),    # first_appearance
            data.get('status_title', ''),        # status_title
            data.get('biography', ''),           # biography
            data.get('appearance', ''),          # appearance
            data.get('personality', '')          # personality
        ]
        
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        
        if overwrite and existing_row:
            for col, value in enumerate(row_data, start=1):
                sheet.update_cell(existing_row, col, value)
            action = 'overwrite'
            message = f"Персонаж '{name}' обновлен!"
        else:
            sheet.append_row(row_data)
            action = 'create'
            message = f"Персонаж '{name}' успешно создан!"
            
        try:
            log_sheet = client.open_by_key(SPREADSHEET_ID).worksheet(LOG_SHEET_NAME)
            log_sheet.append_row([timestamp, action, name, json.dumps(data, ensure_ascii=False)[:200]])
        except:
            pass
        
        return jsonify({
            'message': message,
            'name': name,
            'timestamp': timestamp,
            'record_id': record_id,
            'status': 'success'
        }), 200
        
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        return jsonify({'error': str(e)}), 
        
@app.route('/api/character/delete/<int:row_number>', methods=['DELETE'])
def delete_character(row_number):
    """API: удалить персонажа"""
    try:
        if not client:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        
        name = sheet.cell(row_number, 3).value
        
        sheet.delete_rows(row_number)
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            log_sheet = client.open_by_key(SPREADSHEET_ID).worksheet(LOG_SHEET_NAME)
            log_sheet.append_row([timestamp, 'delete', name, f'Удалена строка {row_number}'])
        except:
            pass
        
        return jsonify({
            'message': f"Персонаж '{name}' удален",
            'status': 'success'
        }), 200
        
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)