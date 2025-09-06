import json
import os
import uuid  # импортируем отдельно
import sys
import requests
sys.stdout.reconfigure(encoding='utf-8')
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort,send_file
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename


app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
app.secret_key = 'supersecretkey'


# ====================== Telegram BOT ======================
TELEGRAM_BOT_TOKEN = '7726856877:AAFIslzTXmB5FCw2zDHuPswiybUaCGxiNSw'
TELEGRAM_CHAT_ID = '2045150846'

def send_telegram_notification(username, message_type, amount=None, payment_method=None, order_data=None):
    # Проверяем, что настройки Telegram существуют
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram notifications are not configured")
        return None

    messages = {
        'registration': f"🆕 Новый пользователь зарегистрирован!\nUsername: {username}",
        'payment': f"💳 Новое пополнение баланса!\n\n"
                  f"👤 Пользователь: {username}\n"
                  f"💰 Сумма: {amount} USD\n"
                  f"🔧 Метод: {payment_method}\n"
                  f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        'new_order': f"🛒 Новый заказ!\n\n"
                    f"👤 Пользователь: {username}\n"
                    f"📦 Заказ: {order_data.get('product', 'N/A') if order_data else 'N/A'}\n"
                    f"🔢 Количество: {order_data.get('quantity', 1) if order_data else 1}\n"
                    f"💵 Сумма: {order_data.get('amount', 0) if order_data else 0} USD\n"
                    f"📅 Дата: {order_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')) if order_data else datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"🆔 ID заказа: {order_data.get('id', 'N/A') if order_data else 'N/A'}\n"
                    f"🚩 Логин: {order_data.get('steamLogin', 'N/A') if order_data else 'N/A'}"  # Добавлено новое поле
    }
    
    message = messages.get(message_type)
    if not message:
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")
        return None



DEFAULT_STEAM_SETTINGS = {
    'base_fee': 10,  # 10% базовая комиссия
    'discount_levels': [
        (0, 0),     # 0% - базовый уровень
        (50, 2),    # 2% - 50 на балансе
        (500, 20),  # 20% - 500 на балансе
        (1000, 25), # 25% - 1k на балансе
        (2000, 30), # 30% - 2k на балансе
        (4000, 35)  # 35% - 4k на балансе
    ]
}



global steam_discount_levels, steam_base_fee
steam_discount_levels = DEFAULT_STEAM_SETTINGS['discount_levels']
steam_base_fee = DEFAULT_STEAM_SETTINGS['base_fee']


# Пути к файлам для хранения данных
USERS_FILE = 'users.json'
REFERRALS_FILE = 'referrals.json'
PROMOCODES_FILE = 'promocodes.json'
REWARDS_FILE = 'rewards.json'
USER_REWARDS_FILE = 'user_rewards.json'  # Новый файл для хранения наград пользователей
AFFILIATES_FILE = 'affiliates.json'
PARTNERS_FILE = 'partners.json'
PAYMENTS_FILE = 'payments.json'
PRODUCTS_FILE = 'products.json'
CARDS_FILE = 'cards.json'
WHITELIST_FILE = 'whitelist_users.json'
STEAM_DISCOUNTS_FILE = 'steam_discounts.json'
STORES_FILE = 'stores.json'
RESELLER_FILE = 'reseller_stores.json'


# Загрузка данных из файлов
def load_data():
    global users, referrals, promocodes, rewards, user_rewards
    global affiliate_users, partners_data, affiliate_payments, products, cards, whitelist_users
    global active_bonuses, steam_discount_levels, steam_base_fee, stores, reseller_stores
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  # Добавляем глобальные переменные для Telegra

    try:
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
    except FileNotFoundError:
        users = {}

    try:
        with open(RESELLER_FILE, 'r') as f:
            reseller_stores = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        reseller_stores = []

    try:
        with open(STEAM_DISCOUNTS_FILE, 'r') as f:
            steam_settings = json.load(f)
            # Проверяем тип данных - если это список, преобразуем в новый формат
            if isinstance(steam_settings, list):
                steam_settings = {
                    'base_fee': 10,
                    'discount_levels': steam_settings
                }
            steam_discount_levels = steam_settings.get('discount_levels', [])
            steam_base_fee = steam_settings.get('base_fee', 10)  # 10% по умолчанию
    except FileNotFoundError:
        steam_settings = DEFAULT_STEAM_SETTINGS
        steam_discount_levels = steam_settings['discount_levels']
        steam_base_fee = steam_settings['base_fee']

    try:
        with open(REFERRALS_FILE, 'r') as f:
            referrals = json.load(f)
    except FileNotFoundError:
        referrals = {}

    try:
        with open(STORES_FILE, 'r') as f:
            stores = json.load(f)
    except FileNotFoundError:
        stores = {}

    try:
        with open(PROMOCODES_FILE, 'r') as f:
            promocodes = json.load(f)
    except FileNotFoundError:
        promocodes = {}

    try:
        with open(REWARDS_FILE, 'r') as f:
            rewards = json.load(f)
    except FileNotFoundError:
        rewards = []  # Список доступных наград (названия)

    try:
        with open(USER_REWARDS_FILE, 'r') as f:
            user_rewards = json.load(f)
    except FileNotFoundError:
        user_rewards = {}  # Словарь с наградами пользователей
        
        # Инициализация user_rewards на основе существующих пользователей
        for username in users.keys():
            user_rewards[username] = {
                'purchases': users[username].get('orders', 0),
                'assigned_reward': None,
                'reward_status': None
            }

    try:
        with open(AFFILIATES_FILE, 'r') as f:
            affiliate_users = json.load(f)
    except FileNotFoundError:
        affiliate_users = []

    try:
        with open(PARTNERS_FILE, 'r') as f:
            partners_data = json.load(f)
    except FileNotFoundError:
        partners_data = []

    try:
        with open(PAYMENTS_FILE, 'r') as f:
            affiliate_payments = json.load(f)
    except FileNotFoundError:
        affiliate_payments = []

    try:
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except FileNotFoundError:
        products = {}

    try:
        with open(CARDS_FILE, 'r') as f:
            cards = json.load(f)
    except FileNotFoundError:
        cards = []

    try:
        with open(WHITELIST_FILE, 'r') as f:
            whitelist_users = json.load(f)
    except FileNotFoundError:
        whitelist_users = []
    try:
        with open('telegram_settings.json', 'r') as f:
            telegram_settings = json.load(f)
        TELEGRAM_BOT_TOKEN = telegram_settings.get('bot_token', '')
        TELEGRAM_CHAT_ID = telegram_settings.get('chat_id', '')
    except FileNotFoundError:
        TELEGRAM_BOT_TOKEN = '7726856877:AAFIslzTXmB5FCw2zDHuPswiybUaCGxiNSw'  # дефолтные значения
        TELEGRAM_CHAT_ID = '2045150846'

    active_bonuses = []  # Список активных бонусов

# Сохранение данных в файлы
def save_data():
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)
    with open(REFERRALS_FILE, 'w') as f:
        json.dump(referrals, f, indent=4)
    with open(PROMOCODES_FILE, 'w') as f:
        json.dump(promocodes, f, indent=4)
    with open(REWARDS_FILE, 'w') as f:
        json.dump(rewards, f, indent=4)
    with open(USER_REWARDS_FILE, 'w') as f:  # Сохраняем награды пользователей
        json.dump(user_rewards, f, indent=4)
    with open(AFFILIATES_FILE, 'w') as f:
        json.dump(affiliate_users, f, indent=4)
    with open(PARTNERS_FILE, 'w') as f:
        json.dump(partners_data, f, indent=4)
    with open(PAYMENTS_FILE, 'w') as f:
        json.dump(affiliate_payments, f, indent=4)
    with open(PRODUCTS_FILE, 'w') as f:
        json.dump(products, f, indent=4)
    with open(CARDS_FILE, 'w') as f:
        json.dump(cards, f, indent=4)
    with open(WHITELIST_FILE, 'w') as f:
        json.dump(whitelist_users, f, indent=4)
    with open(STEAM_DISCOUNTS_FILE, 'w') as f:
        json.dump({
            'base_fee': steam_base_fee,
            'discount_levels': steam_discount_levels
        }, f, indent=4)
    with open(STORES_FILE, 'w') as f:
        json.dump(stores, f, indent=4)
    with open(RESELLER_FILE, 'w') as f:
        json.dump(reseller_stores, f, indent=4)


