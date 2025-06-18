from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import re
import random
from urllib.parse import urlparse
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(filename):
    """Sanitize filenames to remove invalid characters"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)[:200]

def get_ydl_options():
    """Configure YouTube-DL options"""
    return {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'restrictfilenames': True,
        # REMOVED extractor_args that were limiting formats
        'age_limit': 0,
        'geo_bypass': True,
        'noplaylist': True,
    }

def is_valid_youtube_url(url):
    """Validate YouTube URLs"""
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        return any(domain in parsed.netloc.lower() 
                 for domain in ['youtube.com', 'youtu.be', 'm.youtube.com'])
    except:
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def preview():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400

    if not is_valid_youtube_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    ydl_opts = get_ydl_options()
    ydl_opts['extract_flat'] = False

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return jsonify({'error': 'Video unavailable'}), 400

            # FIXED: Properly formatted loop without comments
            formats = []
            for f in info.get('formats', []):
                # Include all formats except audio-only in video formats
                if f.get('vcodec') != 'none':
                    formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext', 'mp4'),
                        'height': f.get('height', 0),
                        'filesize': f.get('filesize'),
                        'vcodec': f.get('vcodec', 'none'),
                        'acodec': f.get('acodec', 'none'),
                        'format_note': f.get('format_note', ''),
                        'tbr': f.get('tbr', 0),
                    })
            
            # Also include audio-only formats
            audio_formats = []
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    audio_formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext', 'mp3'),
                        'height': 0,
                        'filesize': f.get('filesize'),
                        'vcodec': 'none',
                        'acodec': f.get('acodec', 'none'),
                        'format_note': 'Audio',
                        'tbr': f.get('tbr', 0),
                    })
            
            # Combine both lists
            formats.extend(audio_formats)
            
            # Get best thumbnail
            thumbnails = info.get('thumbnails', [])
            thumbnail = info.get('thumbnail', '')
            if thumbnails:
                # Get highest resolution thumbnail
                thumbnails.sort(key=lambda t: t.get('width', 0) * t.get('height', 0), reverse=True)
                thumbnail = thumbnails[0]['url']
            
            return jsonify({
                'title': sanitize_filename(info.get('title', 'Untitled')),
                'thumbnail': thumbnail,
                'duration': info.get('duration', 0),
                'formats': formats
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    url = request.json.get('url')
    format = request.json.get('format', '720p')
    format_id = request.json.get('format_id')
    
    if not url:
        return jsonify({'error': 'URL required'}), 400

    if not is_valid_youtube_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    ydl_opts = get_ydl_options()
    ydl_opts['outtmpl'] = os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s')

    # Format selection - FIXED: Proper format mapping
    if format_id:
        ydl_opts['format'] = format_id
    else:
        format_map = {
            '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]',
            '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]',
            '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480]',
            '360p': 'bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360]',
            'mp3': 'bestaudio/best'
        }
        ydl_opts['format'] = format_map.get(format, 'best[ext=mp4]')

    # Audio conversion
    if format == 'mp3':
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if format == 'mp3':
                filename = os.path.splitext(filename)[0] + '.mp3'
            
            if not os.path.exists(filename):
                return jsonify({'error': 'Download failed'}), 500
                
            return send_file(filename, as_attachment=True)
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Cleanup downloaded files"""
    try:
        for filename in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Replit-specific configuration
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)