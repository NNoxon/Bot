import os
import uuid
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from datetime import datetime
from supabase import create_client

# -----------------------
# Configuration
# -----------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8519493548:AAGJzqk9KtiPz51pBlJAYZNVRuoyG-5bhHY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") 
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "uploads")
ADMIN_IDS = [8464611503]  # Replace with your Telegram user ID

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# User sessions
user_sessions = {}

# -----------------------
# Telegram Bot Functions
# -----------------------
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Sorry, you are not authorized to use this bot.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📚 Upload Book", callback_data="upload_book")],
        [InlineKeyboardButton("📊 Stats", callback_data="view_stats")],
        [InlineKeyboardButton("🚀 Bulk Upload (5 Books)", callback_data="bulk_upload")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📚 *Welcome to Book Upload Bot!*\n\n"
        "Choose an option:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Unauthorized access.")
        return
    
    data = query.data
    
    if data == "upload_book":
        user_sessions[user_id] = {"step": "waiting_title"}
        await query.edit_message_text(
            "📖 *Single Book Upload*\n\n"
            "Please send the book details in this format:\n\n"
            "`Title: Book Name\n"
            "Author: Author Name\n"
            "Category: Fiction`\n\n"
            "After this, you'll be asked to send the book file and thumbnail.",
            parse_mode='Markdown'
        )
    
    elif data == "bulk_upload":
        user_sessions[user_id] = {"step": "bulk_upload", "books": []}
        await query.edit_message_text(
            "🚀 *Bulk Upload - 5 Books*\n\n"
            "Send book details one by one in this format:\n\n"
            "`Title: Book Name\n"
            "Author: Author Name\n"
            "Category: Fiction`\n\n"
            "I'll ask for files after all 5 books.",
            parse_mode='Markdown'
        )
    
    elif data == "view_stats":
        stats = get_stats()
        await query.edit_message_text(
            f"📊 *Library Statistics*\n\n"
            f"• Total Books: {stats['total_books']}\n"
            f"• Total Downloads: {stats['total_downloads']}\n"
            f"• Total Size: {stats['total_size']}",
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    
    text = update.message.text
    session = user_sessions.get(user_id, {})
    
    if session.get("step") == "waiting_title":
        # Parse book details
        try:
            details = parse_book_details(text)
            if details:
                user_sessions[user_id] = {
                    "step": "waiting_book_file",
                    "book_data": details
                }
                await update.message.reply_text(
                    "✅ Book details saved!\n\n"
                    "Now please send the *BOOK FILE* (PDF/EPUB):",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Invalid format. Please use:\n\nTitle: ...\nAuthor: ...\nCategory: ...")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    elif session.get("step") == "waiting_book_file":
        await update.message.reply_text("📁 Please send the BOOK FILE first.")
    
    elif session.get("step") == "waiting_thumbnail":
        await update.message.reply_text("🖼️ Please send the THUMBNAIL image.")
    
    elif session.get("step") == "bulk_upload":
        # Bulk upload - collecting book details
        try:
            details = parse_book_details(text)
            if details:
                session["books"].append({"details": details})
                
                books_count = len(session["books"])
                if books_count < 5:
                    await update.message.reply_text(
                        f"✅ Book {books_count} saved!\n\n"
                        f"Send details for book {books_count + 1}/5:\n\n"
                        "`Title: ...\nAuthor: ...\nCategory: ...`",
                        parse_mode='Markdown'
                    )
                else:
                    user_sessions[user_id]["step"] = "bulk_waiting_files"
                    await update.message.reply_text(
                        "🎉 All 5 books details saved!\n\n"
                        "Now please send all 5 BOOK FILES in order (one by one):",
                        parse_mode='Markdown'
                    )
            else:
                await update.message.reply_text("❌ Invalid format. Please use:\n\nTitle: ...\nAuthor: ...\nCategory: ...")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_document(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    
    session = user_sessions.get(user_id, {})
    document = update.message.document
    
    if session.get("step") == "waiting_book_file":
        # Single upload - book file
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{document.file_name}"
        
        await file.download_to_drive(file_path)
        
        user_sessions[user_id]["book_data"]["book_file_path"] = file_path
        user_sessions[user_id]["step"] = "waiting_thumbnail"
        
        await update.message.reply_text(
            "📚 Book file received!\n\n"
            "Now please send the *THUMBNAIL* image:",
            parse_mode='Markdown'
        )
    
    elif session.get("step") == "bulk_waiting_files":
        # Bulk upload - book files
        books = session["books"]
        current_file_index = len([b for b in books if "book_file_path" in b])
        
        if current_file_index < 5:
            file = await context.bot.get_file(document.file_id)
            file_path = f"temp_bulk_{current_file_index}_{document.file_name}"
            
            await file.download_to_drive(file_path)
            books[current_file_index]["book_file_path"] = file_path
            
            files_received = current_file_index + 1
            if files_received < 5:
                await update.message.reply_text(
                    f"📚 Book file {files_received}/5 received!\n\n"
                    f"Send book file {files_received + 1}/5:"
                )
            else:
                user_sessions[user_id]["step"] = "bulk_waiting_thumbnails"
                await update.message.reply_text(
                    "✅ All 5 book files received!\n\n"
                    "Now please send all 5 THUMBNAILS in order (one by one):"
                )

async def handle_photo(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    
    session = user_sessions.get(user_id, {})
    photo = update.message.photo[-1]  # Highest resolution
    
    if session.get("step") == "waiting_thumbnail":
        # Single upload - thumbnail
        file = await context.bot.get_file(photo.file_id)
        file_path = f"temp_thumb_{photo.file_id}.jpg"
        
        await file.download_to_drive(file_path)
        
        # Upload to Supabase
        book_data = session["book_data"]
        result = upload_book_to_supabase(
            book_data.get("title"),
            book_data.get("author"), 
            book_data.get("category"),
            book_data.get("description", ""),
            book_data["book_file_path"],
            file_path
        )
        
        # Cleanup
        cleanup_files([book_data["book_file_path"], file_path])
        
        if result["success"]:
            del user_sessions[user_id]
            await update.message.reply_text(
                f"✅ *Book Uploaded Successfully!*\n\n"
                f"• Title: {book_data['title']}\n"
                f"• Author: {book_data['author']}\n"
                f"• Category: {book_data['category']}\n"
                f"• Size: {result['file_size']} MB\n\n"
                f"View: {result['file_url']}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Upload failed: {result['error']}")
    
    elif session.get("step") == "bulk_waiting_thumbnails":
        # Bulk upload - thumbnails
        books = session["books"]
        current_thumb_index = len([b for b in books if "thumbnail_path" in b])
        
        if current_thumb_index < 5:
            file = await context.bot.get_file(photo.file_id)
            file_path = f"temp_thumb_bulk_{current_thumb_index}.jpg"
            
            await file.download_to_drive(file_path)
            books[current_thumb_index]["thumbnail_path"] = file_path
            
            thumbs_received = current_thumb_index + 1
            if thumbs_received < 5:
                await update.message.reply_text(
                    f"🖼️ Thumbnail {thumbs_received}/5 received!\n\n"
                    f"Send thumbnail {thumbs_received + 1}/5:"
                )
            else:
                # Upload all 5 books
                await update.message.reply_text("🚀 Uploading all 5 books to Supabase...")
                
                results = []
                for i, book in enumerate(books):
                    result = upload_book_to_supabase(
                        book["details"]["title"],
                        book["details"]["author"],
                        book["details"]["category"], 
                        book["details"].get("description", ""),
                        book["book_file_path"],
                        book["thumbnail_path"]
                    )
                    results.append(result)
                
                # Cleanup
                all_files = []
                for book in books:
                    all_files.extend([book["book_file_path"], book["thumbnail_path"]])
                cleanup_files(all_files)
                
                # Show results
                success_count = len([r for r in results if r["success"]])
                failed_count = 5 - success_count
                
                result_text = f"📊 *Bulk Upload Complete!*\n\n✅ Success: {success_count}\n❌ Failed: {failed_count}\n\n"
                
                for i, result in enumerate(results):
                    if result["success"]:
                        result_text += f"• {result['title']} ✅\n"
                    else:
                        result_text += f"• {result.get('title', f'Book {i+1}')} ❌\n"
                
                del user_sessions[user_id]
                await update.message.reply_text(result_text, parse_mode='Markdown')

# -----------------------
# Helper Functions
# -----------------------
def parse_book_details(text):
    """Parse book details from text"""
    lines = text.split('\n')
    details = {}
    
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            
            if key == 'title':
                details['title'] = value
            elif key == 'author':
                details['author'] = value  
            elif key == 'category':
                details['category'] = value
            elif key == 'description':
                details['description'] = value
    
    # Check required fields
    if all(k in details for k in ['title', 'author', 'category']):
        return details
    return None

def upload_book_to_supabase(title, author, category, description, book_file_path, thumbnail_path):
    """Upload book to Supabase"""
    try:
        uid = str(uuid.uuid4())
        book_name = f"books/{uid}_{os.path.basename(book_file_path)}"
        thumb_name = f"thumbnails/{uid}_{os.path.basename(thumbnail_path)}"
        
        # Read files
        with open(book_file_path, 'rb') as f:
            book_bytes = f.read()
        with open(thumbnail_path, 'rb') as f:
            thumb_bytes = f.read()
        
        # Upload to storage
        supabase.storage.from_(SUPABASE_BUCKET).upload(book_name, book_bytes)
        supabase.storage.from_(SUPABASE_BUCKET).upload(thumb_name, thumb_bytes)
        
        # Generate URLs
        book_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{book_name}"
        thumb_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{thumb_name}"
        file_size_mb = round(len(book_bytes) / (1024 * 1024), 2)
        
        # Insert into database
        insert_data = {
            "title": title,
            "author": author,
            "category": category,
            "description": description,
            "file_url": book_url,
            "thumbnail_url": thumb_url,
            "file_size": file_size_mb,
            "downloads": 0,
            "upload_date": datetime.utcnow().isoformat()
        }
        
        res = supabase.table("books").insert(insert_data).execute()
        
        if res.data:
            return {
                "success": True,
                "title": title,
                "file_url": book_url,
                "thumbnail_url": thumb_url,
                "file_size": file_size_mb
            }
        else:
            return {"success": False, "error": "Database insert failed"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_stats():
    """Get library statistics"""
    try:
        res = supabase.table("books").select("id,downloads,file_size").execute()
        rows = res.data or []
        total_books = len(rows)
        total_downloads = sum((r.get('downloads') or 0) for r in rows)
        total_size_mb = sum((r.get('file_size') or 0) for r in rows)
        
        return {
            "total_books": total_books,
            "total_downloads": total_downloads,
            "total_size": f"{round(total_size_mb, 2)} MB"
        }
    except Exception as e:
        return {"total_books": 0, "total_downloads": 0, "total_size": "0 MB"}

def cleanup_files(file_paths):
    """Cleanup temporary files"""
    for path in file_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except:
            pass

# -----------------------
# Main Bot Setup
# -----------------------
def main():
    """Start the bot"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("Please set it: export TELEGRAM_BOT_TOKEN='your_bot_token_here'")
        return
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Start bot
    print("🤖 Telegram Bot is running...")
    print("📚 Use /start command in Telegram to begin!")
    application.run_polling()

if __name__ == "__main__":
    main()