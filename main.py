import aiohttp
import aiosqlite
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

from aiogram import Bot, Dispatcher, Router,types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,InlineKeyboardButton,ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.filters import Command  
from aiogram.filters.state import StateFilter

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('TEL_API_TOKEN')
MOODLE_URL = os.getenv('REQUEST_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# Setup logging
logging.basicConfig(level=logging.INFO)

#User state
class UserState(StatesGroup):
    waiting_for_token = State()


#Calculator state
class ScholarshipStates(StatesGroup):
    waiting_for_first_attestation = State()
    waiting_for_second_attestation = State()


#Broadcast state 
class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_group_message = State()


# Database initialization
async def create_db():
    async with aiosqlite.connect('users.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL UNIQUE,
                first_name TEXT NOT NULL,
                token TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS group_chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL UNIQUE
            )
        ''')
        await db.commit()

async def store_token(chat_id, first_name, token):
    async with aiosqlite.connect('users.db') as db:
        await db.execute('''
            INSERT OR REPLACE INTO user_tokens (chat_id, first_name, token)
            VALUES (?, ?, ?)
        ''', (chat_id, first_name, token))
        await db.commit()

async def get_token(chat_id):
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT token FROM user_tokens WHERE chat_id = ?', (chat_id,))
        result = await cursor.fetchone()
        return result[0] if result else None

async def store_group_chat_id(chat_id):
    async with aiosqlite.connect('users.db') as db:
        try:
            await db.execute('INSERT INTO group_chat (chat_id) VALUES (?)', (chat_id,))
            await db.commit()
        except aiosqlite.IntegrityError:
            logging.info(f"Group chat {chat_id} already stored")

async def get_all_group_chat_ids():
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT chat_id FROM group_chat')
        return [row[0] for row in await cursor.fetchall()]
    
async def get_users_id():
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT chat_id FROM user_tokens')
        return [user_id[0] for user_id in await cursor.fetchall()]



async def is_user_registered(chat_id):
    async with aiosqlite.connect('users.db') as db:

        cursor = await db.execute('SELECT * FROM user_tokens WHERE chat_id = ?', (chat_id,))
        user = await cursor.fetchone()
        return user is not None



async def delete_token(chat_id):
    try:
        async with aiosqlite.connect('users.db') as db:
            await db.execute('DELETE FROM user_tokens WHERE chat_id = ?', (chat_id,))
            await db.commit()
    except Exception as e:
        print(f"Error deleting token for {chat_id}: {e}")


async def verify_security_key(token):
    params = {
        'wstoken': token,
        'wsfunction': 'core_webservice_get_site_info',
        'moodlewsrestformat': 'json'
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MOODLE_URL, params=params) as response:
                data = await response.json()
                return data.get('userid')
    except aiohttp.ClientError as e:
        logging.error(f"Error verifying token: {e}")
        return None

async def get_courses(token, user_id):
    params = {
        'wstoken': token,
        'wsfunction': 'core_enrol_get_users_courses',
        'moodlewsrestformat': 'json',
        'userid': user_id
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(MOODLE_URL, params=params) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            logging.error(f"Error retrieving courses: {e}")
            return []

async def get_assignments(token, course_id):
    params = {
        'wstoken': token,
        'wsfunction': 'mod_assign_get_assignments',
        'courseids[0]': course_id,
        'moodlewsrestformat': 'json'
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(MOODLE_URL, params=params) as response:
                return await response.json()
        except aiohttp.ClientError as e:
            logging.error(f"Error retrieving assignments: {e}")
            return {}

"""
def time_remaining(due_date):
    due_date_obj = datetime.fromtimestamp(due_date)
    remaining_time = due_date_obj - datetime.now()
    remaining_days = remaining_time.days
    remaining_seconds = remaining_time.seconds
    remaining_hours = remaining_seconds // 3600
    remaining_minutes = (remaining_seconds % 3600) // 60
    return f"{remaining_days} days, {remaining_hours} hours, {remaining_minutes} minutes" if remaining_days > 0 else f"{remaining_hours} hours, {remaining_minutes} minutes"

"""
    
# Bot states for calculator
class CalculatorStates(StatesGroup):
    midterm = State()
    endterm = State()

#Menu buttons
async def main_menu(message):
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Deadlines"),KeyboardButton(text="Calculator"))
    builder.row(KeyboardButton(text="👤Profile"))

    if message.chat.id == ADMIN_ID:
        builder.add(KeyboardButton(text="🔑Admin"))
    
    await message.answer("Choose an action:", reply_markup=builder.as_markup(resize_keyboard=True))



async def adm_btn(message):
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Users"),KeyboardButton(text="Broadcast"))
    builder.row(KeyboardButton(text="Exit"))
    
    await message.answer("Choose an action:", reply_markup=builder.as_markup(resize_keyboard=True))



async def broadcast_btn(message):
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Induvidual chats"),KeyboardButton(text="Group chats"))
    builder.row(KeyboardButton(text="Exit"))
    
    await message.answer("Choose an action:", reply_markup=builder.as_markup(resize_keyboard=True))



def kz_time(utc_timestamp):
    utc_time = datetime.utcfromtimestamp(utc_timestamp)
    kz_time = utc_time + timedelta(hours=5)

    return kz_time.strftime('%d-%m | %H:%M')


async def show_deadlines(message, token):
    user_id = await verify_security_key(token)
    courses = await get_courses(token, user_id)
    
    if not courses:
        await message.answer("No courses found.")
        return

    upcoming_assignments = {}
    current_timestamp = int(datetime.now().timestamp())
    tasks = [get_assignments(token, course['id']) for course in courses]
    assignments = await asyncio.gather(*tasks)
    
    # Collecting deadlines
    for course, assignment_list in zip(courses, assignments):
        course_name = course['fullname']
        for course_assignment in assignment_list.get('courses', []):
            for assignment in course_assignment.get('assignments', []):
                due_date = assignment['duedate']
                assignment_name = assignment['name'].lower()

                days_left = (due_date - current_timestamp) // (24 * 3600)
                
                if due_date >= current_timestamp and not any(term in assignment_name for term in ['midterm', 'endterm']):
                    #time_left = time_remaining(due_date)
                    if course_name not in upcoming_assignments:
                        upcoming_assignments[course_name] = [] 

                    if due_date >= current_timestamp:

                        due_date = datetime.fromtimestamp(due_date)
                        current_time = datetime.fromtimestamp(current_timestamp)
                        
                        time_left = due_date - current_time
                        days_left = time_left.days
                        hours_left, remainder = divmod(time_left.seconds, 3600)
                        minutes_left, seconds_left = divmod(remainder, 60)


                    upcoming_assignments[course_name].append({
                        'name': assignment['name'],
                        'due_date': kz_time(due_date),
                        'days_left': days_left,
                        'hours_left': hours_left,
                        'minutes_left': minutes_left,
                    })  

    message_text = ''
    message_parts = []  
    assignment_index = 1

    for course, assignments in upcoming_assignments.items():
        for assignment in assignments:
            message_text += "\n"
            due_date_str = assignment['due_date'].strftime('%d %B %H:%M:%S')

            if assignment['days_left'] < 1:
                time_left = f"{assignment['hours_left']} hours, {assignment['minutes_left']:02d} minutes left"
            else:
                time_left = f"{assignment['days_left']} days left"


            message_parts.append(
                (f"{assignment_index}. {due_date_str} ({time_left})\n"
                             f"📝 {assignment['name']} is due - {course}\n")
                )
            assignment_index += 1

    message_text = "\n".join(message_parts)
    await bot.send_message(message, message_text if message_text else "No upcoming deadlines.")


@router.message(Command("start")) 
async def send_welcome(message: Message, state: FSMContext):
    chat_id = message.chat.id

    if await is_user_registered(chat_id):
        await main_menu(message)
    else:
        text = "[here](https://moodle.astanait.edu.kz/user/managetoken.php)"
        await bot.send_message(chat_id, f"Welcome\\! Please provide your Moodle token You can get it {text}:", parse_mode='MarkdownV2')

    token = await get_token(message.from_user.id)

    if not token :
        await state.set_state(UserState.waiting_for_token)



@router.message(UserState.waiting_for_token)
async def handle_message(message: Message, state: FSMContext):
    chat_id = message.chat.id
    text = message.text

    if await verify_security_key(text):
        user = message.from_user
        first_name = user.first_name or "unknown"
        await store_token(chat_id, first_name, text)
        
        await message.answer("Thank you! Your token has been registered.")
        await main_menu(message)

        await state.clear()

    else:
        await message.answer("Invalid token. Please try again.")



@router.message(Command("deadlines"))
async def handle_message(message: Message):
    chat_id = message.chat.id
    text = message.text

    if message.chat.type in ['group', 'supergroup']:
            log_id = message.chat.id
            await store_group_chat_id(log_id) 
            user_token = await get_token(message.from_user.id)
            if user_token:
                await show_deadlines(chat_id, user_token)
            else:
                text = "[here](https://moodle.astanait.edu.kz/user/managetoken.php)"
                await message.answer(f'Please provide a Moodle "Mobile Web Service" token in a private chat of the bot first. You can get it {text}', parse_mode='MarkdownV2')
    




@router.message(lambda message: message.text == "Deadlines")
async def handle_deadlines(message: Message, state: FSMContext):
    token = await get_token(message.from_user.id)
    user_data = await state.get_data()
    chat_id = message.chat.id

    if user_data.get("is_processing"):
        return    
    if token:
        user_id = await verify_security_key(token)
        if user_id:
            await show_deadlines(chat_id, token)
        else:
            await message.answer("Invalid token. Please provide a valid token.")
    else:
        await message.answer('Please provide a token first!')
        await state.set_state(UserState.waiting_for_token)
        
           


@router.message(F.text == "Calculator")
async def calculator_menu(message: Message):

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


    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="GPA"))
    builder.add(KeyboardButton(text="Scholarship"))
    builder.add(KeyboardButton(text="Exit"))
    await message.answer(info_message, reply_markup=builder.as_markup(resize_keyboard=True))

@router.message(lambda message: message.text == "Scholarship")
async def scholarship_calculator(message: Message, state: FSMContext):
    await bot.send_message(message.chat.id, "ℹ️Введите оценку за Register Mid-Term:")
    
    await state.set_state(ScholarshipStates.waiting_for_first_attestation)


@router.message(lambda message: message.text == "GPA")
async def scholarship_calculator(message: Message, state: FSMContext):
    await message.answer("Will be added soon!")




@router.message(lambda message: message.text == "Exit")
async def scholarship_calculator(message: Message):
    await main_menu(message)


# Handler for the first attestation
@router.message(ScholarshipStates.waiting_for_first_attestation)
async def get_first_attestation(message: Message, state: FSMContext):
    if message.text.lower() == 'exit':
        await main_menu(message, state)
        return
    
    try:
        first_att = float(message.text)
        if first_att < 0 or first_att > 100:
            await bot.send_message(message.chat.id, "Пожалуйста введите допустимую оценку от 0 до 100.")
            return
        await state.update_data(first_att=first_att)
        
        await bot.send_message(message.chat.id, "ℹ️Введите оценку за Register End-Term:")
        
        await state.set_state(ScholarshipStates.waiting_for_second_attestation)
    except ValueError:
        await bot.send_message(message.chat.id, "Неверный ввод. Пожалуйста, введите действительную оценку за Register Mid-Term.")
    
# Handler for the second attestation
@router.message(ScholarshipStates.waiting_for_second_attestation)
async def get_second_attestation(message: Message, state: FSMContext):
    if message.text.lower() == 'exit':
        await main_menu(message, state)
        return

    try:
        second_att = float(message.text)
        if second_att < 0 or second_att > 100:
            await bot.send_message(message.chat.id, "Пожалуйста введите допустимую оценку от 0 до 100.")
            return
        
        data = await state.get_data()
        first_att = data.get("first_att")
        
        await calculate_scholarship(first_att, second_att, message)
        
        await state.clear()
    except ValueError:
        await bot.send_message(message.chat.id, "Неверный ввод. Пожалуйста, введите действительную оценку за Register End-Term.")

async def calculate_scholarship(first_att: float, second_att: float, message: Message):
    current_grade = 0.3 * first_att + 0.3 * second_att

    required_for_retake = max(50, (50 - current_grade) / 0.4)
    required_for_scholarship = max(50, (70 - current_grade) / 0.4)
    required_for_high_scholarship = max(0, (90 - current_grade) / 0.4)
    grade_if_100_final = current_grade + 0.4 * 100

    high_scholarship_message = f"{int(required_for_high_scholarship)}%" if required_for_high_scholarship <= 100 else "Невозможно"
    not_retake = int(required_for_retake)
    for_scholar = int(required_for_scholarship)
    total_if_100 = int(grade_if_100_final)

    result_message = (
        f"1️⃣ Не получить RETAKE или FX (>50): {not_retake}%\n"
        f"2️⃣ Для сохранения стипендии (>70): {for_scholar}%\n"
        f"3️⃣ Для повышенной стипендии (>90): {high_scholarship_message}\n"
        f"4️⃣ Ваша итоговая оценка {total_if_100}% если вы получите 100% на Final Exam"
    )

    await bot.send_message(message.chat.id, result_message)



def get_keyboard():
    buttons = [
        [
            types.InlineKeyboardButton(text="Delete", callback_data="token_delete")
        ],
        [types.InlineKeyboardButton(text="Exit", callback_data="token_exit")]
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(F.data.startswith("token_"))
async def callbacks_num(callback: types.CallbackQuery):
    action = callback.data.split("_")[1]
    chat_id = callback.message.chat.id
    message_id = callback.message.message_id

    if action == "delete":
        await delete_token(chat_id)
        await bot.edit_message_text(
            text='Your token is deleted!', 
            chat_id=chat_id,  
            message_id=message_id 
        )

        
    elif action == "exit":
        await main_menu(callback.message)
        await bot.delete_message(chat_id, message_id)

    await callback.answer()


@router.message(lambda message: message.text == "👤Profile")
async def profile_options(message):
        chat_id = message.chat.id
        token = await get_token(chat_id)
        await message.answer(f"Your token: \n\n {token}",reply_markup=get_keyboard())
         


async def send_broadcast_for_group(message):
    all_ids = await get_all_group_chat_ids() 
    message_text = message.text

    if message_text.lower() == "exit":
        await message.answer(message.chat.id, "Broadcast canceled. Returning to main menu.", reply_markup=types.ReplyKeyboardRemove())
        await main_menu(message)
        return


    for chat_id in all_ids:
        try:    
            await bot.send_message(chat_id, message_text) 
        except Exception as e:
            print(f"Failed to send message to {chat_id}: {e}")
    
    await message.answer("Broadcast message sent successfully!")
    await broadcast_btn(message)



async def send_broadcast_for_private_chats(message):
    all_ids = await get_users_id()
    message_text = message.text

    if message_text.lower() == "exit":
        bot.send_message(message.chat.id, "Broadcast canceled. Returning to main menu.", reply_markup=types.ReplyKeyboardRemove())
        await main_menu(message)
        return

    for chat_id in all_ids:
        try:
            await bot.send_message(chat_id, message_text)
        except Exception as e :
            await message.answer(message.chat.id , f"Failed to send a message to {chat_id}: {e}")

    await message.answer("Broadcast message sent successfully!")
    await broadcast_btn(message)



async def process_group_chat_message(message):
    if message.text.lower() == 'exit':
        await adm_btn(message)  
        await message.answer(message.chat.id, "Canceled")
    else:
        await send_broadcast_for_group(message)


async def process_private_chat_message(message):
    if message.text.lower() == 'exit':
        await adm_btn(message)  
        await message.answer(message.chat.id, "Canceled")
    else:
        await send_broadcast_for_private_chats(message)


@router.message(lambda message : message.text == "🔑Admin")
async def admin_panel(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Assalamu aleykum boss!")
        await adm_btn(message)
    
    else:
        await message.answer("You are not admin!")



@router.message(lambda message: message.text == "Users")
async def send_users_data(message):
    chat_id = message.chat.id
    file_path = 'users.db'
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            bot.send_document(chat_id, file)
    else:
        await message.answer('Users data not found!')



@router.message(lambda message: message.text == "Broadcast")
async def brd_menu(message):
    await broadcast_btn(message)



@router.message(lambda message: message.text == "Induvidual chats")
async def private_chat(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Exit"))
    msg = await bot.send_message(message.chat.id, "Enter your message: ", reply_markup=builder.as_markup(resize_keyboard=True))

    await state.set_state(BroadcastStates.waiting_for_message)


@router.message(BroadcastStates.waiting_for_message)
async def handle_broadcast_message(message: types.Message, state: FSMContext):


    if message.content_type == "text": 
        await process_private_chat_message(message)
    else:
        await message.answer("Please send a text message.")
    
    await state.clear()
    


@router.message(lambda message: message.text == "Group chats")
async def group_chat(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="Exit"))
    msg = await bot.send_message(message.chat.id, "Enter your message: ", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(BroadcastStates.waiting_for_group_message)


@router.message(BroadcastStates.waiting_for_group_message)
async def handle_group_broadcast_message(message: types.Message, state: FSMContext):
    if message.content_type == "text": 
        await process_group_chat_message(message)
    else:
        await message.answer("Please send a text message.")
    await state.clear()



async def main():
    await create_db()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())