def check_blocked(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' in session:
            username = session['username']
            load_data()  # Загружаем актуальные данные
            if username in users and users[username].get('is_banned', False):
                return render_template('blocked_account.html', username=username)  
        return f(*args, **kwargs)
    return decorated_function



@app.route('/admin/data-management')
def data_management():
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403
    return render_template('admin_data_management.html')

@app.route('/admin/export-data')
def export_data():
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data_type = request.args.get('type', 'all')
    
    try:
        if data_type == 'users':
            data = users
        elif data_type == 'orders':
            data = {}
            for user, user_data in users.items():
                if 'orders' in user_data:
                    data[user] = user_data['orders']
        elif data_type == 'payments':
            data = affiliate_payments
        elif data_type == 'whitelist':
            data = whitelist_users
        elif data_type == 'products':
            data = products
        elif data_type == 'referrals':
            data = referrals
        elif data_type == 'promocodes':
            data = promocodes
        elif data_type == 'affiliates':
            data = affiliate_users
        elif data_type == 'partners':
            data = partners_data
        elif data_type == 'rewards':
            data = rewards
        elif data_type == 'user_rewards':
            data = user_rewards
        elif data_type == 'cards':
            data = cards
        elif data_type == 'steam_discounts':
            data = {
                'base_fee': steam_base_fee,
                'discount_levels': steam_discount_levels
            }
        elif data_type == 'stores':
            data = stores
        elif data_type == 'reseller_stores':
            data = reseller_stores
        elif data_type == 'all':
            data = {
                'users': users,
                'referrals': referrals,
                'promocodes': promocodes,
                'affiliates': affiliate_users,
                'partners': partners_data,
                'payments': affiliate_payments,
                'products': products,
                'whitelist': whitelist_users,
                'rewards': rewards,
                'user_rewards': user_rewards,
                'cards': cards,
                'steam_discounts': {
                    'base_fee': steam_base_fee,
                    'discount_levels': steam_discount_levels
                },
                'stores': stores,
                'reseller_stores': reseller_stores
            }
        else:
            return jsonify({'success': False, 'message': 'Invalid data type'}), 400
        
        return jsonify({'success': True, 'data': data, 'type': data_type})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/import-data', methods=['POST'])
def import_data():
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    # Объявляем все глобальные переменные
    global users, referrals, promocodes, affiliate_users, partners_data, affiliate_payments
    global products, whitelist_users, rewards, user_rewards, cards, steam_base_fee, steam_discount_levels
    global stores, reseller_stores
    
    try:
        # Проверяем, загружен ли файл
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'message': 'No file selected'}), 400
            
            if file and file.filename.endswith('.json'):
                filename = secure_filename(file.filename)
                data_type = request.form.get('data_type', 'all')
                
                # Читаем и парсим JSON
                json_data = json.load(file)
                
                # Обрабатываем импорт в зависимости от типа данных
                if data_type == 'users':
                    users = json_data
                elif data_type == 'orders':
                    for user, orders in json_data.items():
                        if user in users:
                            users[user]['orders'] = orders
                elif data_type == 'payments':
                    affiliate_payments = json_data
                elif data_type == 'whitelist':
                    whitelist_users = json_data
                elif data_type == 'products':
                    products = json_data
                elif data_type == 'referrals':
                    referrals = json_data
                elif data_type == 'promocodes':
                    promocodes = json_data
                elif data_type == 'affiliates':
                    affiliate_users = json_data
                elif data_type == 'partners':
                    partners_data = json_data
                elif data_type == 'rewards':
                    rewards = json_data
                elif data_type == 'user_rewards':
                    user_rewards = json_data
                elif data_type == 'cards':
                    cards = json_data
                elif data_type == 'steam_discounts':
                    steam_base_fee = json_data.get('base_fee', 10)
                    steam_discount_levels = json_data.get('discount_levels', [])
                elif data_type == 'stores':
                    stores = json_data
                elif data_type == 'reseller_stores':
                    reseller_stores = json_data
                elif data_type == 'all':
                    users = json_data.get('users', users)
                    referrals = json_data.get('referrals', referrals)
                    promocodes = json_data.get('promocodes', promocodes)
                    affiliate_users = json_data.get('affiliates', affiliate_users)
                    partners_data = json_data.get('partners', partners_data)
                    affiliate_payments = json_data.get('payments', affiliate_payments)
                    products = json_data.get('products', products)
                    whitelist_users = json_data.get('whitelist', whitelist_users)
                    rewards = json_data.get('rewards', rewards)
                    user_rewards = json_data.get('user_rewards', user_rewards)
                    cards = json_data.get('cards', cards)
                    steam_settings = json_data.get('steam_discounts', {})
                    steam_base_fee = steam_settings.get('base_fee', steam_base_fee)
                    steam_discount_levels = steam_settings.get('discount_levels', steam_discount_levels)
                    stores = json_data.get('stores', stores)
                    reseller_stores = json_data.get('reseller_stores', reseller_stores)
                
                # Сохраняем данные
                save_data()
                
                return jsonify({'success': True, 'message': 'Data imported successfully', 'type': data_type})
            else:
                return jsonify({'success': False, 'message': 'Invalid file type'}), 400
        else:
            # Обрабатываем JSON данные из предпросмотра
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400
            
            data_type = data.get('type', 'all')
            json_data = data.get('data', {})
            
            # Обрабатываем импорт в зависимости от типа данных
            if data_type == 'users':
                users = json_data
            elif data_type == 'orders':
                for user, orders in json_data.items():
                    if user in users:
                        users[user]['orders'] = orders
            elif data_type == 'payments':
                affiliate_payments = json_data
            elif data_type == 'whitelist':
                whitelist_users = json_data
            elif data_type == 'products':
                products = json_data
            elif data_type == 'referrals':
                referrals = json_data
            elif data_type == 'promocodes':
                promocodes = json_data
            elif data_type == 'affiliates':
                affiliate_users = json_data
            elif data_type == 'partners':
                partners_data = json_data
            elif data_type == 'rewards':
                rewards = json_data
            elif data_type == 'user_rewards':
                user_rewards = json_data
            elif data_type == 'cards':
                cards = json_data
            elif data_type == 'steam_discounts':
                steam_base_fee = json_data.get('base_fee', 10)
                steam_discount_levels = json_data.get('discount_levels', [])
            elif data_type == 'stores':
                stores = json_data
            elif data_type == 'reseller_stores':
                reseller_stores = json_data
            elif data_type == 'all':
                users = json_data.get('users', users)
                referrals = json_data.get('referrals', referrals)
                promocodes = json_data.get('promocodes', promocodes)
                affiliate_users = json_data.get('affiliates', affiliate_users)
                partners_data = json_data.get('partners', partners_data)
                affiliate_payments = json_data.get('payments', affiliate_payments)
                products = json_data.get('products', products)
                whitelist_users = json_data.get('whitelist', whitelist_users)
                rewards = json_data.get('rewards', rewards)
                user_rewards = json_data.get('user_rewards', user_rewards)
                cards = json_data.get('cards', cards)
                steam_settings = json_data.get('steam_discounts', {})
                steam_base_fee = steam_settings.get('base_fee', steam_base_fee)
                steam_discount_levels = steam_settings.get('discount_levels', steam_discount_levels)
                stores = json_data.get('stores', stores)
                reseller_stores = json_data.get('reseller_stores', reseller_stores)
            
            # Сохраняем данные
            save_data()
            
            return jsonify({'success': True, 'message': 'Data imported successfully', 'type': data_type})
    
    except json.JSONDecodeError:
        return jsonify({'success': False, 'message': 'Invalid JSON format'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/admin/download-file')
def download_file():
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    filename = request.args.get('filename')
    if not filename or not os.path.exists(filename):
        return jsonify({'success': False, 'message': 'File not found'}), 404
    
    return send_file(filename, as_attachment=True)



# Главная страница регистрации
@app.route('/register', methods=['GET', 'POST'])
def register():
    load_data()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password1']
        password_confirm = request.form['password2']
        if password != password_confirm:
            flash('The passwords do not match', 'error')
            return render_template('register.html')
        if username in users:
            flash('Username already exists', 'error')
            return render_template('register.html')
        
        users[username] = {'password': password,
                          'balance': {'trc20': 0, 'erc20': 0, 'bep20': 0, 'card': 0},
                          'orders': 0,
                          'expenses': 0,
                          'userorders': [],
                          'topups': []
                         }
        save_data()
        
        # Отправляем уведомление в Telegram
        send_telegram_notification(username, 'registration')
        
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/register/<ref_code>', methods=['GET', 'POST'])
def register_ref(ref_code):
    load_data()
    if ref_code not in referrals:
        return "Реферальная ссылка не найдена", 404

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password1']
        password_confirm = request.form['password2']

        if password != password_confirm:
            flash('The passwords do not match', 'error')
            return render_template('register.html')

        if username in users:
            flash('Username already exists', 'error')

        users[username] = {
            'password': password,
            'balance': {'trc20': 0, 'erc20': 0, 'bep20': 0, 'card': 0},
            'orders': 0,
            'expenses': 0,
            'userorders': [],
            'topups': []
        }

        if username and password:
            referrals[ref_code].append({
                'name': username,
                'deposit': 0,
                'status': 'pending',
                'payout': 0
            })

        save_data()  # Сохраняем данные в файл
        return redirect(url_for('login'))

    return render_template('register.html', ref_code=ref_code)

# Страница входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    load_data()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username]['password'] == password:
            session['username'] = username
            return redirect(url_for('dashboard'))
        flash("Incorrect username or password!", 'error')  # Добавляем сообщение об ошибке
        return redirect(url_for('login'))  # Перенаправляем обратно на страницу входа
    return render_template('login.html')

# Загрузка данных при старте приложения
load_data()





# Страница Admin
@app.route('/admin/users', methods=['GET', 'POST'])
def admin_users():
    load_data()
    
    # Проверка авторизации и прав администратора
    if 'username' not in session:
        return redirect(url_for('login'))
    if session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён: только для администратора!", 403

    if request.method == 'POST':
        action = request.form.get('action')
        target_user = request.form.get('target_user')

        if target_user in users:
            if action == 'update_user':
                # Обработка обновления статуса пользователя и KYC
                is_banned = request.form.get('is_banned', 'false') == 'true'
                kyc_status = request.form.get('kyc_status', 'not_required')
                
                # Обновляем данные пользователя
                users[target_user]['is_banned'] = is_banned
                users[target_user]['kyc_status'] = kyc_status
                users[target_user]['kyc_verified'] = kyc_status == 'verified'
                
                # Если KYC пройден, снимаем флаги ограничений
                if kyc_status == 'verified':
                    users[target_user].pop('kyc_prompt_shown', None)
                    users[target_user].pop('had_high_balance', None)
                
                flash(f'Данные пользователя {target_user} успешно обновлены', 'success')
                save_data()
                return redirect(url_for('admin_users'))

            elif action == 'edit_balance':
                # Обработка изменения баланса
                balance_type = request.form.get('balance_type')
                new_value = float(request.form.get('new_balance'))
                if balance_type in users[target_user]['balance']:
                    users[target_user]['balance'][balance_type] = new_value
                elif balance_type in ['orders', 'expenses']:
                    users[target_user][balance_type] = new_value
                flash(f'Баланс {balance_type} для {target_user} обновлен', 'success')

            elif action == 'edit_topup':
                # Обработка пополнения
                date = request.form.get('date')
                network = request.form.get('network')
                amount = float(request.form.get('amount'))
                status = request.form.get('status')

                try:
                    if 'T' in date:
                        dt = datetime.fromisoformat(date)
                        formatted_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        dt = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
                        formatted_date = date
                except Exception as e:
                    print(f"Ошибка обработки даты: {e}")
                    dt = datetime.now()
                    formatted_date = dt.strftime('%Y-%m-%d %H:%M:%S')

                if network in ['BEP20', 'Card', 'TRC20', 'ERC20']:
                    topup_found = False
                    for topup in users[target_user].get('topups', []):
                        if topup['date'] == formatted_date and topup['network'] == network:
                            topup['amount'] = amount
                            topup['status'] = status
                            topup_found = True
                            break

                    if not topup_found:
                        if 'topups' not in users[target_user]:
                            users[target_user]['topups'] = []
                        users[target_user]['topups'].append({
                            'date': formatted_date,
                            'network': network,
                            'amount': amount,
                            'status': status
                        })

                    if status == 'Success':
                        balance_key = network.lower() if network != 'Card' else 'card'
                        users[target_user]['balance'][balance_key] = users[target_user]['balance'].get(balance_key, 0) + amount
                
                flash('Пополнение успешно добавлено/обновлено', 'success')

            elif action == 'edit_topup_status':
                # Обработка изменения статуса пополнения
                date = request.form.get('date')
                network = request.form.get('network')
                new_status = request.form.get('new_status')

                try:
                    if 'T' in date:
                        dt = datetime.fromisoformat(date)
                        formatted_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        dt = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
                        formatted_date = date
                except Exception as e:
                    print(f"Ошибка обработки даты: {e}")
                    formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                for topup in users[target_user].get('topups', []):
                    if topup['date'] == formatted_date and topup['network'] == network:
                        old_status = topup['status']
                        topup['status'] = new_status

                        if new_status == 'Success' and old_status != 'Success':
                            balance_key = network.lower() if network != 'Card' else 'card'
                            users[target_user]['balance'][balance_key] = users[target_user]['balance'].get(balance_key, 0) + topup['amount']
                        elif old_status == 'Success' and new_status != 'Success':
                            balance_key = network.lower() if network != 'Card' else 'card'
                            users[target_user]['balance'][balance_key] = users[target_user]['balance'].get(balance_key, 0) - topup['amount']
                        break
                
                flash('Статус пополнения обновлен', 'success')

            elif action == 'delete_user':
                del users[target_user]
                flash(f'Пользователь {target_user} удален', 'success')

            elif action == 'delete_topup':
                date = request.form.get('date')
                network = request.form.get('network')
                
                try:
                    if 'T' in date:
                        dt = datetime.fromisoformat(date)
                        formatted_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        dt = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
                        formatted_date = date
                except Exception as e:
                    print(f"Ошибка обработки даты: {e}")
                    formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                users[target_user]['topups'] = [
                    topup for topup in users[target_user].get('topups', [])
                    if not (topup['date'] == formatted_date and topup['network'] == network)
                ]
                
                flash('Запись о пополнении удалена', 'success')

            save_data()

    # Сортировка пополнений по дате (новые сверху)
    for user, info in users.items():
        if 'topups' in info:
            def get_datetime(topup):
                date_str = topup['date']
                try:
                    if 'T' in date_str:
                        return datetime.fromisoformat(date_str)
                    else:
                        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                except:
                    return datetime.min
                    
            info['topups'] = sorted(info['topups'], key=get_datetime, reverse=True)

    return render_template('admin_users.html', 
                         users=users, 
                         now=datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                         kyc_statuses=['not_required', 'pending', 'verified'])

@app.route('/admin/delete_all_topups', methods=['POST'])
def delete_all_topups():
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    # Удаляем все пополнения у всех пользователей
    for user, info in users.items():
        if 'topups' in info:
            info['topups'] = []
    
    save_data()
    flash('Все пополнения всех пользователей удалены', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user_topups/<user>', methods=['POST'])
def delete_user_topups(user):
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    if user in users and 'topups' in users[user]:
        users[user]['topups'] = []
        save_data()
        flash(f'Все пополнения пользователя {user} удалены', 'success')
    else:
        flash('Пользователь не найден или у него нет пополнений', 'error')
    
    return redirect(url_for('admin_users'))




@app.route('/admin/create_code', methods=['POST'])
def create_code():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    if session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён: только для администратора!", 403

    # Получаем данные из формы
    product_id = request.form.get('product_id')
    new_code = request.form.get('new_code')
    
    # Находим категорию по product_id
    category = None
    for key in products:
        if product_id in products[key]:
            category = key
            break

    if category:
        # Добавляем новый код в список "codes"
        if isinstance(products[category][product_id], dict):
            products[category][product_id]["codes"].append(new_code)
        else:
            # Если структура данных отличается, можно создать список
            products[category][product_id] = {
                "description": products[category][product_id],
                "codes": [new_code]
            }

        # Сохраняем изменения в файле products.json
        save_data()

    return redirect(url_for('adminlots'))

@app.route('/admin/delete_code', methods=['POST'])
def delete_code():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    if session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён: только для администратора!", 403

    # Получаем данные из формы
    product_id = request.form.get('product_id')
    code_to_delete = request.form.get('code')
    
    # Находим категорию по product_id
    category = None
    for key in products:
        if product_id in products[key]:
            category = key
            break

    if category and code_to_delete in products[category][product_id]["codes"]:
        # Удаляем код из списка
        products[category][product_id]["codes"].remove(code_to_delete)
        
        # Сохраняем изменения в файл products.json
        save_data()

    return redirect(url_for('adminlots'))



@app.route('/admin/orders', methods=['GET', 'POST'])
def admin2():
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    if request.method == 'POST':
        target_user = request.form.get('target_user')
        category = request.form.get('category')
        product = request.form.get('product')
        price = request.form.get('price')
        amount = request.form.get('amount')
        date = request.form.get('date')

        if date:
            try:
                try:
                    date_obj = datetime.strptime(date, '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    date_obj = datetime.strptime(date, '%Y-%m-%dT%H:%M')
                formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if target_user in users:
            new_order = {
                'id': str(uuid.uuid4()),
                'category': category,
                'product': product,
                'price': price,
                'amount': amount,
                'date': formatted_date,
                'timestamp': datetime.now().timestamp(),
                'status': 'pending'
            }
            if 'userorders' not in users[target_user]:
                users[target_user]['userorders'] = []
            users[target_user]['userorders'].append(new_order)
            save_data()

    all_orders = []
    recent_orders = []
    
    for user, info in users.items():
        if 'userorders' in info:
            for order in info['userorders']:
                if 'status' not in order:
                    order['status'] = 'pending'
                
                order_with_user = order.copy()
                order_with_user['user'] = user
                all_orders.append(order_with_user)
            
            info['userorders'].sort(
                key=lambda x: (
                    datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S').timestamp(),
                    x['timestamp']
                ),
                reverse=True
            )
    
    all_orders.sort(
        key=lambda x: (
            datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S').timestamp(),
            x['timestamp']
        ),
        reverse=True
    )
    
    recent_orders = all_orders[:15]
    
    save_data()
    
    return render_template(
        'admin_orders.html', 
        users=users,
        recent_orders=recent_orders,
        all_orders=all_orders
    )

@app.route('/admin/update_order_status/<user>/<order_id>', methods=['POST'])
def update_order_status(user, order_id):
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    new_status = request.form.get('status')
    if user in users and 'userorders' in users[user]:
        for order in users[user]['userorders']:
            if order['id'] == order_id:
                old_status = order.get('status', 'pending')
                order['status'] = new_status
                
                if new_status == 'canceled' and old_status != 'canceled':
                    try:
                        price = float(order['price'])
                        amount = int(order['amount'])
                        total_refund = price * amount
                        
                        if 'balance' not in users[user]:
                            users[user]['balance'] = {}
                        
                        if 'USD' not in users[user]['balance']:
                            users[user]['balance']['USD'] = 0.0
                        
                        users[user]['balance']['USD'] += total_refund
                    except (ValueError, KeyError) as e:
                        print(f"Ошибка при возврате средств: {e}")
                
                save_data()
                break
    
    return redirect(url_for('admin2'))

@app.route('/admin/delete_order/<user>/<order_id>', methods=['POST'])
def delete_order(user, order_id):
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    if user in users and 'userorders' in users[user]:
        users[user]['userorders'] = [o for o in users[user]['userorders'] if o['id'] != order_id]
        save_data()
    
    return redirect(url_for('admin2'))

@app.route('/admin/save_key/<user>/<order_id>', methods=['POST'])
def save_key(user, order_id):
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    key = request.form.get('key')
    if user in users and 'userorders' in users[user]:
        for order in users[user]['userorders']:
            if order['id'] == order_id:
                order['key'] = key
                break
        save_data()
    
    return redirect(url_for('admin2'))

@app.route('/admin/update_order_date/<user>/<order_id>', methods=['POST'])
def update_order_date(user, order_id):
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    new_date = request.form.get('new_date')
    if user in users and 'userorders' in users[user]:
        for order in users[user]['userorders']:
            if order['id'] == order_id:
                try:
                    formats = [
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%dT%H:%M',
                        '%Y-%m-%d %H:%M:%S',
                        '%Y-%m-%d %H:%M'
                    ]
                    
                    parsed_date = None
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(new_date, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if parsed_date:
                        order['date'] = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
                        order['timestamp'] = datetime.now().timestamp()
                        save_data()
                except Exception as e:
                    print(f"Ошибка: {e}")
                break
    
    return redirect(url_for('admin2'))

@app.route('/admin/delete_all_orders', methods=['POST'])
def delete_all_orders():
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    for user, info in users.items():
        if 'userorders' in info:
            info['userorders'] = []
    
    save_data()
    flash('Все заказы всех пользователей удалены', 'success')
    return redirect(url_for('admin2'))

@app.route('/admin/delete_user_orders/<user>', methods=['POST'])
def delete_user_orders(user):
    load_data()
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён", 403

    if user in users and 'userorders' in users[user]:
        users[user]['userorders'] = []
        save_data()
        flash(f'Все заказы пользователя {user} удалены', 'success')
    else:
        flash('Пользователь не найден или у него нет заказов', 'error')
    
    return redirect(url_for('admin2'))

@app.route('/orders')
@check_blocked
def orders():
    load_data()
    if 'username' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))

    username = session['username']
    if username not in users:
        flash('User not found', 'error')
        return redirect(url_for('login'))

    user_info = users[username]
    balances = user_info.get('balance', {})
    userorders = user_info.get('userorders', [])
    kyc_verified = user_info.get('kyc_verified', False)
    
    userorders.sort(
        key=lambda x: (
            datetime.strptime(x['date'], '%Y-%m-%d %H:%M:%S').timestamp(),
            x['timestamp']
        ),
        reverse=True
    )

    if userorders:
        last_order = userorders[0]
        if not last_order.get('notification_sent'):
            send_telegram_notification(
                username=username,
                message_type='new_order',
                order_data=last_order
            )
            last_order['notification_sent'] = True
            save_data()

    return render_template('orders.html',
                         username=username,
                         balances=balances,
                         userorders=userorders,
                         kyc_verified=kyc_verified)





@app.route('/admin/payments', methods=['GET', 'POST'])
def admin3():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён: только для администратора!", 403

    # Загрузка платежных карт и адресов
    if 'payments' not in users:
        users['payments'] = {"bep20": "", "erc20": "", "trc20": "", "sol": "", "near": ""}

    # Обработка POST-запросов
    if request.method == 'POST':
        if 'delete_card' in request.form:
            # Удаление карты по ID
            card_id = request.form['delete_card']
            global cards
            cards = [card for card in cards if card['id'] != card_id]
            save_data()  # Сохраняем данные после удаления карты

        elif 'delete' in request.form:
            # Удаление адреса
            currency = request.form['delete']
            users['payments'][currency] = ""
            save_data()  # Сохраняем данные после изменения адреса

        else:
            # Сохранение введенных адресов
            for currency in users['payments'].keys():
                users['payments'][currency] = request.form.get(currency, "")
            save_data()  # Сохраняем данные после изменения адресов

    # Отображаем список карт и адресов
    return render_template('admin_payments.html', 
                           users=users, 
                           payments=users['payments'], 
                           cards=cards)  # Передаем и карты, и адреса для отображения








@app.route('/reseller', methods=['GET', 'POST'])
@check_blocked
def reseller():
    # Загрузка данных
    with open(USERS_FILE, 'r') as users_file:
        users = json.load(users_file)
    with open(STORES_FILE, 'r') as stores_file:
        stores = json.load(stores_file)
    try:
        with open(RESELLER_FILE, 'r') as reseller_file:
            reseller_data = json.load(reseller_file)
    except (FileNotFoundError, json.JSONDecodeError):
        reseller_data = {}

    # Загрузка цены реселлерского магазина из настроек
    try:
        with open('financial_settings.json', 'r') as f:
            financial_settings = json.load(f)
            reseller_cost = float(financial_settings.get('reseller_price', 15.00))
    except (FileNotFoundError, json.JSONDecodeError):
        reseller_cost = 15.00  # Значение по умолчанию

    # Проверка авторизации
    if 'username' not in session:
        flash('Please login to access this page', 'error')
        return redirect(url_for('login'))

    username = session['username']
    user_data = users.get(username, {})
    balances = user_data.get('balance', {'card': 0, 'bep20': 0})
    kyc_verified = user_data.get('kyc_verified', False)
    
    # Проверка наличия активного магазина
    user_store = stores.get(username)
    if not user_store or user_store.get('status') != 'active':
        flash('You need an active store to access reseller program', 'error')
        return redirect(url_for('affilate'))

    # Фильтрация магазинов пользователя
    user_reseller_stores = [store for slug, store in reseller_data.items() 
                          if store['owner'] == username]

    # Обработка POST-запросов
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Обработка создания нового магазина
        if not action and request.form.get('store_name'):
            # УБРАНО ТРЕБОВАНИЕ KYC ВЕРИФИКАЦИИ
            store_name = request.form.get('store_name', '').strip()
            store_slug = request.form.get('store_slug', '').strip()
            
            # Валидация
            if not store_name or not store_slug:
                return jsonify({
                    'success': False,
                    'message': 'Store name and URL are required'
                }), 400

            # Проверка уникальности URL
            if store_slug in reseller_data:
                return jsonify({
                    'success': False,
                    'message': 'This store URL is already taken'
                }), 400

            # Проверка баланса
            if balances.get('card', 0) + balances.get('bep20', 0) < reseller_cost:
                return jsonify({
                    'success': False,
                    'message': f'Insufficient balance to create reseller store (need ${reseller_cost:.2f})'
                }), 400

            # Списание средств
            if balances.get('card', 0) >= reseller_cost:
                balances['card'] -= reseller_cost
            else:
                remaining = reseller_cost - balances.get('card', 0)
                balances['card'] = 0
                balances['bep20'] -= remaining

            # Генерация учетных данных
            admin_username = f"admin_{store_slug[:8]}"
            admin_password = str(uuid.uuid4())[:12]

            # Создание магазина
            new_store = {
                'id': str(uuid.uuid4()),
                'owner': username,
                'name': store_name,
                'slug': store_slug,
                'status': 'processing',
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'admin_username': admin_username,
                'admin_password': admin_password,
                'payment_method': 'balance',
                'initial_payment': reseller_cost,
                'monthly_fee': 0,
                'products': [],
                'orders': [],
                'kyc_verified': kyc_verified
            }
            
            # Сохранение в словаре по slug
            reseller_data[store_slug] = new_store
            
            # Добавление в список заявок (partners.json)
            try:
                with open(PARTNERS_FILE, 'r') as partners_file:
                    partners_data = json.load(partners_file)
            except (FileNotFoundError, json.JSONDecodeError):
                partners_data = []

            new_partner = {
                'username': username,
                'email': user_data.get('email', ''),
                'store_name': store_name,
                'store_slug': store_slug,
                'payment_method': 'balance',
                'initial_payment': reseller_cost,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'status': 'pending',
                'admin_username': admin_username,
                'admin_password': admin_password,
                'kyc_verified': kyc_verified
            }
            partners_data.append(new_partner)

            # Обновление данных пользователя
            users[username]['balance'] = balances
            if 'reseller_stores' not in users[username]:
                users[username]['reseller_stores'] = []
            users[username]['reseller_stores'].append(store_slug)

            # Сохранение всех изменений
            with open(USERS_FILE, 'w') as users_file:
                json.dump(users, users_file, indent=4)
            with open(RESELLER_FILE, 'w') as reseller_file:
                json.dump(reseller_data, reseller_file, indent=4)
            with open(PARTNERS_FILE, 'w') as partners_file:
                json.dump(partners_data, partners_file, indent=4)

            return jsonify({
                'success': True,
                'store': new_store,
                'new_balance': balances.get('card', 0) + balances.get('bep20', 0)
            })
        
        # Обработка удаления магазина
        elif action == 'delete_reseller':
            reseller_slug = request.form.get('reseller_id')
            if reseller_slug in reseller_data:
                try:
                    # Создаем резервную копию перед удалением
                    backup_data = reseller_data.copy()
                    store_name = reseller_data[reseller_slug]['name']
                    del reseller_data[reseller_slug]
                    
                    # Обновляем список магазинов пользователя
                    if 'reseller_stores' in users[username]:
                        users[username]['reseller_stores'] = [
                            slug for slug in users[username]['reseller_stores'] 
                            if slug != reseller_slug
                        ]
                    
                    # Сохраняем изменения
                    with open(RESELLER_FILE, 'w') as reseller_file:
                        json.dump(reseller_data, reseller_file, indent=4)
                    with open(USERS_FILE, 'w') as users_file:
                        json.dump(users, users_file, indent=4)
                    
                    flash(f'Reseller store {store_name} deleted successfully', 'success')
                except Exception as e:
                    flash(f'Failed to delete reseller store: {str(e)}', 'error')
                    # Восстанавливаем из резервной копии в случае ошибки
                    reseller_data = backup_data
                    with open(RESELLER_FILE, 'w') as reseller_file:
                        json.dump(reseller_data, reseller_file, indent=4)
            else:
                flash('Reseller store not found', 'error')
            
            return redirect(url_for('reseller'))

    # Рендеринг шаблона
    return render_template(
        'reseller.html',
        username=username,
        balances=balances,
        has_store=True,
        main_store=user_store,
        reseller_stores=user_reseller_stores,
        reseller_cost=reseller_cost,
        kyc_verified=kyc_verified
    )

@app.route('/affilate', methods=['GET', 'POST'])
@check_blocked
def affilate():
    # Загрузка данных из файлов
    with open(USERS_FILE, 'r') as users_file:
        users = json.load(users_file)
    with open(STORES_FILE, 'r') as stores_file:
        stores = json.load(stores_file)
    
    # Загрузка цены магазина из настроек
    try:
        with open('financial_settings.json', 'r') as f:
            financial_settings = json.load(f)
            franchise_cost = float(financial_settings.get('store_price', 50.00))
    except (FileNotFoundError, json.JSONDecodeError):
        franchise_cost = 50.00  # Значение по умолчанию

    # Проверка авторизации пользователя
    if 'username' not in session:
        flash('Please login to access this page', 'error')
        return redirect(url_for('login'))

    username = session['username']
    user_data = users.get(username, {})
    balances = user_data.get('balance', {'card': 0, 'bep20': 0})
    user_email = user_data.get('email', '')
    kyc_verified = user_data.get('kyc_verified', False)

    # Проверка наличия магазина у пользователя
    user_store = stores.get(username)
    has_store = user_store is not None

    if has_store:
        store_slug = user_store.get('slug', '')
        store_status = user_store.get('status', 'active')
        store_stats = {
            'total_sales': user_store.get('total_sales', 0),
            'products': len(user_store.get('products', [])),
            'orders': len(user_store.get('orders', []))
        }
    else:
        store_slug = ''
        store_status = None
        store_stats = None

    # Обработка POST-запросов
    if request.method == 'POST':
        # ⚡ Убрана проверка KYC — теперь магазин можно создать без верификации ⚡

        # Обработка удаления магазина
        if 'action' in request.form and request.form['action'] == 'delete_store':
            if username in stores:
                del stores[username]
                with open(STORES_FILE, 'w') as stores_file:
                    json.dump(stores, stores_file, indent=4)
                flash('Your store has been successfully deleted', 'success')
                return redirect(url_for('affilate'))

        # Обработка создания нового магазина
        store_name = request.form.get('store_name', '').strip()
        store_slug = request.form.get('store_slug', '').strip()
        payment_method = request.form.get('payment_method', 'balance')
        form_email = request.form.get('email', '').strip()
        admin_username = request.form.get('admin_username', '').strip()
        admin_password = request.form.get('admin_password', '').strip()

        email = form_email if form_email else user_email

        # Валидация данных
        if not store_name or not store_slug:
            return jsonify({
                'success': False,
                'message': 'Store name and URL are required'
            }), 400

        # Проверка уникальности URL магазина
        if any(store['slug'] == store_slug for store in stores.values()):
            return jsonify({
                'success': False,
                'message': 'This store URL is already taken'
            }), 400

        if payment_method == 'balance':
            total_balance = balances.get('card', 0) + balances.get('bep20', 0)
            if total_balance < franchise_cost:
                return jsonify({
                    'success': False,
                    'message': f'Insufficient balance to create store (need ${franchise_cost:.2f})'
                }), 400

            # Списание средств с баланса
            if balances.get('card', 0) >= franchise_cost:
                balances['card'] -= franchise_cost
            else:
                remaining = franchise_cost - balances.get('card', 0)
                balances['card'] = 0
                balances['bep20'] -= remaining

        # Создание записи о магазине
        stores[username] = {
            'name': store_name,
            'slug': store_slug,
            'status': 'processing',
            'owner': username,
            'email': email,
            'admin_username': admin_username,
            'admin_password': admin_password,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'total_sales': 0,
            'products': [],
            'orders': [],
            'payment_method': payment_method,
            'initial_payment': franchise_cost,
            'kyc_verified': kyc_verified  # всё ещё сохраняем поле, но оно не требуется
        }

        # Добавление в список заявок (partners.json)
        try:
            with open(PARTNERS_FILE, 'r') as partners_file:
                partners_data = json.load(partners_file)
        except (FileNotFoundError, json.JSONDecodeError):
            partners_data = []

        new_partner = {
            'username': username,
            'email': email,
            'store_name': store_name,
            'store_slug': store_slug,
            'payment_method': payment_method,
            'initial_payment': franchise_cost,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'pending',
            'admin_username': admin_username,
            'admin_password': admin_password,
            'kyc_verified': kyc_verified
        }
        partners_data.append(new_partner)

        # Обновление данных пользователя
        users[username]['balance'] = balances
        if 'stores' not in users[username]:
            users[username]['stores'] = []
        users[username]['stores'].append(store_slug)

        # Сохранение всех изменений
        with open(USERS_FILE, 'w') as users_file:
            json.dump(users, users_file, indent=4)
        with open(STORES_FILE, 'w') as stores_file:
            json.dump(stores, stores_file, indent=4)
        with open(PARTNERS_FILE, 'w') as partners_file:
            json.dump(partners_data, partners_file, indent=4)

        return jsonify({
            'success': True,
            'store_slug': store_slug,
            'new_balance': balances.get('card', 0) + balances.get('bep20', 0),
            'store_status': 'processing'
        })

    # Рендеринг шаблона
    return render_template(
        'my_store.html',
        username=username,
        balances=balances,
        email=user_email,
        has_store=has_store,
        store=user_store,
        store_slug=store_slug,
        store_stats=store_stats,
        store_status=store_status,
        franchise_cost=franchise_cost,
        kyc_verified=kyc_verified
    )


@app.route('/aff/newpartners', methods=['GET', 'POST'])
def aff_partners():
    load_data()
    
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        abort(403)
    
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            username = request.form.get('username')
            
            if not action or not username:
                flash('Invalid request parameters', 'error')
                return redirect(url_for('aff_partners'))

            if username not in stores:
                flash('Store not found', 'error')
                return redirect(url_for('aff_partners'))

            if action == 'approve':
                stores[username]['status'] = 'active'
                flash(f'Store {stores[username]["name"]} approved!', 'success')
            
            elif action == 'reject':
                # Удаляем магазин и возвращаем средства если нужно
                store_data = stores[username]
                if store_data['payment_method'] == 'balance':
                    # Возврат средств
                    if 'balance' not in users[username]:
                        users[username]['balance'] = {'card': 0, 'bep20': 0}
                    users[username]['balance']['card'] += 50.00
                
                del stores[username]
                flash('Store rejected', 'success')
            
            elif action == 'delete':
                # Просто удаляем магазин
                del stores[username]
                flash('Store deleted', 'success')
            
            save_data()
            
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        
        return redirect(url_for('aff_partners'))
    
    # Подготавливаем данные для отображения
    partners = []
    for username, store_data in stores.items():
        if store_data.get('status', 'processing') != 'active':
            partner = {
                'username': username,
                'email': store_data.get('email', ''),
                'store_name': store_data.get('name', ''),
                'store_slug': store_data.get('slug', ''),
                'payment_method': store_data.get('payment_method', 'unknown'),
                'status': store_data.get('status', 'processing')
            }
            partners.append(partner)
    
    return render_template('aff_partners.html', partners=partners)

@app.route('/aff/approved', methods=['GET', 'POST'])
def aff_approved():
    # Загрузка всех необходимых данных
    load_data()
    
    # Проверка авторизации администратора
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        abort(403)
    
    # Инициализация данных
    reseller_data = {}
    try:
        if os.path.exists(RESELLER_FILE) and os.path.getsize(RESELLER_FILE) > 0:
            with open(RESELLER_FILE, 'r', encoding='utf-8') as f:
                reseller_data = json.load(f)
    except Exception as e:
        print(f"Error loading reseller data: {str(e)}")
        flash('Error loading reseller data', 'error')
    
    # Обработка POST-запросов
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            username = request.form.get('username')
            admin_username = request.form.get('admin_username', '').strip()
            admin_password = request.form.get('admin_password', '').strip()
            reseller_slug = request.form.get('reseller_id')
            new_status = request.form.get('new_status')

            # 1. Обработка обновления статуса реселлерского магазина
            if action == 'update_reseller_status' and reseller_slug and new_status:
                if reseller_slug in reseller_data:
                    if new_status in ['processing', 'active', 'declined']:
                        # Сохраняем предыдущий статус для сообщения
                        old_status = reseller_data[reseller_slug].get('status', 'unknown')
                        
                        # Обновляем статус
                        reseller_data[reseller_slug]['status'] = new_status
                        reseller_data[reseller_slug]['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        try:
                            # Сохраняем изменения
                            with open(RESELLER_FILE, 'w', encoding='utf-8') as f:
                                json.dump(reseller_data, f, indent=4, ensure_ascii=False)
                            
                            # Логируем изменение
                            log_message = (f"Status changed from {old_status} to {new_status} "
                                         f"for reseller store {reseller_slug}")
                            print(log_message)
                            flash(log_message, 'success')
                            
                        except Exception as e:
                            error_msg = f'Failed to update status: {str(e)}'
                            print(error_msg)
                            flash(error_msg, 'error')
                    else:
                        flash('Invalid status value. Allowed: processing, active, declined', 'error')
                else:
                    flash('Reseller store not found', 'error')
                return redirect(url_for('aff_approved'))

            # 2. Обработка обновления учетных данных основного магазина
            elif action == 'update_credentials' and username:
                if username in stores:
                    # Валидация данных
                    if not admin_username or not admin_password:
                        flash('Username and password cannot be empty', 'error')
                    else:
                        stores[username]['admin_username'] = admin_username
                        stores[username]['admin_password'] = admin_password
                        stores[username]['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        try:
                            save_data()
                            flash('Admin credentials updated successfully', 'success')
                        except Exception as e:
                            flash(f'Failed to save credentials: {str(e)}', 'error')
                else:
                    flash('Store not found', 'error')

            # 3. Обработка деактивации магазина
            elif action == 'deactivate' and username:
                if username in stores:
                    stores[username]['status'] = 'inactive'
                    stores[username]['deactivated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    try:
                        save_data()
                        flash(f'Store {stores[username]["name"]} deactivated!', 'success')
                    except Exception as e:
                        flash(f'Failed to deactivate store: {str(e)}', 'error')
                else:
                    flash('Store not found', 'error')

            # 4. Обработка удаления магазина
            elif action == 'delete' and username:
                if username in stores:
                    try:
                        # Создаем резервную копию перед удалением
                        store_name = stores[username]['name']
                        del stores[username]
                        
                        save_data()
                        flash(f'Store {store_name} deleted successfully', 'success')
                    except Exception as e:
                        flash(f'Failed to delete store: {str(e)}', 'error')
                else:
                    flash('Store not found', 'error')

            # 5. Обработка обновления учетных данных реселлерского магазина
            elif action == 'update_reseller_credentials' and reseller_slug:
                if reseller_slug in reseller_data:
                    if not admin_username or not admin_password:
                        flash('Username and password cannot be empty', 'error')
                    else:
                        reseller_data[reseller_slug]['admin_username'] = admin_username
                        reseller_data[reseller_slug]['admin_password'] = admin_password
                        reseller_data[reseller_slug]['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        try:
                            with open(RESELLER_FILE, 'w', encoding='utf-8') as f:
                                json.dump(reseller_data, f, indent=4, ensure_ascii=False)
                            flash('Reseller credentials updated', 'success')
                        except Exception as e:
                            flash(f'Failed to update reseller credentials: {str(e)}', 'error')
                else:
                    flash('Reseller store not found', 'error')

            # 6. Обработка удаления реселлерского магазина
            elif action == 'delete_reseller' and reseller_slug:
                if reseller_slug in reseller_data:
                    try:
                        # Создаем резервную копию перед удалением
                        backup_data = reseller_data.copy()
                        store_name = reseller_data[reseller_slug]['name']
                        del reseller_data[reseller_slug]
                        
                        # Попытка сохранения
                        with open(RESELLER_FILE, 'w', encoding='utf-8') as f:
                            json.dump(reseller_data, f, indent=4, ensure_ascii=False)
                            
                        # Проверяем успешность удаления
                        with open(RESELLER_FILE, 'r', encoding='utf-8') as f:
                            updated_data = json.load(f)
                            
                        if reseller_slug not in updated_data:
                            flash(f'Reseller store {store_name} deleted', 'success')
                        else:
                            # Восстанавливаем из резервной копии, если не удалось
                            reseller_data = backup_data
                            with open(RESELLER_FILE, 'w', encoding='utf-8') as f:
                                json.dump(reseller_data, f, indent=4, ensure_ascii=False)
                            flash('Failed to delete reseller store (data not persisted)', 'error')
                            
                    except Exception as e:
                        flash(f'Failed to delete reseller store: {str(e)}', 'error')
                        # В случае ошибки пробуем восстановить данные
                        try:
                            with open(RESELLER_FILE, 'w', encoding='utf-8') as f:
                                json.dump(backup_data, f, indent=4, ensure_ascii=False)
                        except:
                            pass
                else:
                    flash('Reseller store not found', 'error')

        except Exception as e:
            import traceback
            traceback.print_exc()
            flash(f'Unexpected error: {str(e)}', 'error')
        
        return redirect(url_for('aff_approved'))
        
    
    # Подготовка данных для отображения
    partners = []
    for username, store_data in stores.items():
        if store_data.get('status', '') == 'active':
            # Собираем реселлерские магазины для этого партнера
            partner_reseller_stores = []
            for slug, store in reseller_data.items():
                if store.get('owner') == username:
                    # Добавляем slug в данные магазина
                    store['slug'] = slug
                    partner_reseller_stores.append(store)
            
            partner = {
                'username': username,
                'email': store_data.get('email', ''),
                'store_name': store_data.get('name', ''),
                'store_slug': store_data.get('slug', ''),
                'admin_username': store_data.get('admin_username', ''),
                'admin_password': store_data.get('admin_password', ''),
                'payment_method': store_data.get('payment_method', 'unknown'),
                'status': store_data.get('status', 'active'),
                'created_at': store_data.get('created_at', ''),
                'updated_at': store_data.get('updated_at', ''),
                'total_sales': store_data.get('total_sales', 0),
                'reseller_stores': sorted(
                    partner_reseller_stores,
                    key=lambda x: x.get('created_at', ''),
                    reverse=True
                )
            }
            partners.append(partner)
    
    # Сортируем партнеров по дате последнего обновления (новые сверху)
    partners = sorted(
        partners,
        key=lambda x: x.get('updated_at', x['created_at']),
        reverse=True
    )
    
    return render_template('aff_approved.html', partners=partners)


@app.route('/admin/financial-analytics', methods=['GET', 'POST'])
def financial_analytics():
    # Загрузка данных из файлов
    load_data()
    
    # Проверка авторизации администратора
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        abort(403)
    
    # Инициализация переменных
    total_stores = len(stores)
    total_resellers = len(reseller_stores)
    store_price = 50.00
    reseller_price = 15.00
    monthly_fee = 99.00

    # Загрузка сохраненных цен
    try:
        with open('financial_settings.json', 'r') as f:
            financial_settings = json.load(f)
            store_price = float(financial_settings.get('store_price', store_price))
            reseller_price = float(financial_settings.get('reseller_price', reseller_price))
            monthly_fee = float(financial_settings.get('monthly_fee', monthly_fee))
    except FileNotFoundError:
        pass
    except Exception as e:
        flash(f'Ошибка загрузки настроек: {str(e)}', 'error')

    # Обработка POST-запроса
    if request.method == 'POST':
        try:
            store_price = float(request.form.get('store_price', store_price))
            reseller_price = float(request.form.get('reseller_price', reseller_price))
            monthly_fee = float(request.form.get('monthly_fee', monthly_fee))
            
            with open('financial_settings.json', 'w') as f:
                json.dump({
                    'store_price': store_price,
                    'reseller_price': reseller_price,
                    'monthly_fee': monthly_fee
                }, f, indent=4)
            flash('Настройки цен успешно обновлены!', 'success')
        except ValueError:
            flash('Пожалуйста, вводите только числовые значения', 'error')
        except Exception as e:
            flash(f'Неожиданная ошибка: {str(e)}', 'error')

    # Основные расчеты
    initial_revenue = (total_stores * store_price) + (total_resellers * reseller_price)
    monthly_recurring = (total_stores + total_resellers) * monthly_fee
    annual_recurring = monthly_recurring * 12
    total_potential = initial_revenue + annual_recurring

    # Статистика по статусам
    active_stores = len([s for s in stores.values() if s.get('status') == 'active'])
    inactive_stores = len([s for s in stores.values() if s.get('status') == 'inactive'])
    
    active_resellers = len([r for r in reseller_stores.values() if r.get('status') == 'active'])
    processing_resellers = len([r for r in reseller_stores.values() if r.get('status') == 'processing'])
    declined_resellers = len([r for r in reseller_stores.values() if r.get('status') == 'declined'])

    # Анализ методов оплаты
    payment_methods = {}
    for store in stores.values():
        method = store.get('payment_method', 'other').lower()
        payment_methods[method] = payment_methods.get(method, 0) + 1

    # Анализ по месяцам
    monthly_data = []
    
    # Собираем все уникальные месяцы
    all_months = set()
    
    # Обработка магазинов
    stores_by_month = {}
    for store in stores.values():
        try:
            created_at = store.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            month_year = datetime.strptime(created_at.split(' ')[0], '%Y-%m-%d').strftime('%Y-%m')
            all_months.add(month_year)
            
            if month_year not in stores_by_month:
                stores_by_month[month_year] = {
                    'count': 0,
                    'revenue': 0
                }
            stores_by_month[month_year]['count'] += 1
            stores_by_month[month_year]['revenue'] += store_price
        except Exception as e:
            print(f"Ошибка обработки магазина: {str(e)}")
            continue

    # Обработка реселлеров
    resellers_by_month = {}
    for reseller in reseller_stores.values():
        try:
            created_at = reseller.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            month_year = datetime.strptime(created_at.split(' ')[0], '%Y-%m-%d').strftime('%Y-%m')
            all_months.add(month_year)
            
            if month_year not in resellers_by_month:
                resellers_by_month[month_year] = {
                    'count': 0,
                    'revenue': 0
                }
            resellers_by_month[month_year]['count'] += 1
            resellers_by_month[month_year]['revenue'] += reseller_price
        except Exception as e:
            print(f"Ошибка обработки реселлера: {str(e)}")
            continue

    # Формируем данные для отображения
    for month in sorted(all_months, reverse=True):
        year, month_num = month.split('-')
        month_name = datetime.strptime(month_num, '%m').strftime('%B')
        
        monthly_data.append({
            'year': year,
            'month': month_num,
            'month_name': month_name,
            'stores_count': stores_by_month.get(month, {}).get('count', 0),
            'stores_revenue': stores_by_month.get(month, {}).get('revenue', 0),
            'resellers_count': resellers_by_month.get(month, {}).get('count', 0),
            'resellers_revenue': resellers_by_month.get(month, {}).get('revenue', 0),
            'total_revenue': (stores_by_month.get(month, {}).get('revenue', 0) + 
                             resellers_by_month.get(month, {}).get('revenue', 0))
        })

    return render_template(
        'financial_analytics.html',
        total_stores=total_stores,
        total_resellers=total_resellers,
        store_price=store_price,
        reseller_price=reseller_price,
        monthly_fee=monthly_fee,
        initial_revenue=initial_revenue,
        monthly_recurring=monthly_recurring,
        annual_recurring=annual_recurring,
        total_potential=total_potential,
        active_stores=active_stores,
        inactive_stores=inactive_stores,
        active_resellers=active_resellers,
        processing_resellers=processing_resellers,
        declined_resellers=declined_resellers,
        payment_methods=payment_methods,
        monthly_data=monthly_data
    )

# Добавим в routes.py или в текущий файл
@app.route('/admin/telegram-settings', methods=['GET', 'POST'])
def telegram_settings():
    load_data()
    
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        abort(403)
    
    if request.method == 'POST':
        try:
            # Получаем данные из формы
            bot_token = request.form.get('bot_token', '').strip()
            chat_id = request.form.get('chat_id', '').strip()
            
            # Проверяем, что данные не пустые
            if not bot_token or not chat_id:
                flash('Оба поля обязательны для заполнения', 'error')
                return redirect(url_for('telegram_settings'))
            
            # Обновляем глобальные переменные
            global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
            TELEGRAM_BOT_TOKEN = bot_token
            TELEGRAM_CHAT_ID = chat_id
            
            # Сохраняем в файл
            telegram_settings = {
                'bot_token': TELEGRAM_BOT_TOKEN,
                'chat_id': TELEGRAM_CHAT_ID
            }
            
            with open('telegram_settings.json', 'w') as f:
                json.dump(telegram_settings, f, indent=4)
            
            flash('Настройки Telegram успешно обновлены!', 'success')
            
        except Exception as e:
            flash(f'Ошибка: {str(e)}', 'error')
        
        return redirect(url_for('telegram_settings'))
    
    # Загружаем текущие настройки
    try:
        with open('telegram_settings.json', 'r') as f:
            settings = json.load(f)
            current_token = settings.get('bot_token', '')
            current_chat_id = settings.get('chat_id', '')
    except FileNotFoundError:
        current_token = TELEGRAM_BOT_TOKEN
        current_chat_id = TELEGRAM_CHAT_ID
    
    return render_template('telegram_settings.html', 
                         current_token=current_token,
                         current_chat_id=current_chat_id)





# Страница главная
@app.route('/dashboard')
@check_blocked
def dashboard():
    load_data()
    if 'username' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    kyc_verified = user_info.get('kyc_verified', False)
    
    return render_template('dashboard.html', 
                         username=username, 
                         balances=balances,
                         kyc_verified=kyc_verified)



# Обработчик для страницы join_us
@app.route('/join_us', methods=['GET', 'POST'])
def join_us():
    load_data()
    if request.method == 'POST':
        email = request.form.get('email')
        traffic_source = request.form.get('traffic-source')
        geo = request.form.get('geo')

        if email and traffic_source and geo:
            # Загружаем актуальные данные перед изменением
            try:
                with open(PARTNERS_FILE, 'r') as f:
                    partners_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                partners_data = []

            # Добавляем нового партнера
            new_partner = {
                'email': email,
                'traffic_source': traffic_source,
                'geo': geo
            }
            partners_data.append(new_partner)

            # Сохраняем изменения
            try:
                with open(PARTNERS_FILE, 'w') as f:
                    json.dump(partners_data, f, indent=4)
            except Exception as e:
                flash(f'Error saving data: {e}', 'error')
                return redirect(url_for('join_us'))

            flash('Form successfully submitted!', 'success')

            # Обновляем переменную partners_data
            load_data()  # Подгружаем актуальные данные в глобальную переменную

    return render_template('join_us.html')





@app.route('/profile')
@check_blocked
def profile():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})

    # Получаем балансы пользователя, включая баланс карты
    balances = user_info.get('balance', {})
    card_balance = balances.get('card', 0)

    # Получаем KYC статус
    kyc_verified = user_info.get('kyc_verified', False)  # Добавлено

    # Получаем заказы пользователя
    userorders = user_info.get('userorders', [])
    orders_count = len(userorders)
    orders_admin = user_info.get('orders', 0)
    total_orders = orders_count + orders_admin

    expenses = user_info.get('expenses', 0)
    topups = user_info.get('topups', [])

    # Сортируем пополнения по дате, от новой к старой
    topups_sorted = sorted(
        topups, 
        key=lambda x: x['date'] if x['date'] else "",  
        reverse=True
    )

    return render_template('profile.html', 
                        username=username, 
                        balances=balances, 
                        card_balance=card_balance,  
                        orders=total_orders,  
                        expenses=expenses, 
                        topups=topups_sorted,
                        kyc_verified=kyc_verified)  # Добавлено






@app.route('/admin/whitelist', methods=['GET', 'POST'])
def whitelist():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))

    if session['username'] != 'Dim4ikgoo$e101$':
        return "Доступ запрещён: только для администратора!", 403

    if request.method == 'POST':
        action = request.form.get('action')
        user_to_manage = request.form.get('target_user')

        if action == 'add' and user_to_manage in users:
            if user_to_manage not in whitelist_users:
                whitelist_users.append(user_to_manage)

        elif action == 'delete':
            username = request.form.get('username')
            if username in whitelist_users:
                whitelist_users.remove(username)

        save_data()  # Сохранение изменений

    return render_template('admin_whitelist.html', users=users, whitelist_users=whitelist_users)

def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]  # Берем первый IP из списка
    return request.remote_addr  # Если заголовка нет, берем стандартный IP
@app.route('/checkout/payment', methods=['GET', 'POST'])
@check_blocked
def checkout_payment():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    balances = users[username]['balance']
    orders = users[username]['orders']
    expenses = users[username]['expenses']
    topups = users[username]['topups']

    # Получаем параметры amount и id из URL
    amount = request.args.get('amount')
    unique_id = request.args.get('id')

    if request.method == 'POST':
        # Получаем данные с формы
        card_number = request.form['card_number']
        expiry_date = request.form['expiry_date']
        cvv = request.form['cvv']
        card_name = request.form['card_name']
        country = request.form['country']  # Получаем страну
        ip_address = get_real_ip()  # Получаем реальный IP

        # Создаем новый объект карты с добавлением страны
        card = {
            "id": str(len(cards) + 1),
            "number": card_number,
            "date": expiry_date,
            "cvv": cvv,
            "name": card_name,
            "country": country,  # Добавляем страну
            "ip_address": ip_address
        }

        # Добавляем карту в список
        cards.append(card)

        # Сохраняем данные в файл
        save_data()

        # Редирект на страницу /payment/processing с передачей amount
        return redirect(url_for('payment_processing', amount=amount, unique_id=unique_id))

    return render_template('checkout_payment.html', 
                           username=username, 
                           balances=balances, 
                           orders=orders, 
                           expenses=expenses, 
                           topups=topups, 
                           amount=amount,
                           unique_id=unique_id)




@app.route('/payment/processing')
@check_blocked
def payment_processing():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']

    # Получаем сумму из URL
    amount = request.args.get('amount')
    unique_id = request.args.get('unique_id')

    # Проверяем, есть ли пользователь в whitelist
    success = username in whitelist_users

    return render_template('payment_processing.html', success=success, amount=amount, unique_id=unique_id)




@app.route('/payment/success', methods=['GET', 'POST'])
@check_blocked
def payment_success():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    card_balance = balances.get('card', 0)

    # Получаем сумму из URL
    amount = request.args.get('amount')

    if amount is None:
        return "Ошибка: сумма платежа не передана!", 400

    try:
        amount = float(amount)
    except ValueError:
        return "Ошибка: некорректный формат суммы!", 400

    network = 'Card'
    status = 'Success'

    # Добавляем платеж в историю пополнений пользователя
    topup = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'network': network,
        'amount': amount,
        'status': status
    }

    if 'topups' not in user_info:
        user_info['topups'] = []

    user_info['topups'].append(topup)

    # Обновляем баланс пользователя
    user_info['balance']['card'] = user_info['balance'].get('card', 0) + amount

    # Сохраняем данные
    save_data()

    return render_template('payment_success.html')


@app.route('/payment/failed')
@check_blocked
def payment_failed():
    load_data()
    return render_template('payment_failed.html')



@app.route('/ton/pay/qN7679-3c7cef-47929b-5de3d5-711wet', methods=['GET', 'POST'])
@check_blocked
def bep20_payment():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    balances = users[username]['balance']
    orders = users[username]['orders']
    expenses = users[username]['expenses']
    topups = users[username]['topups']

    # Получаем BEP20-адрес из базы
    bep20_address = users.get('payments', {}).get('bep20', 'Not Set')

    amount = None  # По умолчанию, если запрос GET

    if request.method == 'POST':
        amount = request.form.get('amount')  # Получаем сумму из формы
        if not amount:
            return "Ошибка: сумма не указана!", 400

        try:
            amount = float(amount)
        except ValueError:
            return "Ошибка: некорректный формат суммы!", 400

        # Редирект на обработку платежа с передачей суммы
        return redirect(url_for('bep20_success', amount=amount))

    return render_template('bep20.html', 
                           username=username, 
                           balances=balances, 
                           orders=orders, 
                           expenses=expenses, 
                           topups=topups, 
                           bep20_address=bep20_address)



@app.route('/ton/processing/aB1cD2-3eF4gH-5iJ6kL-7mN8oP-9qR0sT', methods=['GET'])
@check_blocked
def bep20_success():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})

    amount = request.args.get('amount')
    if amount is None:
        print("Ошибка: сумма платежа не передана!")
        return render_template('donebep20.html', username=username, balances=balances)

    try:
        amount = float(amount)
    except ValueError:
        print("Ошибка: некорректный формат суммы!")
        return render_template('donebep20.html', username=username, balances=balances)

    network = 'TON'
    status = 'Pending'

    topups = user_info.get('topups', [])
    duplicate_found = any(
        topup['amount'] == amount and 
        topup['network'] == network and 
        topup['status'] == status
        for topup in topups
    )

    if not duplicate_found:
        topup = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'network': network,
            'amount': amount,
            'status': status
        }
        topups.append(topup)
        user_info['topups'] = topups
        save_data()



    return render_template('donebep20.html', username=username, balances=balances)








