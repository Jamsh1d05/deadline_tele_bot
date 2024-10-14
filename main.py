import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from datetime import datetime
from dotenv import load_dotenv
import os
import sqlite3
import time
import logging
import pytz

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('TEL_API_TOKEN')
MOODLE_URL = os.getenv('REQUEST_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID'))


logging.basicConfig(level=logging.INFO)
def start_bot():
    try:
        bot.polling(none_stop=True) 
    except Exception as e:
        logging.error(f"Error occurred: {e}")
        logging.info("Restarting bot...")
        time.sleep(5) 
        start_bot()

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Create and manage the SQLite database
def create_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # Create a table for storing user tokens
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL UNIQUE,
        first_name TEXT NOT NULL,
        token TEXT NOT NULL
    )
    ''')
                  
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS group_chat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL UNIQUE
    )

    ''')
    
    conn.commit()
    conn.close()

create_db()

def get_db_connection():
    return sqlite3.connect('users.db')

def store_token(chat_id, first_name, token):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO user_tokens (chat_id, first_name, token)
    VALUES (?, ?, ?)
    ''', (chat_id, first_name, token))
    conn.commit()
    conn.close()

def get_token(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT token FROM user_tokens WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def delete_token(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_tokens WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()


def modify_token(message):
    chat_id = message.chat.id
    new_token = message.text

    # Validate the new token (optional)
    if verify_security_key(new_token) is None:
        bot.send_message(chat_id, "The token you provided is invalid. Please try again.")
        return
    
    # Update the token in the database
    first_name = message.chat.first_name
    store_token(chat_id, first_name, new_token)
    
    bot.send_message(chat_id, "Your token has been updated successfully.")
    main_menu(message) 


def is_user_registered(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user_tokens WHERE chat_id = ?', (chat_id,))
    user = cursor.fetchone()
    conn.close()
    return user is not None

def get_users_id():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT chat_id FROM user_tokens')
    user_ids = cursor.fetchall()
    
    conn.close()

    return [user_id[0] for user_id in user_ids]

def get_all_group_chat_ids():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    cursor.execute('SELECT chat_id FROM group_chat')
    group_chat_ids = cursor.fetchall()

    conn.close()

    return [chat_id[0] for chat_id in group_chat_ids] 

def store_group_chat_id(chat_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    try:
        cursor.execute('''
        INSERT INTO group_chat (chat_id)
        VALUES (?)
        ''', (chat_id,))
        conn.commit()
        print(f"Group chat ID {chat_id} stored successfully.")
        
    except sqlite3.IntegrityError:
        print(f"Group chat ID {chat_id} already exists in the database.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()


# Show the main menu
menu_btn = None 
def main_menu(message):
    if message.chat.type == 'private':
        global menu_btn
        menu_btn = types.ReplyKeyboardMarkup(resize_keyboard=True)
        menu_btn.add(
            types.KeyboardButton('Deadlines'),
            types.KeyboardButton('Calculator'), 
            types.KeyboardButton('👤Profile'), 
            types.KeyboardButton('🔑Admin')
            )        
        bot.send_message(message.chat.id, 'Choose an action', reply_markup=menu_btn)
    else:
        bot.send_message(message.chat.id, 'Bot buttons are only available in private chat.')

#Calculator options
def calc_options(message):
    info_message = (
    "ℹ️ Выберите калькулятор\n\n"
    "1️⃣ GPA calculator\n"
    "GPA — это средний балл всех оценок за весь период обучения. "
    "Калькулятор GPA — это инструмент, который вычисляет среднее значение всех ваших оценок за период обучения, помогая вам отслеживать академическую успеваемость. "
    "Вы можете ввести свои предметы, кредиты и оценки, чтобы получать обновленный GPA каждый семестр.\n\n"
    "2️⃣ Рассчитать баллы для стипендии\n"
    "Данный калькулятор поможет узнать сколько процентов вам необходимо набрать на Final Exam."
    "Достаточно отправить оценку за Mid/End-Term."
)
    calc_btn = types.ReplyKeyboardMarkup(resize_keyboard=True)
    calc_btn.add(types.KeyboardButton('Scholarship'), types.KeyboardButton('GPA'), types.KeyboardButton('Exit'))
    bot.send_message(message.chat.id, info_message, reply_markup=calc_btn)
    
# Verify Moodle token
def verify_security_key(token):
    params = {
        'wstoken': token,
        'wsfunction': 'core_webservice_get_site_info',
        'moodlewsrestformat': 'json'
    }
    try:
        response = requests.get(MOODLE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if 'userid' in data:
            return data['userid']
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error verifying token: {e}")
        return None

# Get deadlines and assignments
def get_courses(token, user_id):
    params = {
        'wstoken': token,
        'wsfunction': 'core_enrol_get_users_courses',
        'moodlewsrestformat': 'json',
        'userid': user_id
    }
    try:
        response = requests.get(MOODLE_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving courses: {e}")
        return []

def get_assignments(token, course_id):
    params = {
        'wstoken': token,
        'wsfunction': 'mod_assign_get_assignments',
        'courseids[0]': course_id,
        'moodlewsrestformat': 'json'
    }
    try:
        response = requests.get(MOODLE_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving assignments: {e}")
        return {}

#Calculation of of the remaining time 
ASTANA_TZ = pytz.timezone('Asia/Almaty')  # Astana timezone
def time_remaining(due_date):
    due_date_obj = datetime.fromtimestamp(due_date, ASTANA_TZ)
    
    remaining_time = due_date_obj - datetime.now(ASTANA_TZ)
    
    remaining_days = remaining_time.days
    remaining_seconds = remaining_time.seconds
    remaining_hours = (remaining_seconds // 3600)
    remaining_minutes = (remaining_seconds % 3600) // 60

    if remaining_days < 1:
        return f"{remaining_hours} hours, {remaining_minutes} minutes"
    
    return f"{remaining_days} days, {remaining_hours} hours, {remaining_minutes} minutes"

#Show the deadlines
def show_deadlines(chat_id, token):
    user_id = verify_security_key(token)
    if user_id is None:
        bot.send_message(chat_id, "Invalid token or unable to retrieve user ID.")
        return

    courses = get_courses(token, user_id)
    if not courses:
        bot.send_message(chat_id, "No courses found.")
        return

    current_timestamp = int(datetime.now(ASTANA_TZ).timestamp())
    upcoming_assignments_by_course = {}

    for course in courses:
        course_id = course['id']
        course_name = course['fullname']
        assignments_data = get_assignments(token, course_id)

        if 'courses' in assignments_data:
            if course_name not in upcoming_assignments_by_course:
                upcoming_assignments_by_course[course_name] = []

            for course_assignments in assignments_data['courses']:
                if 'assignments' in course_assignments:
                    for assignment in course_assignments['assignments']:
                        due_date = assignment['duedate']
                        assignment_name = assignment['name'].lower()

                        if due_date >= current_timestamp and not any(term in assignment_name for term in ['midterm', 'endterm']):
                            time_left = time_remaining(due_date)
                            due_date_display = datetime.fromtimestamp(due_date, ASTANA_TZ).strftime('%d/%m | %H:%M')
                            upcoming_assignments_by_course[course_name].append({
                                'name': assignment['name'],
                                'due_date': due_date_display,
                                'time_remaining': time_left
                            })

    message = ""
    course_index = 1 
    for course_name, assignments in upcoming_assignments_by_course.items():
        if assignments:
            message += f"\n{course_index}. {course_name}\n"  
            message += "\n"
            for assignment in assignments:
                message += f"   📝{assignment['name']}\n"
                message += f"   📅Due Date: {assignment['due_date']}\n"
                message += f"   ⏳Time Remaining: {assignment['time_remaining']}\n"
            course_index += 1

    if message:
        bot.send_message(chat_id, message)
    else:
        bot.send_message(chat_id, "No upcoming assignments found.")
        

def scholarship_calculator(message):
    bot.send_message(message.chat.id, "ℹ️Введите оценку за Register Mid-Term:")
    bot.register_next_step_handler(message, get_first_attestation)

def get_first_attestation(message):
    if message.text == 'Exit':
        main_menu(message)
        return

    try:
        first_att = float(message.text)
        if first_att < 0 or first_att > 100:
            bot.send_message(message.chat.id, "Пожалуйста введите допустимую оценку от 0 до 100.")
            return bot.register_next_step_handler(message, get_first_attestation)

        bot.send_message(message.chat.id, "ℹ️Введите оценку за Register End-Term")
        bot.register_next_step_handler(message, get_second_attestation, first_att)
    except ValueError:
        bot.send_message(message.chat.id, "Неверный ввод.Пожалуйста введите действительную оценку за Register Mid-Term: ")
        bot.register_next_step_handler(message, get_first_attestation)

def get_second_attestation(message, first_att):
    if message.text == 'Exit':
        main_menu(message)
        return


    try:
        second_att = float(message.text)
        if second_att < 0 or second_att > 100:
            bot.send_message(message.chat.id, "Пожалуйста введите допустимую оценку от 0 до 100.")
            return bot.register_next_step_handler(message, get_second_attestation, first_att)

        calculate_scholarship(first_att, second_att, message)
    except ValueError:
        bot.send_message(message.chat.id, "Неверный ввод.Пожалуйста введите действительную оценку за Register End-Term:")
        bot.register_next_step_handler(message, get_second_attestation, first_att)

def calculate_scholarship(first_att, second_att, message):
    current_grade = 0.3 * first_att + 0.3 * second_att

    required_for_retake = max(50, (50 - current_grade) / 0.4)  
    required_for_scholarship = max(50, (70 - current_grade) / 0.4)  
    required_for_high_scholarship = max(0, (90 - current_grade) / 0.4)
    grade_if_100_final = current_grade + 0.4 * 100

    if required_for_high_scholarship > 100:
        high_scholarship_message = "Невозможно"
    else:
        high_scholarship_message = f"{required_for_high_scholarship:.2f}%"

    result_message = (
        f"1️⃣ Не получить RETAKE или FX (>50): {required_for_retake:.2f}%\n"
        f"2️⃣ Для сохранения стипендии (>70): {required_for_scholarship:.2f}%\n"
        f"3️⃣ Для повышенной стипендии (>90): {high_scholarship_message}\n"
        f"4️⃣ Ваша итоговая оценка {grade_if_100_final:.2f}% если вы получите 100% на Final Exam"
    )
    bot.send_message(message.chat.id, result_message)



# Profile options
def profile_options():
    markup = types.InlineKeyboardMarkup()
    delete_button = types.InlineKeyboardButton("Delete", callback_data="delete_token_text")
    modify_button = types.InlineKeyboardButton("Modify", callback_data="modify_token_text")
    exit_button = types.InlineKeyboardButton("Exit", callback_data="exit")
    markup.add(delete_button, modify_button, exit_button)
    return markup

# Admin panel
def adm_btn(message):
    adm_btn = types.ReplyKeyboardMarkup(resize_keyboard=True)
    adm_btn.add(types.KeyboardButton('Users data'), types.KeyboardButton('Broadcast Message'), types.KeyboardButton('Exit'))
    bot.send_message(message.chat.id, 'Choose an action', reply_markup=adm_btn)


# Telegram Handlers
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    if is_user_registered(chat_id):
        main_menu(message)
    else:
        text = "[here](https://moodle.astanait.edu.kz/user/managetoken.php)"
        bot.send_message(chat_id, f"Welcome\\! Please provide your Moodle token You can get it {text}:", parse_mode='MarkdownV2')



def broadcast_btn(message):
    brd_btn = types.ReplyKeyboardMarkup(resize_keyboard=True)
    brd_btn.add(types.KeyboardButton('Induvidual chats'),types.KeyboardButton('Group chats'),types.KeyboardButton('Exit'))
    bot.send_message(message.chat.id, 'Choose an action', reply_markup=brd_btn)


def send_broadcast_for_group(message):
    all_ids = get_all_group_chat_ids() 
    message_text = message.text

    if message_text.lower() == "exit":
        bot.send_message(message.chat.id, "Broadcast canceled. Returning to main menu.", reply_markup=types.ReplyKeyboardRemove())
        main_menu(message)


    for chat_id in all_ids:
        try:    
            bot.send_message(chat_id, message_text) 
        except Exception as e:
            print(f"Failed to send message to {chat_id}: {e}")
    
    bot.send_message(message.chat.id, "Broadcast message sent successfully!")
    broadcast_btn(message)

def send_broadcast_for_private_chats(message):
    all_ids = get_users_id()
    message_text = message.text

    if message_text.lower() == "exit":
        bot.send_message(message.chat.id, "Broadcast canceled. Returning to main menu.", reply_markup=types.ReplyKeyboardRemove())
        main_menu(message)


    for chat_id in all_ids:
        try:
            bot.send_message(chat_id, message_text)
        except Exception as e :
            bot.send_message(message.chat.id , f"Failed to send a message to {chat_id}: {e}")

    bot.send_message(message.chat.id, "Broadcast message sent successfully!")
    broadcast_btn(message)


def process_group_chat_message(message):
    if message.text.lower() == 'exit':
        adm_btn(message)  
        bot.send_message(message.chat.id, "Canceled")
    else:
        send_broadcast_for_group(message)



def process_private_chat_message(message):
    if message.text.lower() == 'exit':
        adm_btn(message)  
        bot.send_message(message.chat.id, "Canceled")
    else:
        send_broadcast_for_private_chats(message)


@bot.message_handler(func=lambda message: message.text == 'Broadcast Message', content_types=['text'])
def handle_broadcast(message):
    broadcast_btn(message)


@bot.message_handler(func=lambda message: message.text == 'Group chats', content_types=['text'])
def group_chat(message):
    ex_btn = types.ReplyKeyboardMarkup(resize_keyboard=True)
    ex_btn.add(types.InlineKeyboardButton('Exit'))    
    msg = bot.send_message(message.chat.id, "Enter your message: ", reply_markup=ex_btn)
    bot.register_next_step_handler(msg, process_group_chat_message)


@bot.message_handler(func=lambda message: message.text == 'Induvidual chats', content_types=['text'])
def private_chat(message):
    ex_btn = types.ReplyKeyboardMarkup(resize_keyboard=True)
    ex_btn.add(types.InlineKeyboardButton('Exit'))
    msg = bot.send_message(message.chat.id, "Enter your message: ", reply_markup=ex_btn)
    bot.register_next_step_handler(msg, process_private_chat_message)


@bot.message_handler(func=lambda message: message.text == 'Exit')
def private_chat(message):
    main_menu(message)



#Handler for Calculator
@bot.message_handler(func=lambda message: message.text == 'Calculator')
def calculator(message):
    calc_options(message)
    
@bot.message_handler(func=lambda message: message.text == 'Scholarship')
def scholar_calc(message):
    scholarship_calculator(message)

#logic for GPA calculation
@bot.message_handler(func=lambda message: message.text == 'GPA')
def gpa_calc(message):
    bot.send_message(message.chat.id, 'В скором времени будет доступно!')

#Sending updates
@bot.message_handler(commands=['update'])
def get_update(message):
    if message.chat.type == 'private':
        global menu_btn  
        if menu_btn is None:
            bot.send_message(message.chat.id, 'Menu button is not yet initialized.')
        else:
            bot.send_message(message.chat.id, 'No updates available!')
    else:
        bot.send_message(message.chat.id, 'Run the /update command in private chat!')


@bot.message_handler(func=lambda message: message.text == '🔑Admin')
def admin_panel(message):
    chat_id = message.chat.id
    if chat_id == ADMIN_ID:
        bot.send_message(chat_id, 'Assalamu aleykum boss!')
        adm_btn(message)
    else:
        bot.send_message(chat_id, "You don't have admin access.")

@bot.message_handler(func=lambda message: message.text == 'Users data')
def send_users_data(message):
    chat_id = message.chat.id
    file_path = 'users.db'
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            bot.send_document(chat_id, file)
    else:
        bot.send_message(chat_id, "Users data file not found.")

@bot.message_handler(func=lambda message: message.text == 'Exit')
def send_users_data(message):
    main_menu(message)



@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text

    if message.chat.type in ['group', 'supergroup']:

        if text == '/deadlines@assign_deadlines_bot' or text == '/deadlines':
            log_id = message.chat.id
            store_group_chat_id(log_id)
            user_token = get_token(message.from_user.id)
            if user_token:
                show_deadlines(chat_id, user_token)
            else:
                text = "[here](https://moodle.astanait.edu.kz/user/managetoken.php)"
                bot.send_message(chat_id, f'Please provide a token in a private chat first, you can get it {text}', parse_mode='MarkdownV2')
        return


    if len(text) == 32: 
        user_id = verify_security_key(text) 
        user = message.from_user
        first_name = user.first_name or "unknown"

        if user_id:
            store_token(chat_id, first_name, text)  
            bot.send_message(chat_id, "Thank you! Token stored. ")
            bot.delete_message(chat_id, message.message_id)
            main_menu(message)
        else:
            bot.send_message(chat_id, "Invalid token. Please try again.")
    elif text == '👤Profile':
        token = get_token(chat_id)

        if token:
            markup = InlineKeyboardMarkup()
            token_button = InlineKeyboardButton(text=f"{token}", callback_data="token")
            delete_button = InlineKeyboardButton(text="Delete", callback_data="delete_token_text")
            modify_button = InlineKeyboardButton(text="Modify", callback_data="modify_token_text")
            exit_button = InlineKeyboardButton(text="Exit", callback_data="exit")
            
            markup.add(token_button)
            markup.add(delete_button, modify_button)
            markup.add(exit_button)
            
            bot.send_message(chat_id, "What would you like to do with your token?", reply_markup=markup)
        else:
            bot.send_message(chat_id, 'No token found. Please provide a token first.')
    elif text == 'Deadlines' or text == '/deadlines':
        token = get_token(chat_id)
        if token:
            show_deadlines(chat_id, token)
        else:
            bot.send_message(chat_id, 'Please provide a token to see deadlines.')


@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    chat_id = call.message.chat.id
    if call.data == "delete_token_text":
        delete_token(chat_id)
        bot.send_message(chat_id, "Your token has been deleted.")
    elif call.data == "modify_token_text":
        bot.send_message(chat_id, "Please provide your new token:")
        bot.register_next_step_handler(call.message, modify_token)
    elif call.data == "exit":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        main_menu(call.message)

# Polling the bot
if __name__ == "__main__":
    start_bot()
