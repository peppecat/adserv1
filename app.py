
import json
import os
import uuid
import sys
import requests
import threading
sys.stdout.reconfigure(encoding='utf-8')
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort, send_file
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
app.secret_key = 'supersecretkey'

# ====================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
DEFAULT_STEAM_SETTINGS = {
    'base_fee': 10,
    'discount_levels': [
        (0, 0),
        (50, 2),
        (500, 20),
        (1000, 25),
        (2000, 30),
        (4000, 35)
    ],
    'individual_discounts': {}
}

global users, products, cards, steam_discount_levels, steam_base_fee, individual_discounts, stores
global achievements, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

users = {}
products = {}
cards = {}
stores = {}
achievements = {}
steam_discount_levels = DEFAULT_STEAM_SETTINGS['discount_levels']
steam_base_fee = DEFAULT_STEAM_SETTINGS['base_fee']
individual_discounts = DEFAULT_STEAM_SETTINGS['individual_discounts']
TELEGRAM_BOT_TOKEN = '7726856877:AAFIslzTXmB5FCw2zDHuPswiybUaCGxiNSw'
TELEGRAM_CHAT_ID = '-1003175110976'

USERS_FILE = 'users.json'
PAYMENTS_FILE = 'payments.json'
PRODUCTS_FILE = 'products.json'
STEAM_DISCOUNTS_FILE = 'steam_discounts.json'
STORES_FILE = 'stores.json'

# ====================== AUTOMATIC DATA LOADING
@app.before_request
def load_data_before_request():
    """Автоматически загружает данные перед каждым запросом"""
    load_data()

# ====================== ОСНОВНЫЕ ФУНКЦИИ ДАННЫХ
def sync_user_balance(username):
    """Синхронизирует баланс пользователя с завершенными пополнениями и вычитает расходы на заказы"""
    global users
    
    if username not in users:
        return
    
    user_data = users[username]
    
    # Инициализируем балансы
    if 'balance' not in user_data:
        user_data['balance'] = {'card': 0, 'ton': 0, 'bep20': 0}
    
    # Начинаем с нуля для каждого типа баланса
    current_balance = {'card': 0, 'ton': 0, 'bep20': 0}
    
    # Добавляем завершенные пополнения по соответствующим методам
    if 'topups' in user_data:
        for topup in user_data['topups']:
            if (topup.get('status') == 'completed' and 
                topup.get('payment_confirmed') == True and
                topup.get('method') in current_balance):
                # Каждое пополнение добавляется только к своему методу
                current_balance[topup['method']] += topup['amount']
    
    # Вычитаем расходы на заказы, распределяя их по методам оплаты
    total_expenses = 0
    if 'userorders' in user_data:
        for order in user_data['userorders']:
            total_expenses += order.get('price', 0)
    
    # Вычитаем расходы из балансов в правильной последовательности
    remaining_expenses = total_expenses
    
    # ВАЖНОЕ ИСПРАВЛЕНИЕ: Сохраняем оригинальные балансы до списаний
    original_balances = current_balance.copy()
    
    # Сначала списываем с bep20 (если есть заказы, оплаченные этим методом)
    if current_balance['bep20'] > 0 and remaining_expenses > 0:
        if current_balance['bep20'] >= remaining_expenses:
            current_balance['bep20'] -= remaining_expenses
            remaining_expenses = 0
        else:
            remaining_expenses -= current_balance['bep20']
            current_balance['bep20'] = 0
    
    # Затем с card
    if remaining_expenses > 0 and current_balance['card'] > 0:
        if current_balance['card'] >= remaining_expenses:
            current_balance['card'] -= remaining_expenses
            remaining_expenses = 0
        else:
            remaining_expenses -= current_balance['card']
            current_balance['card'] = 0
    
    # Затем с ton
    if remaining_expenses > 0 and current_balance['ton'] > 0:
        if current_balance['ton'] >= remaining_expenses:
            current_balance['ton'] -= remaining_expenses
            remaining_expenses = 0
        else:
            current_balance['ton'] = max(0, current_balance['ton'] - remaining_expenses)
    
    # Обновляем баланс пользователя
    user_data['balance'] = current_balance
    user_data['expenses'] = total_expenses


def load_data():
    """Загружает все данные из файлов"""
    global users, products, cards, steam_discount_levels, steam_base_fee, individual_discounts, stores
    global achievements, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    try:
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
            
        # СИНХРОНИЗАЦИЯ БАЛАНСА С ЗАВЕРШЕННЫМИ ПОПОЛНЕНИЯМИ И ЗАКАЗАМИ
        for username, user_data in users.items():
            sync_user_balance(username)
                
    except FileNotFoundError:
        users = {}

    try:
        with open(STEAM_DISCOUNTS_FILE, 'r') as f:
            steam_settings = json.load(f)
            if isinstance(steam_settings, list):
                steam_settings = {
                    'base_fee': 10,
                    'discount_levels': steam_settings,
                    'individual_discounts': {}
                }
            steam_discount_levels = steam_settings.get('discount_levels', [])
            steam_base_fee = steam_settings.get('base_fee', 10)
            individual_discounts = steam_settings.get('individual_discounts', {})
    except FileNotFoundError:
        steam_settings = DEFAULT_STEAM_SETTINGS
        steam_discount_levels = steam_settings['discount_levels']
        steam_base_fee = steam_settings['base_fee']
        individual_discounts = steam_settings['individual_discounts']

    try:
        with open(STORES_FILE, 'r') as f:
            stores = json.load(f)
    except FileNotFoundError:
        stores = {}

    try:
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except FileNotFoundError:
        products = {}

    try:
        with open('telegram_settings.json', 'r') as f:
            telegram_settings = json.load(f)
        TELEGRAM_BOT_TOKEN = telegram_settings.get('bot_token', '')
        TELEGRAM_CHAT_ID = telegram_settings.get('chat_id', '')
    except FileNotFoundError:
        TELEGRAM_BOT_TOKEN = '7726856877:AAFIslzTXmB5FCw2zDHuPswiybUaCGxiNSw'
        TELEGRAM_CHAT_ID = '-1003175110976'