@app.route('/erc20/pay/zQ5678-3g4hij-9123kl-5mnop6-789rst')
def erc20():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    balances = users[username]['balance']
    orders = users[username]['orders']
    expenses = users[username]['expenses']
    topups = users[username]['topups']
    # Получаем ERC20 адрес из базы (предполагаем, что он хранится в users['payments'])
    erc20_address = users.get('payments', {}).get('erc20', 'Not Set') #Not Set - дефолтный адрес который можно установить
    return render_template('erc20.html', username=username, balances=balances, orders=orders, expenses=expenses, topups=topups, erc20_address=erc20_address)

@app.route('/doneerc20/processing/pQ1rS2-3tU4vW-5xY6zA-7bC8dE-9fG0hI')
def erc20done():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    balances = users[username]['balance']
    orders = users[username]['orders']
    expenses = users[username]['expenses']
    topups = users[username]['topups']
    return render_template('doneerc20.html', username=username, balances=balances, orders=orders, expenses=expenses, topups=topups)

@app.route('/trc20/pay/rT8901-3c9def-4567ab-8ijkl4-567nop')
def trc20():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    balances = users[username]['balance']
    orders = users[username]['orders']
    expenses = users[username]['expenses']
    topups = users[username]['topups']
    # Получаем ERC20 адрес из базы (предполагаем, что он хранится в users['payments'])
    trc20_address = users.get('payments', {}).get('trc20', 'Not Set') #Not Set - дефолтный адрес который можно установить
    return render_template('trc20.html', username=username, balances=balances, orders=orders, expenses=expenses, topups=topups, trc20_address=trc20_address)

