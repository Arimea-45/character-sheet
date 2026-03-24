from flask import Flask, render_template, request, jsonify
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем ID таблицы из переменных окружения
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '')
SHEET_NAME = os.environ.get('SHEET_NAME', 'Персонажи')
LOG_SHEET_NAME = os.environ.get('LOG_SHEET_NAME', 'Логи')

def get_google_client():
    """Подключение к Google Sheets"""
    try:
        # Получаем JSON из переменной окружения
        json_key = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        
        if not json_key:
            logger.error("GOOGLE_SHEETS_CREDENTIALS не найдена в переменных окружения")
            return None, None
        
        # Парсим JSON
        creds_dict = json.loads(json_key)
        
        # Настраиваем доступ
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        if not SPREADSHEET_ID:
            logger.error("SPREADSHEET_ID не указан")
            return None, None
        
        # Открываем таблицу
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        sheet = spreadsheet.worksheet(SHEET_NAME)
        
        logger.info("Успешно подключено к Google Sheets")
        return sheet, client
        
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Ошибка подключения к Google Sheets: {e}")
        return None, None

def ensure_headers(sheet):
    """Проверяет, что заголовки существуют"""
    try:
        headers = sheet.row_values(1)
        required_headers = [
            'timestamp', 'id', 'name', 'race', 'profession',
            'status', 'current_time', 'location', 'inventory',
            'birth_date', 'birth_place', 'lifespan', 'star_sign',
            'first_appearance', 'status_title', 'biography',
            'appearance', 'personality'
        ]
        
        if len(headers) < len(required_headers):
            # Добавляем недостающие заголовки
            for i, header in enumerate(required_headers, start=1):
                if i > len(headers):
                    sheet.update_cell(1, i, header)
            logger.info("Заголовки добавлены")
        
    except Exception as e:
        logger.error(f"Ошибка при проверке заголовков: {e}")

@app.route('/')
def index():
    """Главная страница"""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"Error loading index.html: {e}", 500

@app.route('/list')
def list_page():
    """Страница списка"""
    try:
        return render_template('list.html')
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"Error loading list.html: {e}", 500

@app.route('/test')
def test():
    """Тестовый маршрут"""
    sheet, _ = get_google_client()
    return jsonify({
        'status': 'working',
        'google_connected': sheet is not None,
        'spreadsheet_id': SPREADSHEET_ID[:10] + '...' if SPREADSHEET_ID else 'not set',
        'credentials_set': bool(os.environ.get('GOOGLE_SHEETS_CREDENTIALS'))
    })

@app.route('/api/characters', methods=['GET'])
def get_characters():
    """API: получить список всех персонажей"""
    try:
        sheet, _ = get_google_client()
        if not sheet:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
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
        
        return jsonify({'characters': characters, 'count': len(characters)}), 200
    except Exception as e:
        logger.error(f"Ошибка получения списка: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/character/<int:row_number>', methods=['GET'])
def get_character(row_number):
    """API: получить конкретного персонажа"""
    try:
        sheet, _ = get_google_client()
        if not sheet:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
        row = sheet.row_values(row_number)
        headers = sheet.row_values(1)
        character = dict(zip(headers, row))
        return jsonify(character), 200
    except Exception as e:
        logger.error(f"Ошибка получения персонажа: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/character/check', methods=['POST'])
def check_character_name():
    """API: проверить существование имени"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'exists': False}), 200
        
        sheet, _ = get_google_client()
        if not sheet:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
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
    """API: сохранить персонажа"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        sheet, _ = get_google_client()
        if not sheet:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
        # Проверяем заголовки
        ensure_headers(sheet)
        
        # Если имя пустое, создаем "Без имени X"
        if not name:
            records = sheet.get_all_records()
            unnamed_count = sum(1 for r in records if not r.get('name', '').strip())
            name = f"Без имени {unnamed_count + 1}"
        
        overwrite = data.get('overwrite', False)
        existing_row = data.get('existing_row')
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        
        row_data = [
            timestamp, record_id, name,
            data.get('race', ''), data.get('profession', ''),
            data.get('status', ''), data.get('current_time', ''),
            data.get('location', ''), data.get('inventory', ''),
            data.get('birth_date', ''), data.get('birth_place', ''),
            data.get('lifespan', ''), data.get('star_sign', ''),
            data.get('first_appearance', ''), data.get('status_title', ''),
            data.get('biography', ''), data.get('appearance', ''),
            data.get('personality', '')
        ]
        
        if overwrite and existing_row:
            # Обновляем существующую запись
            for col, value in enumerate(row_data, start=1):
                sheet.update_cell(existing_row, col, value)
            message = f"Персонаж '{name}' обновлен!"
        else:
            # Добавляем новую запись
            sheet.append_row(row_data)
            message = f"Персонаж '{name}' успешно создан!"
        
        return jsonify({
            'message': message,
            'name': name,
            'timestamp': timestamp,
            'status': 'success'
        }), 200
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/character/delete/<int:row_number>', methods=['DELETE'])
def delete_character(row_number):
    """API: удалить персонажа"""
    try:
        sheet, _ = get_google_client()
        if not sheet:
            return jsonify({'error': 'Не подключено к Google Sheets'}), 500
        
        name = sheet.cell(row_number, 3).value
        sheet.delete_rows(row_number)
        
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