def save_data():
    """Сохраняет все данные в файлы"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)
    with open(STEAM_DISCOUNTS_FILE, 'w') as f:
        json.dump({
            'base_fee': steam_base_fee,
            'discount_levels': steam_discount_levels,
            'individual_discounts': individual_discounts
        }, f, indent=4)
    with open(STORES_FILE, 'w') as f:
        json.dump(stores, f, indent=4)


# ====================== Telegram API
# Принудительно устанавливаем значения для группы
TELEGRAM_BOT_TOKEN = '7726856877:AAFIslzTXmB5FCw2zDHuPswiybUaCGxiNSw'
TELEGRAM_CHAT_ID = '-1003175110976'  # ID вашей группы

# Сохраняем оригинальные значения, чтобы их нельзя было переопределить
ORIGINAL_TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN
ORIGINAL_TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID

def send_telegram_notification_async(username, message_type, amount=None, payment_method=None, order_data=None):
    """Асинхронная отправка уведомления в Telegram в отдельном потоке"""
    thread = threading.Thread(
        target=send_telegram_notification,
        args=(username, message_type, amount, payment_method, order_data)
    )
    thread.daemon = True  # Поток завершится при завершении основного процесса
    thread.start()

def send_telegram_notification(username, message_type, amount=None, payment_method=None, order_data=None):
    """Синхронная функция отправки уведомления в Telegram"""
    # Используем оригинальные значения, а не глобальные переменные
    bot_token = ORIGINAL_TELEGRAM_BOT_TOKEN
    chat_id = ORIGINAL_TELEGRAM_CHAT_ID
    
    if not bot_token or not chat_id:
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
                    f"🚩 Логин: {order_data.get('steamLogin', 'N/A') if order_data else 'N/A'}"
    }
    
    message = messages.get(message_type)
    if not message:
        return None

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")
        return None




# ====================== STEAM API
# Глобальная переменная для хранения курсов и времени последнего обновления
exchange_rates_cache = {
    'last_updated': None,
    'rates': None
}

# ====================== EXCHANGE RATES API
@app.route('/api/exchange_rates')
def get_exchange_rates():
    """API endpoint для получения курсов валют с кешированием"""
    global exchange_rates_cache
    
    # Проверяем, нужно ли обновлять курсы (не чаще чем раз в 10 минут)
    current_time = datetime.now().timestamp()
    if (exchange_rates_cache['last_updated'] and 
        current_time - exchange_rates_cache['last_updated'] < 600):  # 10 минут
        print("Используем кешированные курсы валют")
        return jsonify(exchange_rates_cache['rates'])
    
    print("Обновляем курсы валют...")
    currencies = [
        {'code': 'rub', 'id': 5, 'symbol': '₽'},
        {'code': 'uah', 'id': 18, 'symbol': '₴'},
        {'code': 'kzt', 'id': 37, 'symbol': '₸'}
    ]
    
    api_key = '62e5589d9e984151936b3625afa32774'
    rates = {}
    
    for currency in currencies:
        try:
            url = f"https://desslyhub.com/api/v1/exchange_rate/steam/{currency['id']}"
            response = requests.get(url, headers={'apikey': api_key})
            
            if response.status_code == 200:
                data = response.json()
                # Пробуем разные форматы ответа
                rate = None
                if data and 'rate' in data:
                    rate = data['rate']
                elif data and 'data' in data and 'rate' in data['data']:
                    rate = data['data']['rate']
                elif data and 'exchange_rate' in data:
                    rate = data['exchange_rate']
                elif isinstance(data, (int, float)):
                    rate = data
                
                if rate is not None:
                    rates[currency['code']] = {
                        'rate': float(rate),
                        'symbol': currency['symbol'],
                        'timestamp': current_time,
                        'fake': False
                    }
                    print(f"Курс {currency['code']}: {rate}")
                else:
                    # Используем фиктивные данные если не удалось получить реальные
                    fake_rates = {'rub': 90.5, 'uah': 38.2, 'kzt': 450.3}
                    rates[currency['code']] = {
                        'rate': fake_rates[currency['code']],
                        'symbol': currency['symbol'],
                        'timestamp': current_time,
                        'fake': True
                    }
                    print(f"Используем фиктивный курс {currency['code']}: {fake_rates[currency['code']]}")
            else:
                # Используем фиктивные данные при ошибке
                fake_rates = {'rub': 90.5, 'uah': 38.2, 'kzt': 450.3}
                rates[currency['code']] = {
                    'rate': fake_rates[currency['code']],
                    'symbol': currency['symbol'],
                    'timestamp': current_time,
                    'fake': True
                }
                print(f"Ошибка HTTP {response.status_code}, используем фиктивный курс {currency['code']}")
                
        except Exception as e:
            print(f"Ошибка при получении курса {currency['code']}: {e}")
            # Используем фиктивные данные при исключении
            fake_rates = {'rub': 90.5, 'uah': 38.2, 'kzt': 450.3}
            rates[currency['code']] = {
                'rate': fake_rates[currency['code']],
                'symbol': currency['symbol'],
                'timestamp': current_time,
                'fake': True
            }
            print(f"Исключение, используем фиктивный курс {currency['code']}")
    
    # Обновляем кеш
    exchange_rates_cache = {
        'last_updated': current_time,
        'rates': rates
    }
    
    return jsonify(rates)


# ====================== STEAM TOPUP API
@app.route('/api/steam_topup', methods=['POST'])
def steam_topup():
    """API endpoint для пополнения Steam кошелька"""
    
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    
    # Получаем данные из запроса
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    steam_login = data.get('steamLogin')
    amount = data.get('amount')
    
    if not steam_login or not amount:
        return jsonify({'error': 'Missing steamLogin or amount'}), 400
    
    try:
        requested_amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid amount format'}), 400
    
    # Проверяем максимальную сумму
    max_amount = 500
    if requested_amount > max_amount:
        return jsonify({'error': f'Maximum allowed amount is ${max_amount}'}), 400
    
    # РАСЧЕТ СКИДКИ И КОМИССИИ
    total_balance = balances.get('card', 0) + balances.get('bep20', 0) + balances.get('ton', 0)
    
    # Определяем текущую скидку на основе баланса
    current_discount = 0
    for bal_threshold, discount in steam_discount_levels:
        if total_balance >= bal_threshold:
            current_discount = discount
    
    # Проверяем индивидуальную скидку для пользователя
    individual_discount = individual_discounts.get(username)
    if individual_discount is not None:
        current_discount = individual_discount
        discount_source = 'individual'
    else:
        discount_source = 'balance'
    
    # РАССЧИТЫВАЕМ ФИНАЛЬНУЮ СУММУ ДЛЯ СПИСАНИЯ
    # Сначала применяем скидку (уменьшаем сумму)
    amount_after_discount = requested_amount * (1 - current_discount / 100)
    
    # Затем применяем комиссию (увеличиваем сумму)
    amount_to_pay = amount_after_discount * (1 + steam_base_fee / 100)
    
    # Проверяем баланс пользователя
    if total_balance < amount_to_pay:
        return jsonify({'error': 'Insufficient funds'}), 400
    
    try:
        # Отправляем запрос к внешнему API
        api_key = '62e5589d9e984151936b3625afa32774'
        payload = {
            "amount": requested_amount,
            "username": steam_login
        }
        headers = {
            "apikey": api_key,
            "content-type": "application/json"
        }
        
        print(f"Отправляем запрос к внешнему API: {payload}")
        response = requests.post(
            'https://desslyhub.com/api/v1/service/steamtopup/topup',
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Статус ответа от API: {response.status_code}")
        print(f"Ответ от API: {response.text}")
        
        if response.status_code == 200:
            api_data = response.json()
            
            if 'error_code' in api_data:
                # Обработка ошибки от API
                error_message = f"API error: {api_data.get('error_code')}"
                return jsonify({'error': error_message}), 400
            
            # Успешный запрос - списываем средства и создаем заказ
            transaction_id = api_data.get('transaction_id')
            transaction_status = api_data.get('status', 'pending')
            
            # Списываем средства с баланса пользователя
            remaining = amount_to_pay
            
            # Сначала списываем с card баланса
            if balances.get('card', 0) >= remaining:
                users[username]['balance']['card'] -= remaining
                remaining = 0
            else:
                card_balance = balances.get('card', 0)
                if card_balance > 0:
                    users[username]['balance']['card'] = 0
                    remaining -= card_balance
            
            # Затем списываем с bep20 баланса
            if remaining > 0 and balances.get('bep20', 0) >= remaining:
                users[username]['balance']['bep20'] -= remaining
                remaining = 0
            elif remaining > 0:
                bep20_balance = balances.get('bep20', 0)
                if bep20_balance > 0:
                    users[username]['balance']['bep20'] = 0
                    remaining -= bep20_balance
            
            # Затем списываем с ton баланса
            if remaining > 0 and balances.get('ton', 0) >= remaining:
                users[username]['balance']['ton'] -= remaining
                remaining = 0
            
            # ВАЖНОЕ ИСПРАВЛЕНИЕ: Добавляем сумму к общим расходам пользователя
            if username in users:
                if 'expenses' not in users[username]:
                    users[username]['expenses'] = 0
                users[username]['expenses'] += amount_to_pay
            
            # Создаем заказ
            formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            timestamp = datetime.now().timestamp()
            
            new_order = {
                'id': str(uuid.uuid4()),
                'category': 'Steam',
                'product': 'Steam TopUp',
                'price': amount_to_pay,
                'amount': requested_amount,
                'requested_amount': requested_amount,
                'paid_amount': amount_to_pay,
                'base_fee_applied': True,
                'base_fee_percent': steam_base_fee,
                'discount': current_discount,
                'discount_source': discount_source,
                'date': formatted_date,
                'timestamp': timestamp,
                'steamLogin': steam_login,
                'individual_discount_applied': individual_discount is not None,
                'transaction_id': transaction_id,
                'transaction_status': transaction_status,
                'external_service_used': True
            }
            
            users[username].setdefault('userorders', []).append(new_order)
            # СИНХРОНИЗИРУЕМ БАЛАНС ПОСЛЕ СОЗДАНИЯ ЗАКАЗА
            sync_user_balance(username)
            save_data()
            
            # АСИНХРОННАЯ отправка уведомления в Telegram
            send_telegram_notification_async(
                username=username,
                message_type='new_order',
                order_data=new_order
            )
            
            return jsonify({
                'success': True,
                'transaction_id': transaction_id,
                'status': transaction_status,
                'amount_paid': amount_to_pay,
                'amount_received': requested_amount,
                'discount_applied': current_discount,
                'base_fee_applied': steam_base_fee
            })
        else:
            return jsonify({'error': f'API returned status {response.status_code}'}), 400
            
    except requests.exceptions.Timeout:
        return jsonify({'error': 'API request timeout'}), 408
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Cannot connect to API'}), 503
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'API request failed: {str(e)}'}), 500
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({'error': 'Internal server error'}), 500











# ====================== 1. INDEX.HTML
@app.route('/')
def main():
    
    
    # Получаем уровни скидок для Steam
    sorted_levels = sorted(steam_discount_levels, key=lambda x: x[0])
    
    return render_template('1.index.html', 
                         discount_levels=sorted_levels,
                         steam_base_fee=steam_base_fee)



# ====================== 2. USER_AGREEMENT.HTML
@app.route('/user_agreement')
def user_agreement():
    
    return render_template('2.user_agreement.html')



# ====================== 3. PRIVACY_POLICY.HTML
@app.route('/privacy_policy')
def privacy_policy():
    
    return render_template('3.privacy_policy.html')



# ====================== 4. SUPPORT.HTML
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
    
    return render_template('4.support.html')



# ====================== 5. LOGIN.HTML
@app.route('/login', methods=['GET', 'POST'])
def login():
    
    # Если пользователь уже авторизован, перенаправляем на dashboard
    if 'username' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username]['password'] == password:
            # Проверяем, не заблокирован ли пользователь
            if users[username].get('status') == 'banned':
                flash('Ваш аккаунт заблокирован. Причина: ' + users[username].get('ban_reason', 'Не указана'), 'error')
                return redirect(url_for('login'))
            
            session['username'] = username
            # Обновляем время последнего входа
            users[username]['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            save_data()
            return redirect(url_for('dashboard'))
        flash("Incorrect username or password!", 'error')
        return redirect(url_for('login'))
    return render_template('5.login.html')



# ====================== 6. REGISTER.HTML
@app.route('/register', methods=['GET', 'POST'])
def register():
    
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
        
        users[username] = {
            'password': password,
            'balance': {'card': 0, 'ton': 0, 'bep20': 0},
            'orders': 0,
            'expenses': 0,
            'userorders': [],
            'topups': [],
            'status': 'active',  # Добавляем статус по умолчанию
            'registration_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        save_data()
        
        # АСИНХРОННАЯ отправка уведомления в Telegram
        send_telegram_notification_async(username, 'registration')
        
        return redirect(url_for('login'))
    return render_template('6.register.html')



# ====================== 7. DASHBOARD.HTML
@app.route('/dashboard')
def dashboard():
   
    if 'username' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    
    # Рассчитываем общий баланс (все типы балансов)
    total_balance = balances.get('card', 0) + balances.get('bep20', 0) + balances.get('ton', 0)
    
    return render_template('7.dashboard.html', 
                         username=username, 
                         balances=balances,
                         total_balance=total_balance)



# ====================== 8. PRODUCT_1.HTML
@app.route('/product/1', methods=['GET', 'POST'])
def product1():
    
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    
    # ИСПРАВЛЕНИЕ: Учитываем ВСЕ типы балансов для total_balance
    total_balance = balances.get('card', 0) + balances.get('bep20', 0) + balances.get('ton', 0)
    
    error = None
    max_amount = 500
    purchase_limit = None
    purchases_count = 0

    # Считаем количество совершенных покупок Steam
    if 'userorders' in user_info:
        steam_purchases = [order for order in user_info['userorders'] 
                          if order.get('category') == 'Steam']
        purchases_count = len(steam_purchases)

    # Сортируем уровни скидок по возрастанию порога
    sorted_levels = sorted(steam_discount_levels, key=lambda x: x[0])

    # Определяем текущую скидку на основе баланса
    current_discount_from_balance = 0
    for bal_threshold, discount in sorted_levels:
        if total_balance >= bal_threshold:
            current_discount_from_balance = discount

    # Проверяем индивидуальную скидку для пользователя
    individual_discount = individual_discounts.get(username)
    
    # Выбираем максимальную скидку: индивидуальную или на основе баланса
    if individual_discount is not None:
        current_discount = individual_discount
        discount_source = 'individual'
    else:
        current_discount = current_discount_from_balance
        discount_source = 'balance'

    # УБРАЛИ обработку POST запроса - теперь это делает отдельный endpoint

    return render_template('8.product_1.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         error=error,
                         steam_base_fee=steam_base_fee,  # ДОБАВЛЕНО: передаем комиссию в шаблон
                         current_discount=current_discount,
                         discount_levels=sorted_levels,
                         max_amount=max_amount,
                         purchases_count=purchases_count,
                         purchase_limit=purchase_limit,
                         individual_discount=individual_discount)


# ====================== 9. PRODUCT_2.HTML
@app.route('/product/2', methods=['GET', 'POST'])
def product2():
    
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    
    # Учитываем ВСЕ типы балансов для total_balance
    total_balance = balances.get('card', 0) + balances.get('bep20', 0) + balances.get('ton', 0)
    
    error = None
    
    # Получаем товары из products.json
    category_products = {}
    if 'categories' in products and 'steam_wallet_us' in products['categories']:
        category_products = products['categories']['steam_wallet_us']['products']
    
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        amount_str = request.form.get('amount', '0')
        
        try:
            amount = int(amount_str)
        except ValueError:
            error = "Invalid amount format"
            amount = 0
        
        if not product_id:
            error = "Product ID is required"
        elif amount <= 0:
            error = "Amount must be greater than 0"
        else:
            # Получаем цену из products.json
            product_price = None
            if product_id in category_products:
                product_price = category_products[product_id]['price']
                product_name = category_products[product_id]['name']
                in_stock = category_products[product_id].get('in_stock', True)
            else:
                error = "Product not found"
                product_price = 0

            if not in_stock:
                error = "Product is out of stock"
            else:
                total_price = amount * product_price
                formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                timestamp = datetime.now().timestamp()

                if total_price <= 0:
                    error = "Invalid total price."
                # Проверяем ВСЕ доступные балансы
                elif total_balance >= total_price:
                    # Сначала списываем с card баланса
                    if balances.get('card', 0) >= total_price:
                        users[username]['balance']['card'] -= total_price
                    else:
                        # Если card баланса недостаточно, используем другие балансы
                        remaining = total_price
                        
                        # Списываем с card баланса всё что есть
                        card_balance = balances.get('card', 0)
                        if card_balance > 0:
                            if card_balance >= remaining:
                                users[username]['balance']['card'] -= remaining
                                remaining = 0
                            else:
                                users[username]['balance']['card'] = 0
                                remaining -= card_balance
                        
                        # Затем списываем с bep20 баланса
                        if remaining > 0 and balances.get('bep20', 0) >= remaining:
                            users[username]['balance']['bep20'] -= remaining
                            remaining = 0
                        elif remaining > 0:
                            bep20_balance = balances.get('bep20', 0)
                            if bep20_balance > 0:
                                users[username]['balance']['bep20'] = 0
                                remaining -= bep20_balance
                        
                        # Затем списываем с ton баланса
                        if remaining > 0 and balances.get('ton', 0) >= remaining:
                            users[username]['balance']['ton'] -= remaining
                            remaining = 0
                        elif remaining > 0:
                            # Если всё равно недостаточно - ошибка
                            error = "Insufficient funds across all balance types"
                else:
                    error = "Insufficient funds."

                if not error:
                    users[username]['expenses'] += total_price
                    new_order = {
                        'id': str(uuid.uuid4()),
                        'category': 'Steam Wallet Code | USA',
                        'product': product_name,
                        'price': total_price,
                        'amount': amount,
                        'date': formatted_date,
                        'timestamp': timestamp
                    }
                    users[username].setdefault('userorders', []).append(new_order)
                    # СИНХРОНИЗИРУЕМ БАЛАНС ПОСЛЕ СОЗДАНИЯ ЗАКАЗА
                    sync_user_balance(username)
                    save_data()
                    
                    # АСИНХРОННАЯ отправка уведомления в Telegram
                    send_telegram_notification_async(
                        username=username,
                        message_type='new_order',
                        order_data=new_order
                    )
                    return redirect(url_for('product2'))

    return render_template('9.product_2.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         error=error,
                         products=category_products)




# ====================== 10. PRODUCT_3.HTML
@app.route('/product/3', methods=['GET', 'POST'])
def product3():
   
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    
    # Учитываем ВСЕ типы балансов для total_balance
    total_balance = balances.get('card', 0) + balances.get('bep20', 0) + balances.get('ton', 0)
    
    error = None
    
    # Получаем товары из products.json для EU региона
    category_products = {}
    if 'categories' in products and 'steam_wallet_eu' in products['categories']:
        category_products = products['categories']['steam_wallet_eu']['products']
    
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        amount_str = request.form.get('amount', '0')
        
        try:
            amount = int(amount_str)
        except ValueError:
            error = "Invalid amount format"
            amount = 0
        
        if not product_id:
            error = "Product ID is required"
        elif amount <= 0:
            error = "Amount must be greater than 0"
        else:
            # Получаем цену из products.json
            product_price = None
            if product_id in category_products:
                product_price = category_products[product_id]['price']
                product_name = category_products[product_id]['name']
                in_stock = category_products[product_id].get('in_stock', True)
            else:
                error = "Product not found"
                product_price = 0

            if not in_stock:
                error = "Product is out of stock"
            else:
                total_price = amount * product_price
                formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                timestamp = datetime.now().timestamp()

                if total_price <= 0:
                    error = "Invalid total price."
                # Проверяем ВСЕ доступные балансы
                elif total_balance >= total_price:
                    # Сначала списываем с card баланса
                    if balances.get('card', 0) >= total_price:
                        users[username]['balance']['card'] -= total_price
                    else:
                        # Если card баланса недостаточно, используем другие балансы
                        remaining = total_price
                        
                        # Списываем с card баланса всё что есть
                        card_balance = balances.get('card', 0)
                        if card_balance > 0:
                            if card_balance >= remaining:
                                users[username]['balance']['card'] -= remaining
                                remaining = 0
                            else:
                                users[username]['balance']['card'] = 0
                                remaining -= card_balance
                        
                        # Затем списываем с bep20 баланса
                        if remaining > 0 and balances.get('bep20', 0) >= remaining:
                            users[username]['balance']['bep20'] -= remaining
                            remaining = 0
                        elif remaining > 0:
                            bep20_balance = balances.get('bep20', 0)
                            if bep20_balance > 0:
                                users[username]['balance']['bep20'] = 0
                                remaining -= bep20_balance
                        
                        # Затем списываем с ton баланса
                        if remaining > 0 and balances.get('ton', 0) >= remaining:
                            users[username]['balance']['ton'] -= remaining
                            remaining = 0
                        elif remaining > 0:
                            # Если всё равно недостаточно - ошибка
                            error = "Insufficient funds across all balance types"
                else:
                    error = "Insufficient funds."

                if not error:
                    users[username]['expenses'] += total_price
                    new_order = {
                        'id': str(uuid.uuid4()),
                        'category': 'Steam Wallet Code | EU',
                        'product': product_name,
                        'price': total_price,
                        'amount': amount,
                        'date': formatted_date,
                        'timestamp': timestamp
                    }
                    users[username].setdefault('userorders', []).append(new_order)
                    # СИНХРОНИЗИРУЕМ БАЛАНС ПОСЛЕ СОЗДАНИЯ ЗАКАЗА
                    sync_user_balance(username)
                    save_data()
                    
                    # АСИНХРОННАЯ отправка уведомления в Telegram
                    send_telegram_notification_async(
                        username=username,
                        message_type='new_order',
                        order_data=new_order
                    )
                    return redirect(url_for('product3'))

    return render_template('10.product_3.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         error=error,
                         products=category_products)


# ====================== 11. ORDERS.HTML
@app.route('/orders')
def orders():
    
    if 'username' not in session:
        flash('Please login to view your orders', 'error')
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    total_balance = balances.get('card', 0) + balances.get('bep20', 0) + balances.get('ton', 0)
    
    # Get user orders, sorted by timestamp (newest first)
    user_orders = user_info.get('userorders', [])
    user_orders_sorted = sorted(user_orders, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    total_orders = len(user_orders_sorted)
    
    return render_template('11.orders.html',
                         username=username,
                         total_balance=total_balance,
                         user_orders=user_orders_sorted,
                         total_orders=total_orders)



# ====================== 12. ACCOUNT.HTML 
@app.route('/account', methods=['GET', 'POST'])
def account():
   
    if 'username' not in session:
        flash('Please login to access your account', 'error')
        return redirect(url_for('login'))
    
    username = session['username']
    user_info = users.get(username, {})
    balances = user_info.get('balance', {})
    
    # Рассчитываем общий баланс (все типы балансов)
    total_balance = balances.get('card', 0) + balances.get('bep20', 0) + balances.get('ton', 0)
    
    # Получаем общее количество заказов
    total_orders = len(user_info.get('userorders', []))
    
    # Получаем общие расходы
    total_expenses = user_info.get('expenses', 0)
    
    # Получаем историю пополнений
    topup_history = user_info.get('topups', [])
    # Сортируем по дате (новые сверху)
    topup_history_sorted = sorted(topup_history, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    return render_template('12.account.html',
                         username=username,
                         balances=balances,
                         total_balance=total_balance,
                         total_orders=total_orders,
                         total_expenses=total_expenses,
                         topup_history=topup_history_sorted)


# ====================== 13. PAYMENT PAGES.HTML 
@app.route('/payment/bep20', methods=['GET', 'POST'])
def payment_bep20():
    """Страница оплаты через BEP20"""
    
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    
    # Получаем данные из сессии
    payment_data = session.get('payment_data')
    if not payment_data or payment_data.get('method') != 'bep20':
        flash('Неверные данные оплаты', 'error')
        return redirect(url_for('account'))
    
    amount = payment_data.get('amount')
    
    # Загружаем адрес кошелька BEP20 из файла
    try:
        with open('payment_wallets.json', 'r') as f:
            wallets = json.load(f)
        wallet_address = wallets.get('bep20', '')
    except FileNotFoundError:
        wallet_address = "0x742d35Cc6634C0532925a3b8D4B5b875aD0B0000"  # fallback адрес
    
    if not wallet_address:
        flash('Адрес кошелька BEP20 не настроен', 'error')
        return redirect(url_for('account'))
    
    if request.method == 'POST':
        # Пользователь нажал "Оплачено"
        # Создаем запись о пополнении
        formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        timestamp = datetime.now().timestamp()
        
        new_topup = {
            'id': str(uuid.uuid4()),
            'amount': amount,
            'method': 'bep20',
            'date': formatted_date,
            'timestamp': timestamp,
            'status': 'pending',
            'wallet_address': wallet_address,
            'payment_confirmed': False
        }
        
        # Добавляем в историю пополнений пользователя
        users[username].setdefault('topups', []).append(new_topup)
        save_data()
        
        # Очищаем данные сессии
        session.pop('payment_data', None)
        
        # АСИНХРОННАЯ отправка уведомления в Telegram
        send_telegram_notification_async(
            username=username,
            message_type='payment',
            amount=amount,
            payment_method='BEP20 (USDT)'
        )
        
        return render_template('13.payment_waiting.html', 
                             username=username,
                             amount=amount,
                             method='BEP20 (USDT)',
                             wallet_address=wallet_address)
    
    # Устанавливаем время истечения (10 минут)
    expiry_time = datetime.now().timestamp() + 600  # 10 минут
    
    return render_template('13.payment_bep20.html',
                         username=username,
                         amount=amount,
                         wallet_address=wallet_address,
                         expiry_time=expiry_time)


@app.route('/payment/ton', methods=['GET', 'POST'])
def payment_ton():
    """Страница оплаты через TON"""
    
    if 'username' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    
    # Получаем данные из сессии
    payment_data = session.get('payment_data')
    if not payment_data or payment_data.get('method') != 'ton':
        flash('Неверные данные оплаты', 'error')
        return redirect(url_for('account'))
    
    amount = payment_data.get('amount')
    
    # Загружаем адрес кошелька TON из файла
    try:
        with open('payment_wallets.json', 'r') as f:
            wallets = json.load(f)
        wallet_address = wallets.get('ton', '')
    except FileNotFoundError:
        wallet_address = "UQCD39VS5jcptHL8vMjEXrzGaRcCVYto7HUn4bpAOg8xqB2N"  # fallback адрес
    
    if not wallet_address:
        flash('Адрес кошелька TON не настроен', 'error')
        return redirect(url_for('account'))
    
    if request.method == 'POST':
        # Пользователь нажал "Оплачено"
        # Создаем запись о пополнении
        formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        timestamp = datetime.now().timestamp()
        
        new_topup = {
            'id': str(uuid.uuid4()),
            'amount': amount,
            'method': 'ton',
            'date': formatted_date,
            'timestamp': timestamp,
            'status': 'pending',
            'wallet_address': wallet_address,
            'payment_confirmed': False
        }
        
        # Добавляем в историю пополнений пользователя
        users[username].setdefault('topups', []).append(new_topup)
        save_data()
        
        # Очищаем данные сессии
        session.pop('payment_data', None)
        
        # АСИНХРОННАЯ отправка уведомления в Telegram
        send_telegram_notification_async(
            username=username,
            message_type='payment',
            amount=amount,
            payment_method='TON (USDT)'
        )
        
        return render_template('13.payment_waiting.html', 
                             username=username,
                             amount=amount,
                             method='TON (USDT)',
                             wallet_address=wallet_address)
    
    # Устанавливаем время истечения (10 минут)
    expiry_time = datetime.now().timestamp() + 600  # 10 минут
    
    return render_template('13.payment_ton.html',
                         username=username,
                         amount=amount,
                         wallet_address=wallet_address,
                         expiry_time=expiry_time)


@app.route('/payment/create', methods=['POST'])
def create_payment():
    """Создание платежа и перенаправление на страницу оплаты"""
    
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    amount = data.get('amount')
    method = data.get('method')
    
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid amount format'}), 400
    
    if amount < 1 or amount > 10000:
        return jsonify({'error': 'Amount must be between $1 and $10,000'}), 400
    
    if method not in ['bep20', 'ton']:
        return jsonify({'error': 'Invalid payment method'}), 400
    
    # Сохраняем данные оплаты в сессии
    session['payment_data'] = {
        'amount': amount,
        'method': method,
        'timestamp': datetime.now().timestamp()
    }
    
    # Перенаправляем на соответствующую страницу оплаты
    if method == 'bep20':
        return jsonify({'redirect': url_for('payment_bep20')})
    else:  # ton
        return jsonify({'redirect': url_for('payment_ton')})




# ====================== АДМИН ФУНКЦИИ

@app.route('/admin')
def admin_dashboard():
    """Главная страница админ-панели"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    # Статистика для дашборда
    total_users = len(users) - 1  # исключаем админа
    active_users = len([u for u in users.values() if u.get('status', 'active') == 'active' and u != users.get('admin')])
    banned_users = total_users - active_users
    
    # Общая статистика по заказам и балансам
    total_orders = sum(len(u.get('userorders', [])) for u in users.values() if u != users.get('admin'))
    total_balance = sum(
        u.get('balance', {}).get('card', 0) + 
        u.get('balance', {}).get('ton', 0) + 
        u.get('balance', {}).get('bep20', 0) 
        for u in users.values() if u != users.get('admin')
    )
    total_expenses = sum(u.get('expenses', 0) for u in users.values() if u != users.get('admin'))
    
    # Последние 5 заказов
    all_orders = []
    for username, user_data in users.items():
        if username == 'admin':
            continue
        for order in user_data.get('userorders', []):
            order_with_user = order.copy()
            order_with_user['username'] = username
            all_orders.append(order_with_user)
    
    latest_orders = sorted(all_orders, key=lambda x: x.get('timestamp', 0), reverse=True)[:5]
    
    return render_template('15.admin_dashboard.html',
                         total_users=total_users,
                         active_users=active_users,
                         banned_users=banned_users,
                         total_orders=total_orders,
                         total_balance=total_balance,
                         total_expenses=total_expenses,
                         latest_orders=latest_orders)


