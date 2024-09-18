import telebot
from telebot import types
import requests
from datetime import datetime
from dotenv import load_dotenv
import os
import sqlite3

# Telegram bot token
load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# Moodle API request URL
MOODLE_URL = 'https://moodle.astanait.edu.kz/webservice/rest/server.php'

# DataBase model
def create_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    

    # Create a table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL UNIQUE,
        first_name TEXT NOT NULL,
        token TEXT NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()

create_db()

def get_db_connection():
    conn = sqlite3.connect('users.db')
    return conn

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
    
    if result:
        return result[0]
    return None

def main_menu(message):
    menu_btn = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu_btn.add(types.KeyboardButton('See deadlines'), types.KeyboardButton('👤Profile'))
    bot.send_message(message.chat.id, 'Choose an action', reply_markup=menu_btn)

def profile_options():
    markup = types.InlineKeyboardMarkup()
    delete_button = types.InlineKeyboardButton("Delete", callback_data="delete_token_text")
    modify_button = types.InlineKeyboardButton("Modify", callback_data="modify_token_text")
    exit_button = types.InlineKeyboardButton("Exit", callback_data="exit")
    markup.add(delete_button, modify_button, exit_button)
    return markup

# Function to delete a token
def delete_token(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM user_tokens WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

# Function to modify a token
def modify_token(message):
    chat_id = message.chat.id
    new_token = message.text

    user_id = verify_security_key(new_token)
    if user_id:
        first_name = message.from_user.first_name or "unknown"
        store_token(chat_id, first_name, new_token)  
        bot.send_message(chat_id, "Your token has been updated.")
    else:
        bot.send_message(chat_id, "Invalid token. Please try again.")

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
        print(f"An error occurred while verifying the security key: {e}")
        return None

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
        print(f"An error occurred while retrieving courses: {e}")
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
        print(f"An error occurred while retrieving assignments: {e}")
        return {}

def days_remaining(due_date):
    due_date_obj = datetime.fromtimestamp(due_date)
    remaining_days = (due_date_obj - datetime.now()).days
    return remaining_days

def show_deadlines(chat_id, token):
    user_id = verify_security_key(token)
    if user_id is None:
        bot.send_message(chat_id, "Invalid token or unable to retrieve user ID.")
        return

    courses = get_courses(token, user_id)
    if not courses:
        bot.send_message(chat_id, "No courses found.")
        return

    current_timestamp = int(datetime.now().timestamp())
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
                            remaining_days = days_remaining(due_date)
                            upcoming_assignments_by_course[course_name].append({
                                'name': assignment['name'],
                                'due_date': datetime.fromtimestamp(due_date).strftime('%Y-%m-%d %H:%M:%S'),
                                'days_remaining': remaining_days
                            })

    message = ""
    course_index = 1 
    for course_name, assignments in upcoming_assignments_by_course.items():
        if assignments:
            message += f"\n{course_index}. {course_name}\n"  # Numbering for each course
            message += "\n"
            for assignment in assignments:
                message += f"   {assignment['name']}\n"
                message += f"   Due Date: {assignment['due_date']}\n"
                message += f"   Days Remaining: {assignment['days_remaining']} days\n"
            course_index += 1

    if message:
        bot.send_message(chat_id, message)
    else:
        bot.send_message(chat_id, "No upcoming assignments found.")

# Start the bot
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "Welcome! Please provide your Moodle mobile web service token to proceed:")

# Handle the user input and store the token
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text

    if message.chat.type in ['group', 'supergroup']:

        if text == '/deadlines':
            user_token = get_token(message.from_user.id)
            if user_token:
                bot.send_message(chat_id, "Just a second...")
                show_deadlines(chat_id, user_token)
            else:
                bot.send_message(chat_id, 'Please provide a token in a private chat first.')
        return


    if len(text) == 32: 
        user_id = verify_security_key(text) 
        user = message.from_user
        first_name = user.first_name or "unknown"

        if user_id:
            store_token(chat_id, first_name, text)  
            bot.send_message(chat_id, "Thank you! Token stored. ")
            main_menu(message)
        else:
            bot.send_message(chat_id, "Invalid token. Please try again.")
    elif text == '👤Profile':
        token = get_token(chat_id)

        if token:
            bot.send_message(chat_id, f'Your stored token: {token}')
            bot.send_message(chat_id, 'What would you like to do?', reply_markup=profile_options())
        else:
            bot.send_message(chat_id, 'No token found. Please provide a token first.')
    elif text == 'See deadlines':
        token = get_token(chat_id)
        if token:
            bot.send_message(chat_id, "Just a second...")
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
        bot.send_message(chat_id, "You have exited the profile settings.")
        main_menu(call.message)  

bot.polling(non_stop=True)