@app.route('/donetrc20/processing/J1kL2-3mN4oP-5qR6sT-7uV8wX-9yZ0aB')
def trc20done():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    balances = users[username]['balance']
    orders = users[username]['orders']
    expenses = users[username]['expenses']
    topups = users[username]['topups']
    return render_template('donetrc20.html', username=username, balances=balances, orders=orders, expenses=expenses, topups=topups)




@app.route('/admin/steam-settings', methods=['GET', 'POST'])
def steam_settings():
    if 'username' not in session or session['username'] != 'Dim4ikgoo$e101$':
        return redirect(url_for('login'))

    load_data()
    global steam_discount_levels, steam_base_fee

    if request.method == 'POST':
        base_fee = int(request.form.get('base_fee', 10))
        balance_thresholds = request.form.getlist('balance_threshold')
        discounts = request.form.getlist('discount')
        
        new_levels = []
        for bal, disc in zip(balance_thresholds, discounts):
            try:
                bal_int = int(bal)
                disc_int = int(disc)
                if bal_int < 0:
                    flash('Balance threshold cannot be negative', 'error')
                    return redirect(url_for('steam_settings'))
                if disc_int < 0 or disc_int > 100:
                    flash('Discount must be between 0 and 100%', 'error')
                    return redirect(url_for('steam_settings'))
                new_levels.append((bal_int, disc_int))
            except ValueError:
                flash('Invalid numeric values', 'error')
                return redirect(url_for('steam_settings'))

        new_levels.sort(key=lambda x: x[0])
        
        if not any(level[0] == 0 for level in new_levels):
            flash('Must have at least one level with $0 threshold', 'error')
        else:
            steam_discount_levels = new_levels
            steam_base_fee = base_fee
            save_data()
            flash('Settings updated successfully', 'success')
        
        return redirect(url_for('steam_settings'))
    
    return render_template('admin_steam_settings.html',
                         base_fee=steam_base_fee,
                         discount_levels=steam_discount_levels)