# ====================== 1. УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
@app.route('/admin/users')
def admin_users():
    """Админская страница для управления пользователями"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    # Собираем информацию о всех пользователях
    users_list = []
    for username, user_info in users.items():
        if username == 'admin':  # Пропускаем самого админа
            continue
            
        user_data = {
            'username': username,
            'status': user_info.get('status', 'active'),
            'ban_reason': user_info.get('ban_reason', ''),
            'balance': user_info.get('balance', {'card': 0, 'ton': 0, 'bep20': 0}),
            'orders_count': len(user_info.get('userorders', [])),
            'expenses': user_info.get('expenses', 0),
            'registration_date': user_info.get('registration_date', 'N/A'),
            'last_login': user_info.get('last_login', 'N/A')
        }
        users_list.append(user_data)
    
    # Сортируем по дате регистрации (новые сверху)
    # Преобразуем даты в объекты datetime для корректной сортировки
    def get_sort_key(user):
        reg_date = user['registration_date']
        if reg_date == 'N/A':
            return datetime.min  # Ставим пользователей без даты в конец
        try:
            return datetime.strptime(reg_date, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return datetime.min
    
    users_list_sorted = sorted(users_list, key=get_sort_key, reverse=True)
    
    return render_template('16.admin_users.html', users=users_list_sorted)


@app.route('/admin/user/<username>/update', methods=['POST'])
def admin_update_user(username):
    """Обновление статуса пользователя"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    status = data.get('status', 'active')
    ban_reason = data.get('ban_reason', '')
    
    # Обновляем статус пользователя
    users[username]['status'] = status
    if status == 'banned':
        users[username]['ban_reason'] = ban_reason
        users[username]['banned_by'] = session['username']
        users[username]['banned_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    else:
        # Если разблокировали, очищаем информацию о блокировке
        users[username].pop('ban_reason', None)
        users[username].pop('banned_by', None)
        users[username].pop('banned_date', None)
        users[username]['unbanned_by'] = session['username']
        users[username]['unbanned_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'Статус пользователя {username} обновлен'
    })


