# bot.py
import logging
import random
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from flags_data import FLAGS

# Logging setup
logging.basicConfig(level=logging.INFO)

# Dummy HTTP server to satisfy Render's Web Service port requirement
   class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
       def do_GET(self):
           self.send_response(200)
           self.send_header("Content-Type", "text/plain")
           self.end_headers()
           self.wfile.write(b"Bot is alive!")

       def do_HEAD(self):
           self.send_response(200)
           self.end_headers()

       def log_message(self, *args):
           pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

# Start the dummy server in a background thread so it doesn't block the bot
threading.Thread(target=run_dummy_server, daemon=True).start()

# State constants for ConversationHandler
SELECT_MODE, SELECT_SCOPE, SELECT_COUNT, IN_QUIZ = range(4)

TOKEN = "8882888229:AAEe4mBnBwFJ_DKgxhNMG978RDSYZ2NQ2GA"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and presents game mode options."""
    text = (
        "🌍 *Welcome to the Global Flag Quiz Bot!*\n\n"
        "Test your geography knowledge across the world.\n"
        "Choose your preferred game mode below:"
    )
    keyboard = [
        [InlineKeyboardButton("🎯 Multiple Choice (4 Options)", callback_data="mode_mcq")],
        [InlineKeyboardButton("✍️ Direct Text Input (Hardcore)", callback_data="mode_text")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
        
    return SELECT_MODE

async def mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores mode and prompts for geographic scope."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['mode'] = query.data.replace("mode_", "")
    
    continents = sorted(list(set(f['continent'] for f in FLAGS)))
    keyboard = [[InlineKeyboardButton("🌍 All Continents (Global)", callback_data="scope_all")]]
    for cont in continents:
        keyboard.append([InlineKeyboardButton(f"📍 {cont}", callback_data=f"scope_{cont}")])
        
    await query.edit_message_text(
        "Select the region or scope for your quiz:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_SCOPE


async def scope_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores scope and prompts for total question count."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['scope'] = query.data.replace("scope_", "")
    
    keyboard = [
        [InlineKeyboardButton("5 Flags", callback_data="count_5"), InlineKeyboardButton("10 Flags", callback_data="count_10")],
        [InlineKeyboardButton("20 Flags", callback_data="count_20")]
    ]
    
    await query.edit_message_text(
        "How many flags do you want to play?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_COUNT


async def count_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initializes quiz session data and sends the first flag question."""
    query = update.callback_query
    await query.answer()
    
    total_requested = int(query.data.replace("count_", ""))
    scope = context.user_data['scope']
    
    if scope == "all":
        pool = FLAGS.copy()
    else:
        pool = [f for f in FLAGS if f['continent'] == scope]
        
    random.shuffle(pool)
    quiz_flags = pool[:min(total_requested, len(pool))]
    
    context.user_data['quiz_flags'] = quiz_flags
    context.user_data['total_questions'] = len(quiz_flags)
    context.user_data['current_index'] = 0
    context.user_data['score'] = 0
    
    await query.edit_message_text(f"🚀 Quiz Initialized! Total flags: {len(quiz_flags)}. Get ready!")
    return await send_next_flag(update, context)


async def send_next_flag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends current flag image with either MCQ options or direct prompt."""
    idx = context.user_data['current_index']
    flags = context.user_data['quiz_flags']
    
    if idx >= len(flags):
        return await show_final_score(update, context)
        
    current_item = flags[idx]
    mode = context.user_data['mode']
    chat_id = update.effective_chat.id
    
    caption_text = f"🚩 *Flag {idx + 1} of {len(flags)}*"
    
    if mode == "mcq":
        all_countries = [f['country'] for f in FLAGS if f['country'] != current_item['country']]
        distractors = random.sample(all_countries, min(3, len(all_countries)))
        choices = distractors + [current_item['country']]
        random.shuffle(choices)
        
        keyboard = [[InlineKeyboardButton(c, callback_data=f"answer_{c}")] for c in choices]
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=current_item['flag_url'],
            caption=caption_text + "\nIdentify this country:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=current_item['flag_url'],
            caption=caption_text + "\n\n✍️ *Type the exact name of this country:*",
            parse_mode="Markdown"
        )
        
    return IN_QUIZ


async def handle_mcq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates Multiple Choice answers."""
    query = update.callback_query
    await query.answer()
    
    user_answer = query.data.replace("answer_", "")
    idx = context.user_data['current_index']
    correct_country = context.user_data['quiz_flags'][idx]['country']
    
    if user_answer == correct_country:
        context.user_data['score'] += 1
        await query.message.reply_text(f"✅ *Correct!* It is *{correct_country}*.", parse_mode="Markdown")
    else:
        await query.message.reply_text(f"❌ *Incorrect!* Correct answer: *{correct_country}*.", parse_mode="Markdown")
        
    context.user_data['current_index'] += 1
    return await send_next_flag(update, context)


async def handle_text_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates Direct Text Input answers."""
    user_answer = update.message.text.strip()
    idx = context.user_data['current_index']
    correct_country = context.user_data['quiz_flags'][idx]['country']
    
    if user_answer.lower() == correct_country.lower():
        context.user_data['score'] += 1
        await update.message.reply_text(f"✅ *Spot on!*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *Wrong!* Correct answer: *{correct_country}*.", parse_mode="Markdown")
        
    context.user_data['current_index'] += 1
    return await send_next_flag(update, context)


async def show_final_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays final performance score and loops back to mode selection."""
    score = context.user_data.get('score', 0)
    total = context.user_data.get('total_questions', 0)
    
    score_text = (
        f"🏆 *Quiz Completed!*\n\n"
        f"📊 *Final Scoreboard:*\n"
        f"• Correct Answers: *{score} / {total}*\n\n"
        f"Want to play again? Choose your mode below:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎯 Multiple Choice (4 Options)", callback_data="mode_mcq")],
        [InlineKeyboardButton("✍️ Direct Text Input (Hardcore)", callback_data="mode_text")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=score_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )
    return SELECT_MODE


def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_MODE: [CallbackQueryHandler(mode_chosen, pattern="^mode_")],
            SELECT_SCOPE: [CallbackQueryHandler(scope_chosen, pattern="^scope_")],
            SELECT_COUNT: [CallbackQueryHandler(count_chosen, pattern="^count_")],
            IN_QUIZ: [
                CallbackQueryHandler(handle_mcq_answer, pattern="^answer_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_answer)
            ]
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    
    print("Bot is up and running...")
    app.run_polling()

if __name__ == "__main__":
    main()