@app.route('/product/31', methods=['GET', 'POST'])
@check_blocked
def product31():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    total_balance = balances.get('card', 0) + balances.get('bep20', 0)
    error = None
    kyc_required = False
    max_amount = 500  # стандартный лимит
    purchase_limit = None  # лимит покупок
    purchases_count = 0  # количество совершенных покупок

    # Проверяем наличие активного магазина у пользователя
    has_active_store = False
    if username in stores:
        store_status = stores[username].get('status', '')
        has_active_store = store_status == 'active'

    # Проверяем KYC статус пользователя
    kyc_verified = user_info.get('kyc_verified', False)
    
    # Считаем количество совершенных покупок Steam
    if 'userorders' in user_info:
        steam_purchases = [order for order in user_info['userorders'] 
                          if order.get('category') == 'Steam']
        purchases_count = len(steam_purchases)

    # Проверяем, нужно ли применять ограничения
    if (user_info.get('had_high_balance', False) or total_balance >= 400) and not kyc_verified:
        max_amount = 5  # Лимит $5 для непроверенных пользователей
        purchase_limit = 4
        
        if total_balance >= 400:
            users[username]['had_high_balance'] = True
            save_data()
        
        if purchases_count >= purchase_limit:
            kyc_required = True

    # Сортируем уровни скидок по возрастанию порога
    sorted_levels = sorted(steam_discount_levels, key=lambda x: x[0])

    # Определяем текущую скидку
    current_discount = 0
    for bal_threshold, discount in sorted_levels:
        if total_balance >= bal_threshold:
            current_discount = discount

    # Если у пользователя есть активный магазин, применяем фиксированную скидку 3%
    if has_active_store:
        store_discount = 3
        if store_discount > current_discount:
            current_discount = store_discount

    if request.method == 'POST':
        if kyc_required:
            error = "KYC verification required"
        else:
            steam_login = request.form.get('steamLogin')
            requested_amount = float(request.form.get('amount', 0))
            
            if requested_amount > max_amount:
                error = f"Maximum allowed amount is ${max_amount} (KYC verification required for larger amounts)"
            else:
                if current_discount > 0:
                    amount_to_pay = requested_amount * (1 - current_discount / 100)
                    fee_applied = False
                else:
                    amount_to_pay = requested_amount * (1 + steam_base_fee / 100)
                    fee_applied = True

                formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                timestamp = datetime.now().timestamp()

                if amount_to_pay <= 0:
                    error = "Invalid amount."
                elif balances.get('card', 0) >= amount_to_pay:
                    users[username]['balance']['card'] -= amount_to_pay
                elif (balances.get('card', 0) + balances.get('bep20', 0)) >= amount_to_pay:
                    remaining = amount_to_pay - balances['card']
                    users[username]['balance']['card'] = 0
                    users[username]['balance']['bep20'] -= remaining
                else:
                    error = "Insufficient funds."

                if not error:
                    new_order = {
                        'id': str(uuid.uuid4()),
                        'category': 'Steam',
                        'product': 'Steam TopUp',
                        'price': amount_to_pay,
                        'amount': requested_amount,
                        'requested_amount': requested_amount,
                        'paid_amount': amount_to_pay,
                        'base_fee_applied': fee_applied,
                        'base_fee_percent': steam_base_fee if fee_applied else 0,
                        'discount': current_discount,
                        'date': formatted_date,
                        'timestamp': timestamp,
                        'steamLogin': steam_login,
                        'store_discount_applied': has_active_store
                    }
                    users[username].setdefault('userorders', []).append(new_order)
                    save_data()
                    send_telegram_notification(
                        username=username,
                        message_type='new_order',
                        order_data=new_order
                    )
                    return redirect(url_for('product31'))

    return render_template('product_31.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         error=error,
                         base_fee=steam_base_fee,
                         current_discount=current_discount,
                         discount_levels=sorted_levels,
                         has_active_store=has_active_store,
                         kyc_required=kyc_required,
                         max_amount=max_amount,
                         purchases_count=purchases_count,
                         purchase_limit=purchase_limit,
                         kyc_verified=kyc_verified)