@app.route('/admin/user/<username>/delete', methods=['POST'])
def admin_delete_user(username):
    """Полное удаление пользователя"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    if username == 'admin':
        return jsonify({'error': 'Cannot delete admin user'}), 400
    
    # Полностью удаляем пользователя
    deleted_user = users.pop(username)
    save_data()
    
    # АСИНХРОННАЯ отправка уведомления в Telegram
    send_telegram_notification_async(
        username=session['username'],
        message_type='user_deleted',
        amount=None,
        payment_method=None,
        order_data={'deleted_user': username}
    )
    
    return jsonify({
        'success': True,
        'message': f'Пользователь {username} полностью удален'
    })


@app.route('/admin/user/<username>/balance/update', methods=['POST'])
def admin_update_user_balance(username):
    """Обновление баланса пользователя"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    method = data.get('method')
    action = data.get('action')  # add, subtract, set
    amount = data.get('amount')
    
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid amount format'}), 400
    
    if method not in ['card', 'ton', 'bep20']:
        return jsonify({'error': 'Invalid payment method'}), 400
    
    if action not in ['add', 'subtract', 'set']:
        return jsonify({'error': 'Invalid action'}), 400
    
    # Обновляем баланс
    if action == 'add':
        users[username]['balance'][method] += amount
    elif action == 'subtract':
        users[username]['balance'][method] = max(0, users[username]['balance'][method] - amount)
    elif action == 'set':
        users[username]['balance'][method] = max(0, amount)
    
    # Синхронизируем баланс
    sync_user_balance(username)
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'Баланс пользователя {username} обновлен',
        'new_balance': users[username]['balance'][method]
    })


