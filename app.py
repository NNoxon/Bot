from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
import os

# =========================
# ENV VARIABLES (RENDER)
# =========================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# =========================
# APP
# =========================
app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return {"status": "OceanBooks backend running ✅"}

# =========================
# AUTH
# =========================
@app.route("/api/register", methods=["POST"])
def register():
    data = request.json

    auth = supabase.auth.sign_up({
        "email": data["email"],
        "password": data["password"]
    })

    supabase.table("profiles").insert({
        "id": auth.user.id,
        "name": data["name"],
        "role": "user"
    }).execute()

    return jsonify({"success": True})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json

    auth = supabase.auth.sign_in_with_password({
        "email": data["email"],
        "password": data["password"]
    })

    return jsonify({
        "user_id": auth.user.id,
        "access_token": auth.session.access_token
    })

# =========================
# BOOKS
# =========================
@app.route("/api/books", methods=["GET"])
def get_books():
    books = supabase.table("books").select("*").execute()
    return jsonify(books.data)

# =========================
# DOWNLOAD TRACK
# =========================
@app.route("/api/download", methods=["POST"])
def download():
    data = request.json

    supabase.table("downloads").insert({
        "user_id": data["user_id"],
        "book_id": data["book_id"]
    }).execute()

    book = supabase.table("books") \
        .select("gdrive_link") \
        .eq("id", data["book_id"]) \
        .single() \
        .execute()

    return jsonify({"link": book.data["gdrive_link"]})

# =========================
# ADMIN – UPLOAD BOOK
# =========================
@app.route("/api/admin/upload-book", methods=["POST"])
def upload_book():
    data = request.json

    supabase.table("books").insert({
        "name": data["name"],
        "author": data["author"],
        "class": data["class"],
        "thumbnail": data["thumbnail"],
        "gdrive_link": data["gdrive_link"],
        "trending": data.get("trending", False)
    }).execute()

    return jsonify({"success": True})

# =========================
# RENDER ENTRY POINT
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)