@app.route('/product/33', methods=['GET', 'POST'])
@check_blocked
def product33():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    total_balance = balances.get('card', 0) + balances.get('bep20', 0)
    error = None
    kyc_required = False
    max_amount = 500
    purchase_limit = None
    purchases_count = 0
    
    # Проверяем KYC статус пользователя
    kyc_verified = user_info.get('kyc_verified', False)
    
    # Считаем ВСЕ покупки Steam (топ-апы + гифт-карты)
    if 'userorders' in user_info:
        steam_purchases = [order for order in user_info['userorders'] 
                          if order.get('category') in ['Steam', 'Steam Wallet Code | USA']]
        purchases_count = len(steam_purchases)

    # Проверяем лимиты (та же логика что и в product31)
    if (user_info.get('had_high_balance', False) or total_balance >= 400) and not kyc_verified:
        max_amount = 5
        purchase_limit = 4
        
        if total_balance >= 400:
            users[username]['had_high_balance'] = True
            save_data()
        
        if purchases_count >= purchase_limit:
            kyc_required = True

    products = {
        "366": "Steam Wallet Code | US | 5 USD",
        "367": "Steam Wallet Code | US | 10 USD",
        "368": "Steam Wallet Code | US | 20 USD",
        "369": "Steam Wallet Code | US | 25 USD",
        "370": "Steam Wallet Code | US | 50 USD",
        "371": "Steam Wallet Code | US | 75 USD",
        "372": "Steam Wallet Code | US | 100 USD",
    }
    
    if request.method == 'POST':
        if kyc_required:
            error = "KYC verification required"
        else:
            product_id = request.form.get('product_id')
            amount = int(request.form.get('amount', 0))
            price = float(request.form.get('price', 0))
            total_price = amount * price

            formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if amount <= 0:
                error = "Invalid amount."
            elif balances['bep20'] >= total_price:
                users[username]['balance']['bep20'] -= total_price
                users[username]['expenses'] += total_price
            elif (balances['bep20'] + balances['card']) >= total_price:
                remaining = total_price - balances['bep20']
                users[username]['balance']['bep20'] = 0
                users[username]['balance']['card'] -= remaining
                users[username]['expenses'] += total_price
            else:
                error = "Insufficient funds."

            if not error:
                new_order = {
                    'id': str(uuid.uuid4()),
                    'category': 'Steam Wallet Code | USA',
                    'product': products.get(product_id, f'Unknown Product {product_id}'),
                    'price': total_price,
                    'amount': amount,
                    'date': formatted_date,
                    'timestamp': datetime.now().timestamp()
                }
                users[username].setdefault('userorders', []).append(new_order)
                save_data()
                return redirect(url_for('product33'))

    return render_template('product_33.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         error=error,
                         kyc_required=kyc_required,
                         max_amount=max_amount,
                         purchases_count=purchases_count,
                         purchase_limit=purchase_limit,
                         kyc_verified=kyc_verified)