# ====================== 2. УПРАВЛЕНИЕ СРЕДСТВАМИ
@app.route('/admin/finances')
def admin_finances():
    """Управление средствами пользователей"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    # Получаем параметр фильтрации
    filter_user = request.args.get('user', '')
    
    # Собираем все пополнения
    all_topups = []
    for username, user_info in users.items():
        if username == 'admin':
            continue
        user_topups = user_info.get('topups', [])
        for topup in user_topups:
            topup_with_user = topup.copy()
            topup_with_user['username'] = username
            # Применяем фильтр по пользователю
            if not filter_user or username == filter_user:
                all_topups.append(topup_with_user)
    
    # Сортируем по дате (новые сверху)
    all_topups_sorted = sorted(all_topups, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    # Получаем список пользователей для выпадающего списка
    user_list = [username for username in users.keys() if username != 'admin']
    
    return render_template('17.admin_finances.html', 
                         topups=all_topups_sorted,
                         users=user_list,
                         filter_user=filter_user)  # Добавляем текущий фильтр


@app.route('/admin/topup/add', methods=['POST'])
def admin_add_topup():
    """Добавление пополнения вручную"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    username = data.get('username')
    amount = data.get('amount')
    method = data.get('method')
    status = data.get('status', 'completed')
    
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid amount format'}), 400
    
    if method not in ['card', 'ton', 'bep20']:
        return jsonify({'error': 'Invalid payment method'}), 400
    
    # Создаем запись о пополнении
    formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    timestamp = datetime.now().timestamp()
    
    new_topup = {
        'id': str(uuid.uuid4()),
        'amount': amount,
        'method': method,
        'date': formatted_date,
        'timestamp': timestamp,
        'status': status,
        'payment_confirmed': status == 'completed',
        'added_by': session['username'],
        'wallet_address': 'Административное пополнение'
    }
    
    # Добавляем в историю пополнений пользователя
    users[username].setdefault('topups', []).append(new_topup)
    
    # Если статус completed, пополняем баланс
    if status == 'completed':
        if method not in users[username]['balance']:
            users[username]['balance'][method] = 0
        users[username]['balance'][method] += amount
    
    # Синхронизируем баланс
    sync_user_balance(username)
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'Пополнение для {username} добавлено'
    })


