import os
import uuid
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from supabase import create_client

# Config
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_IDS = [8464611503]  # Your Telegram ID

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
user_sessions = {}

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user_sessions[user_id] = {"step": "waiting_title", "books": []}
    await update.message.reply_text(
        "📚 *Book Upload Bot*\n\n"
        "Send book details in format:\n"
        "Title: Book Name\n"
        "Author: Author Name\n"
        "Category: Category\n\n"
        "You can upload 5-6 books at once!",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    
    session = user_sessions.get(user_id, {})
    text = update.message.text
    
    if session.get("step") == "waiting_title":
        # Parse book details
        try:
            lines = text.split('\n')
            details = {}
            for line in lines:
                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip().lower()
                    details[key] = val.strip()
            
            if 'title' in details and 'author' in details and 'category' in details:
                session["books"].append({
                    "details": details,
                    "step": "waiting_file"
                })
                
                count = len(session["books"])
                if count < 6:
                    await update.message.reply_text(
                        f"✅ Book {count} saved!\n"
                        f"Send details for book {count + 1} or send FILE for book {count}"
                    )
                else:
                    session["step"] = "waiting_files"
                    await update.message.reply_text(
                        "📚 All 6 books saved! Now send all BOOK FILES one by one."
                    )
            else:
                await update.message.reply_text("❌ Format: Title: ...\\nAuthor: ...\\nCategory: ...")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

async def handle_document(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    
    session = user_sessions.get(user_id, {})
    document = update.message.document
    
    if session.get("step") in ["waiting_files", "waiting_thumbnails"]:
        books = session["books"]
        
        # Find first book that needs file/thumbnail
        current_index = 0
        for i, book in enumerate(books):
            if session["step"] == "waiting_files" and "file_path" not in book:
                current_index = i
                break
            elif session["step"] == "waiting_thumbnails" and "thumb_path" not in book:
                current_index = i
                break
        
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{document.file_name}"
        await file.download_to_drive(file_path)
        
        if session["step"] == "waiting_files":
            books[current_index]["file_path"] = file_path
            files_done = len([b for b in books if "file_path" in b])
            
            if files_done < len(books):
                await update.message.reply_text(f"📁 File {files_done}/{len(books)} received! Send next file.")
            else:
                session["step"] = "waiting_thumbnails"
                await update.message.reply_text("✅ All files received! Now send THUMBNAILS one by one.")
        
        elif session["step"] == "waiting_thumbnails":
            books[current_index]["thumb_path"] = file_path
            thumbs_done = len([b for b in books if "thumb_path" in b])
            
            if thumbs_done < len(books):
                await update.message.reply_text(f"🖼️ Thumbnail {thumbs_done}/{len(books)} received! Send next thumbnail.")
            else:
                # Upload all books to Supabase
                await update.message.reply_text("🚀 Uploading all books...")
                
                success_count = 0
                for book in books:
                    try:
                        # Upload to Supabase
                        uid = str(uuid.uuid4())
                        book_name = f"books/{uid}_{os.path.basename(book['file_path'])}"
                        thumb_name = f"thumbnails/{uid}_{os.path.basename(book['thumb_path'])}"
                        
                        # Read and upload files
                        with open(book["file_path"], 'rb') as f:
                            book_bytes = f.read()
                        with open(book["thumb_path"], 'rb') as f:
                            thumb_bytes = f.read()
                        
                        supabase.storage.from_("uploads").upload(book_name, book_bytes)
                        supabase.storage.from_("uploads").upload(thumb_name, thumb_bytes)
                        
                        # Database entry
                        book_url = f"{SUPABASE_URL}/storage/v1/object/public/uploads/{book_name}"
                        thumb_url = f"{SUPABASE_URL}/storage/v1/object/public/uploads/{thumb_name}"
                        
                        supabase.table("books").insert({
                            "title": book["details"]["title"],
                            "author": book["details"]["author"],
                            "category": book["details"]["category"],
                            "file_url": book_url,
                            "thumbnail_url": thumb_url,
                            "file_size": round(len(book_bytes) / (1024 * 1024), 2),
                            "downloads": 0
                        }).execute()
                        
                        success_count += 1
                        
                        # Cleanup
                        os.remove(book["file_path"])
                        os.remove(book["thumb_path"])
                        
                    except Exception as e:
                        print(f"Upload error: {e}")
                
                del user_sessions[user_id]
                await update.message.reply_text(f"✅ {success_count}/{len(books)} books uploaded successfully!")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("🤖 Bot started!")
    application.run_polling()

if __name__ == '__main__':
    main()