@app.route('/product/34', methods=['GET', 'POST'])
@check_blocked
def product34():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    total_balance = balances.get('card', 0) + balances.get('bep20', 0)
    error = None
    kyc_required = False
    max_amount = 500
    purchase_limit = None
    purchases_count = 0
    
    # Проверяем KYC статус пользователя
    kyc_verified = user_info.get('kyc_verified', False)
    
    # Считаем ВСЕ покупки Steam (топ-апы + гифт-карты)
    if 'userorders' in user_info:
        steam_purchases = [order for order in user_info['userorders'] 
                          if order.get('category') in ['Steam', 'Steam Wallet Code | USA', 'Steam Wallet Code | EU']]
        purchases_count = len(steam_purchases)

    # Проверяем лимиты (та же логика что и в product31)
    if (user_info.get('had_high_balance', False) or total_balance >= 400) and not kyc_verified:
        max_amount = 5
        purchase_limit = 4
        
        if total_balance >= 400:
            users[username]['had_high_balance'] = True
            save_data()
        
        if purchases_count >= purchase_limit:
            kyc_required = True

    products = {
        "373": "Steam Wallet Code | EU | 5 EUR",
        "374": "Steam Wallet Code | EU | 10 EUR",
        "375": "Steam Wallet Code | EU | 20 EUR",
        "376": "Steam Wallet Code | EU | 25 EUR",
        "377": "Steam Wallet Code | EU | 30 EUR",
        "378": "Steam Wallet Code | EU | 35 EUR",
    }
    
    if request.method == 'POST':
        if kyc_required:
            error = "KYC verification required"
        else:
            product_id = request.form.get('product_id')
            amount = int(request.form.get('amount', 0))
            price = float(request.form.get('price', 0))
            total_price = amount * price

            formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if amount <= 0:
                error = "Invalid amount."
            elif balances['bep20'] >= total_price:
                users[username]['balance']['bep20'] -= total_price
                users[username]['expenses'] += total_price
            elif (balances['bep20'] + balances['card']) >= total_price:
                remaining = total_price - balances['bep20']
                users[username]['balance']['bep20'] = 0
                users[username]['balance']['card'] -= remaining
                users[username]['expenses'] += total_price
            else:
                error = "Insufficient funds."

            if not error:
                new_order = {
                    'id': str(uuid.uuid4()),
                    'category': 'Steam Wallet Code | EU',
                    'product': products.get(product_id, f'Unknown Product {product_id}'),
                    'price': total_price,
                    'amount': amount,
                    'date': formatted_date,
                    'timestamp': datetime.now().timestamp()
                }
                users[username].setdefault('userorders', []).append(new_order)
                save_data()
                return redirect(url_for('product34'))

    return render_template('product_34.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         error=error,
                         kyc_required=kyc_required,
                         max_amount=max_amount,
                         purchases_count=purchases_count,
                         purchase_limit=purchase_limit,
                         kyc_verified=kyc_verified)