@app.route('/admin/topup/<username>/<topup_id>/update_status', methods=['POST'])
def admin_update_topup_status(username, topup_id):
    """Обновление статуса пополнения"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users or 'topups' not in users[username]:
        return jsonify({'error': 'User or topup not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    new_status = data.get('status')
    if new_status not in ['completed', 'pending', 'failed']:
        return jsonify({'error': 'Invalid status'}), 400
    
    # Находим пополнение
    topup_found = None
    for topup in users[username]['topups']:
        if topup['id'] == topup_id:
            topup_found = topup
            break
    
    if not topup_found:
        return jsonify({'error': 'Topup not found'}), 404
    
    old_status = topup_found['status']
    method = topup_found['method']
    amount = topup_found['amount']
    
    # Обновляем статус
    topup_found['status'] = new_status
    topup_found['payment_confirmed'] = new_status == 'completed'
    
    # Обрабатываем изменения баланса
    if old_status == 'completed' and new_status != 'completed':
        # Убираем сумму из баланса
        users[username]['balance'][method] -= amount
    elif old_status != 'completed' and new_status == 'completed':
        # Добавляем сумму в баланс
        if method not in users[username]['balance']:
            users[username]['balance'][method] = 0
        users[username]['balance'][method] += amount
    
    # Синхронизируем баланс
    sync_user_balance(username)
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'Статус обновлен на "{new_status}"'
    })


@app.route('/admin/topup/<username>/<topup_id>/delete', methods=['POST'])
def admin_delete_topup(username, topup_id):
    """Удаление пополнения"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users or 'topups' not in users[username]:
        return jsonify({'error': 'User or topup not found'}), 404
    
    # Находим и удаляем пополнение
    original_topups = users[username]['topups']
    users[username]['topups'] = [topup for topup in original_topups if topup['id'] != topup_id]
    
    # Если удалили, синхронизируем баланс
    if len(users[username]['topups']) < len(original_topups):
        sync_user_balance(username)
        save_data()
        return jsonify({'success': True, 'message': 'Пополнение удалено'})
    else:
        return jsonify({'error': 'Topup not found'}), 404


