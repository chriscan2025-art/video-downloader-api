from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=False)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def delete_file_later(path, delay=600):
    def _delete():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=_delete, daemon=True).start()

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "online"})

@app.route("/info", methods=["POST"])
def get_info():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        seen = set()
        for f in info.get("formats", []):
            height = f.get("height")
            ext = f.get("ext")
            vcodec = f.get("vcodec", "none")
            if height and vcodec != "none" and ext in ["mp4", "webm"]:
                label = f"{height}p ({ext})"
                if label not in seen:
                    seen.add(label)
                    formats.append({"format_id": f["format_id"], "label": label, "type": "video", "height": height, "ext": ext})

        formats.sort(key=lambda x: x.get("height", 0), reverse=True)
        formats.append({"format_id": "bestaudio", "label": "MP3 Audio Only", "type": "audio", "ext": "mp3"})

        return jsonify({
            "title": info.get("title", "Video"),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
            "platform": info.get("extractor_key", ""),
            "formats": formats[:10]
        })
    except Exception as e:
        return jsonify({"error": "Could not fetch video. Check URL and try again."}), 400

@app.route("/download", methods=["POST"])
def download_video():
    data = request.json
    url = data.get("url", "").strip()
    format_id = data.get("format_id", "best")
    is_audio = data.get("type", "video") == "audio"
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    file_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(DOWNLOAD_FOLDER, file_id)

    if is_audio:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_path + ".%(ext)s",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "quiet": True,
        }
    else:
        ydl_opts = {
            "format": f"{format_id}+bestaudio/best",
            "outtmpl": output_path + ".%(ext)s",
            "merge_output_format": "mp4",
            "quiet": True,
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        downloaded_file = None
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(file_id):
                downloaded_file = os.path.join(DOWNLOAD_FOLDER, f)
                break

        if not downloaded_file:
            return jsonify({"error": "Download failed"}), 500

        delete_file_later(downloaded_file)
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:50]
        ext = downloaded_file.split(".")[-1]

        return send_file(downloaded_file, as_attachment=True, download_name=f"{safe_title}.{ext}")
    except Exception as e:
        return jsonify({"error": "Download failed. Try another quality."}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