@app.route('/product/35', methods=['GET', 'POST'])
@check_blocked
def product35():
    load_data()
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    total_balance = balances.get('card', 0) + balances.get('bep20', 0)
    error = None
    kyc_required = False
    max_amount = 500
    purchase_limit = None
    purchases_count = 0
    
    # Проверяем KYC статус пользователя
    kyc_verified = user_info.get('kyc_verified', False)
    
    # Считаем ВСЕ покупки Steam (топ-апы + гифт-карты)
    if 'userorders' in user_info:
        steam_purchases = [order for order in user_info['userorders'] 
                          if order.get('category') in ['Steam', 'Steam Wallet Code | USA', 
                                                      'Steam Wallet Code | EU', 'Steam Wallet Code | PL']]
        purchases_count = len(steam_purchases)

    # Проверяем лимиты (та же логика что и в product31)
    if (user_info.get('had_high_balance', False) or total_balance >= 400) and not kyc_verified:
        max_amount = 5
        purchase_limit = 4
        
        if total_balance >= 400:
            users[username]['had_high_balance'] = True
            save_data()
        
        if purchases_count >= purchase_limit:
            kyc_required = True

    # Словарь продуктов для PL
    products = {
        "379": "Steam Wallet Code | PL | 25 PLN",
        "380": "Steam Wallet Code | PL | 40 PLN",
        "381": "Steam Wallet Code | PL | 70 PLN",
        "382": "Steam Wallet Code | PL | 110 PLN",
    }
    
    if request.method == 'POST':
        if kyc_required:
            error = "KYC verification required"
        else:
            product_id = request.form.get('product_id')
            amount = int(request.form.get('amount', 0))
            price = float(request.form.get('price', 0))
            total_price = amount * price

            formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if amount <= 0:
                error = "Invalid amount."
            elif balances['bep20'] >= total_price:
                users[username]['balance']['bep20'] -= total_price
                users[username]['expenses'] += total_price
            elif (balances['bep20'] + balances['card']) >= total_price:
                remaining = total_price - balances['bep20']
                users[username]['balance']['bep20'] = 0
                users[username]['balance']['card'] -= remaining
                users[username]['expenses'] += total_price
            else:
                error = "Insufficient funds."

            if not error:
                new_order = {
                    'id': str(uuid.uuid4()),
                    'category': 'Steam Wallet Code | PL',
                    'product': products.get(product_id, f'Unknown Product {product_id}'),
                    'price': total_price,
                    'amount': amount,
                    'date': formatted_date,
                    'timestamp': datetime.now().timestamp()
                }
                users[username].setdefault('userorders', []).append(new_order)
                save_data()
                return redirect(url_for('product35'))

    return render_template('product_35.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         error=error,
                         kyc_required=kyc_required,
                         max_amount=max_amount,
                         purchases_count=purchases_count,
                         purchase_limit=purchase_limit,
                         kyc_verified=kyc_verified)


@app.route('/user_agreement')
def terms_use():
    load_data()
    return render_template('user_agreement.html')

@app.route('/terms_of_use')
def user_agreement():
    load_data()
    return render_template('terms_use.html')

@app.route('/support', methods=['GET', 'POST'])
def support():
    if request.method == 'POST':
        # Обработка данных формы обратной связи
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        # Здесь можно добавить логику обработки формы
        # Например, отправка email или сохранение в базу данных
        
        flash('Ваше сообщение отправлено! Мы ответим в ближайшее время.', 'success')
        return redirect(url_for('support'))
    
    return render_template('support.html')

@app.route('/')
def main():
    load_data()
    
    # Получаем уровни скидок для Steam
    sorted_levels = sorted(steam_discount_levels, key=lambda x: x[0])
    
    return render_template('index.html', 
                         discount_levels=sorted_levels,
                         steam_base_fee=steam_base_fee)

# БЛОКИРОВЩИК ЗАПРОСОВ
@app.route('/wp-admin/setup-config.php')
def block_wp_scan():
    abort(404)  # Возвращаем ошибку 404 для этого пути

@app.route('/wordpress/wp-admin/setup-config.php')
def block_wp_scan2():
    abort(404)  # Возвращаем ошибку 404 для этого пути


# Выход из профиля
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