@app.route('/admin/topup/<username>/clear', methods=['POST'])
def admin_clear_user_topups(username):
    """Очистка всей истории пополнений пользователя"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    # Очищаем историю пополнений
    users[username]['topups'] = []
    sync_user_balance(username)
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'История пополнений пользователя {username} очищена'
    })


# ====================== 3. УПРАВЛЕНИЕ ЗАКАЗАМИ
@app.route('/admin/orders')
def admin_orders():
    """Управление заказами пользователей"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    # Получаем параметры фильтрации
    filter_type = request.args.get('filter', 'recent')
    username_filter = request.args.get('username', '')
    
    # Собираем все заказы
    all_orders = []
    for username, user_info in users.items():
        if username == 'admin':
            continue
        if username_filter and username != username_filter:
            continue
            
        user_orders = user_info.get('userorders', [])
        for order in user_orders:
            order_with_user = order.copy()
            order_with_user['username'] = username
            all_orders.append(order_with_user)
    
    # Сортируем и фильтруем
    all_orders_sorted = sorted(all_orders, key=lambda x: x.get('timestamp', 0), reverse=True)
    
    if filter_type == 'recent':
        orders_to_show = all_orders_sorted[:15]
    else:
        orders_to_show = all_orders_sorted
    
    return render_template('18.admin_orders.html', 
                         orders=orders_to_show,
                         filter_type=filter_type,
                         username_filter=username_filter,
                         all_usernames=[u for u in users.keys() if u != 'admin'])


@app.route('/admin/order/<username>/<order_id>/update', methods=['POST'])
def admin_update_order(username, order_id):
    """Обновление заказа"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users or 'userorders' not in users[username]:
        return jsonify({'error': 'User or order not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Находим заказ
    order_index = None
    for i, order in enumerate(users[username]['userorders']):
        if order['id'] == order_id:
            order_index = i
            break
    
    if order_index is None:
        return jsonify({'error': 'Order not found'}), 404
    
    # Обновляем поля
    if 'date' in data:
        users[username]['userorders'][order_index]['date'] = data['date']
    if 'status' in data:
        users[username]['userorders'][order_index]['status'] = data['status']
    if 'transaction_status' in data:
        users[username]['userorders'][order_index]['transaction_status'] = data['transaction_status']
    
    save_data()
    
    return jsonify({
        'success': True,
        'message': 'Заказ обновлен'
    })


@app.route('/admin/order/<username>/<order_id>/delete', methods=['POST'])
def admin_delete_order(username, order_id):
    """Удаление заказа"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in users or 'userorders' not in users[username]:
        return jsonify({'error': 'User or order not found'}), 404
    
    # Удаляем заказ
    original_orders = users[username]['userorders']
    users[username]['userorders'] = [order for order in original_orders if order['id'] != order_id]
    
    # Если удалили, синхронизируем баланс
    if len(users[username]['userorders']) < len(original_orders):
        sync_user_balance(username)
        save_data()
        return jsonify({'success': True, 'message': 'Заказ удален'})
    else:
        return jsonify({'error': 'Order not found'}), 404


# ====================== 4. НАСТРОЙКИ ПРИЕМА СРЕДСТВ
@app.route('/admin/payment_settings')
def admin_payment_settings():
    """Настройки приема средств"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    # Загружаем настройки кошельков
    try:
        with open('payment_wallets.json', 'r') as f:
            wallets = json.load(f)
    except FileNotFoundError:
        wallets = {
            'bep20': '0x742d35Cc6634C0532925a3b8D4B5b875aD0B0000',
            'ton': 'UQCD39VS5jcptHL8vMjEXrzGaRcCVYto7HUn4bpAOg8xqB2N'
        }
    
    return render_template('19.admin_payment_settings.html', wallets=wallets)


@app.route('/admin/payment_settings/update', methods=['POST'])
def admin_update_payment_settings():
    """Обновление настроек приема средств"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Сохраняем настройки кошельков
    wallets = {
        'bep20': data.get('bep20', ''),
        'ton': data.get('ton', '')
    }
    
    with open('payment_wallets.json', 'w') as f:
        json.dump(wallets, f, indent=4)
    
    return jsonify({
        'success': True,
        'message': 'Настройки приема средств обновлены'
    })



# ====================== 5. УПРАВЛЕНИЕ ДАННЫМИ (ИМПОРТ/ЭКСПОРТ)
@app.route('/admin/data_management')
def admin_data_management():
    """Управление данными - импорт и экспорт JSON файлов"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    # Получаем информацию о файлах
    files_info = {
        'users': {
            'name': 'users.json',
            'description': 'Данные пользователей',
            'size': get_file_size('users.json'),
            'last_modified': get_file_last_modified('users.json')
        },
        'steam_discounts': {
            'name': 'steam_discounts.json',
            'description': 'Настройки скидок Steam',
            'size': get_file_size('steam_discounts.json'),
            'last_modified': get_file_last_modified('steam_discounts.json')
        },
        'stores': {
            'name': 'stores.json',
            'description': 'Данные магазинов',
            'size': get_file_size('stores.json'),
            'last_modified': get_file_last_modified('stores.json')
        },
        'payment_wallets': {
            'name': 'payment_wallets.json',
            'description': 'Настройки кошельков',
            'size': get_file_size('payment_wallets.json'),
            'last_modified': get_file_last_modified('payment_wallets.json')
        }
    }
    
    return render_template('20.admin_data_management.html', files_info=files_info)

@app.route('/admin/data/export/<file_type>')
def admin_export_data(file_type):
    """Экспорт JSON файла"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    file_mapping = {
        'users': USERS_FILE,
        'steam_discounts': STEAM_DISCOUNTS_FILE,
        'stores': STORES_FILE,
        'payment_wallets': 'payment_wallets.json'
    }
    
    if file_type not in file_mapping:
        flash('Неверный тип файла', 'error')
        return redirect(url_for('admin_data_management'))
    
    filename = file_mapping[file_type]
    
    try:
        return send_file(
            filename,
            as_attachment=True,
            download_name=f"{file_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mimetype='application/json'
        )
    except FileNotFoundError:
        flash('Файл не найден', 'error')
        return redirect(url_for('admin_data_management'))

@app.route('/admin/data/import/<file_type>', methods=['POST'])
def admin_import_data(file_type):
    """Импорт JSON файла"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    file_mapping = {
        'users': USERS_FILE,
        'steam_discounts': STEAM_DISCOUNTS_FILE,
        'stores': STORES_FILE,
        'payment_wallets': 'payment_wallets.json'
    }
    
    if file_type not in file_mapping:
        return jsonify({'error': 'Invalid file type'}), 400
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.json'):
        return jsonify({'error': 'File must be JSON'}), 400
    
    try:
        # Читаем и проверяем JSON
        content = file.read().decode('utf-8')
        data = json.loads(content)
        
        # Валидация данных в зависимости от типа файла
        if file_type == 'users':
            if not isinstance(data, dict):
                return jsonify({'error': 'Invalid users data format'}), 400
        elif file_type == 'steam_discounts':
            required_keys = ['base_fee', 'discount_levels', 'individual_discounts']
            if not all(key in data for key in required_keys):
                return jsonify({'error': 'Invalid steam discounts format'}), 400
        elif file_type == 'stores':
            if not isinstance(data, dict):
                return jsonify({'error': 'Invalid stores data format'}), 400
        elif file_type == 'payment_wallets':
            required_keys = ['bep20', 'ton']
            if not all(key in data for key in required_keys):
                return jsonify({'error': 'Invalid payment wallets format'}), 400
        
        # Создаем резервную копию
        backup_filename = f"{file_mapping[file_type]}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            with open(file_mapping[file_type], 'r') as original:
                with open(backup_filename, 'w') as backup:
                    backup.write(original.read())
        except FileNotFoundError:
            pass  # Если файла нет, пропускаем создание бэкапа
        
        # Сохраняем новые данные
        with open(file_mapping[file_type], 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        # Перезагружаем данные в память
        load_data()
        
        return jsonify({
            'success': True,
            'message': f'Файл {file_type} успешно импортирован',
            'backup_created': os.path.exists(backup_filename)
        })
        
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON file'}), 400
    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500

@app.route('/admin/data/backup/all')
def admin_backup_all_data():
    """Создание резервной копии всех данных"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    try:
        # Создаем папку для бэкапов если её нет
        backup_dir = 'backups'
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_data = {}
        
        # Собираем все данные
        files_to_backup = {
            'users': USERS_FILE,
            'steam_discounts': STEAM_DISCOUNTS_FILE,
            'stores': STORES_FILE,
            'payment_wallets': 'payment_wallets.json'
        }
        
        for key, filename in files_to_backup.items():
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    backup_data[key] = json.load(f)
            except FileNotFoundError:
                backup_data[key] = None
        
        # Сохраняем бэкап
        backup_filename = f"{backup_dir}/backup_{timestamp}.json"
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=4, ensure_ascii=False)
        
        return send_file(
            backup_filename,
            as_attachment=True,
            download_name=f"backup_{timestamp}.json",
            mimetype='application/json'
        )
        
    except Exception as e:
        flash(f'Ошибка при создании бэкапа: {str(e)}', 'error')
        return redirect(url_for('admin_data_management'))

# Вспомогательные функции
def get_file_size(filename):
    """Получает размер файла в читаемом формате"""
    try:
        size = os.path.getsize(filename)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    except FileNotFoundError:
        return "Файл не найден"

def get_file_last_modified(filename):
    """Получает дату последнего изменения файла"""
    try:
        timestamp = os.path.getmtime(filename)
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except FileNotFoundError:
        return "Файл не найден"




# ====================== 21. УПРАВЛЕНИЕ СКИДКАМИ STEAM
@app.route('/admin/steam_discounts')
def admin_steam_discounts():
    """Управление скидками и комиссиями Steam"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        abort(403)
    
    return render_template('21.admin_steam_discounts.html',
                         steam_base_fee=steam_base_fee,
                         discount_levels=steam_discount_levels,
                         individual_discounts=individual_discounts,
                         all_usernames=[u for u in users.keys() if u != 'admin'])

@app.route('/admin/steam_discounts/update_base_fee', methods=['POST'])
def admin_update_base_fee():
    """Обновление базовой комиссии"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    new_fee = data.get('base_fee')
    try:
        new_fee = float(new_fee)
        if new_fee < 0 or new_fee > 100:
            return jsonify({'error': 'Commission must be between 0 and 100'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid commission format'}), 400
    
    # Обновляем базовую комиссию
    global steam_base_fee
    steam_base_fee = new_fee
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'Базовая комиссия обновлена до {new_fee}%'
    })

@app.route('/admin/steam_discounts/update_levels', methods=['POST'])
def admin_update_discount_levels():
    """Обновление уровней скидок"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    new_levels = data.get('discount_levels', [])
    
    # Валидация данных
    if not isinstance(new_levels, list):
        return jsonify({'error': 'Invalid discount levels format'}), 400
    
    try:
        validated_levels = []
        for level in new_levels:
            if len(level) != 2:
                return jsonify({'error': 'Each level must contain [threshold, discount]'}), 400
            threshold = float(level[0])
            discount = float(level[1])
            if threshold < 0 or discount < 0 or discount > 100:
                return jsonify({'error': 'Invalid threshold or discount value'}), 400
            validated_levels.append((threshold, discount))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid numeric values in discount levels'}), 400
    
    # Сортируем по порогу
    validated_levels.sort(key=lambda x: x[0])
    
    # Обновляем уровни скидок
    global steam_discount_levels
    steam_discount_levels = validated_levels
    save_data()
    
    return jsonify({
        'success': True,
        'message': 'Уровни скидок обновлены'
    })

@app.route('/admin/steam_discounts/add_individual', methods=['POST'])
def admin_add_individual_discount():
    """Добавление индивидуальной скидки"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    username = data.get('username')
    discount = data.get('discount')
    
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        discount = float(discount)
        if discount < 0 or discount > 100:
            return jsonify({'error': 'Discount must be between 0 and 100'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid discount format'}), 400
    
    # Добавляем индивидуальную скидку
    individual_discounts[username] = discount
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'Индивидуальная скидка {discount}% установлена для {username}'
    })

@app.route('/admin/steam_discounts/remove_individual/<username>', methods=['POST'])
def admin_remove_individual_discount(username):
    """Удаление индивидуальной скидки"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    if username not in individual_discounts:
        return jsonify({'error': 'Individual discount not found'}), 404
    
    # Удаляем индивидуальную скидку
    removed_discount = individual_discounts.pop(username)
    save_data()
    
    return jsonify({
        'success': True,
        'message': f'Индивидуальная скидка {removed_discount}% удалена для {username}'
    })

@app.route('/admin/steam_discounts/reset_individual', methods=['POST'])
def admin_reset_individual_discounts():
    """Сброс всех индивидуальных скидок"""
    
    # Проверка прав администратора
    if 'username' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    # Сбрасываем все индивидуальные скидки
    global individual_discounts
    individual_discounts = {}
    save_data()
    
    return jsonify({
        'success': True,
        'message': 'Все индивидуальные скидки сброшены'
    })







# ====================== ERROR HANDLERS
@app.errorhandler(404)
def page_not_found(e):
    """Обработчик для 404 ошибки - страница не найдена"""
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    """Обработчик для 403 ошибки - доступ запрещен"""
    return render_template('404.html'), 403

@app.errorhandler(500)
def internal_server_error(e):
    """Обработчик для 500 ошибки - внутренняя ошибка сервера"""
    return render_template('404.html'), 500


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))
if __name__ == '__main__':
    app.run(debug=True)