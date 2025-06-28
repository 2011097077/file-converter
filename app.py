import os
import csv
import datetime
import traceback
import uuid
import time
from flask import Flask, request, send_file, jsonify, render_template
from werkzeug.utils import secure_filename
from PIL import Image
from docx import Document
import pandas as pd
import magic
import fitz  # PyMuPDF
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# === 설정 ===
UPLOAD_FOLDER = 'uploads'
LOG_FILE = 'conversion_logs.csv'
GOOGLE_CREDENTIALS_FILE = 'credentials.json'  # 서비스 계정 키 파일
GOOGLE_FOLDER_ID = '1GV7VOGpamzVwcflXSbXS9083Ydt2d4yV'  # Google Drive 폴더 ID

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def cleanup_old_files():
    now = time.time()
    for filename in os.listdir(UPLOAD_FOLDER):
        path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(path) and now - os.path.getmtime(path) > 86400:
            os.remove(path)
cleanup_old_files()

ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'pdf',
    'doc', 'docx', 'odt', 'rtf', 'txt',
    'xls', 'xlsx', 'csv',
    'ppt', 'pptx',
    'hwp', 'md', 'xml'
}

EXTENSION_MAP = {
    'jpg': ['pdf', 'png'],
    'jpeg': ['pdf', 'png'],
    'png': ['pdf', 'jpg'],
    'pdf': ['txt'],
    'doc': ['pdf', 'txt'],
    'docx': ['pdf', 'txt'],
    'odt': ['pdf', 'txt'],
    'rtf': ['pdf', 'txt'],
    'txt': ['pdf'],
    'xls': ['csv', 'pdf'],
    'xlsx': ['csv'],
    'csv': ['xlsx'],
    'ppt': ['pdf'],
    'pptx': ['pdf'],
    'hwp': ['pdf'],
    'md': ['pdf', 'txt'],
    'xml': ['pdf', 'txt'],
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

# === Google Drive 업로드 ===
def upload_to_drive(filepath, filename, folder_id=None):
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=['https://www.googleapis.com/auth/drive.file']
    )
    service = build('drive', 'v3', credentials=credentials)
    file_metadata = {'name': filename}
    if folder_id:
        file_metadata['parents'] = [folder_id]
    media = MediaFileUpload(filepath, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return file.get('webViewLink')

# === MIME 검사 ===
def allowed_file_mime(file_stream, filename):
    allowed_mimes = {
        'jpg': ['image/jpeg'],
        'jpeg': ['image/jpeg'],
        'png': ['image/png'],
        'pdf': ['application/pdf'],
        'doc': ['application/msword'],
        'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
        'odt': ['application/vnd.oasis.opendocument.text'],
        'rtf': ['application/rtf', 'text/rtf'],
        'txt': ['text/plain'],
        'xls': ['application/vnd.ms-excel'],
        'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel', 'application/octet-stream'],
        'csv': ['text/csv', 'application/csv', 'application/vnd.ms-excel', 'text/plain'],
        'ppt': ['application/vnd.ms-powerpoint'],
        'pptx': ['application/vnd.openxmlformats-officedocument.presentationml.presentation'],
        'hwp': ['application/x-hwp', 'application/octet-stream'],
        'md': ['text/markdown', 'text/plain'],
        'xml': ['application/xml', 'text/xml'],
    }
    ext = filename.rsplit('.', 1)[-1].lower()
    file_stream.seek(0)
    mime = magic.from_buffer(file_stream.read(2048), mime=True)
    file_stream.seek(0)
    return mime in allowed_mimes.get(ext, [])

# === 변환 함수 ===
def convert_csv_to_xlsx(input_path, output_path):
    pd.read_csv(input_path, encoding='utf-8').to_excel(output_path, index=False)

def convert_xlsx_to_csv(input_path, output_path):
    pd.read_excel(input_path).to_csv(output_path, index=False)

def convert_image_to_pdf(input_path, output_path):
    img = Image.open(input_path)
    img.convert('RGB').save(output_path, "PDF")

def convert_image_to_jpg(input_path, output_path):
    img = Image.open(input_path)
    img.convert('RGB').save(output_path, 'JPEG')

def convert_docx_to_txt(input_path, output_path):
    doc = Document(input_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join([p.text for p in doc.paragraphs]))

def convert_pdf_to_txt(input_path, output_path):
    doc = fitz.open(input_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        for page in doc:
            f.write(page.get_text())

CONVERSION_FUNCTIONS = {
    ('csv', 'xlsx'): convert_csv_to_xlsx,
    ('xlsx', 'csv'): convert_xlsx_to_csv,
    ('docx', 'txt'): convert_docx_to_txt,
    ('jpg', 'pdf'): convert_image_to_pdf,
    ('jpeg', 'pdf'): convert_image_to_pdf,
    ('png', 'pdf'): convert_image_to_pdf,
    ('png', 'jpg'): convert_image_to_jpg,
    ('pdf', 'txt'): convert_pdf_to_txt,
}

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/get-targets')
def get_targets():
    ext = request.args.get('ext', '').lower()
    return jsonify(EXTENSION_MAP.get(ext, []))

@app.route('/convert', methods=['POST'])
def convert():
    file = request.files.get('file')
    target_ext = request.form.get('target_ext', '').lower()

    if not file or target_ext == '':
        return "파일과 변환 형식을 모두 선택해주세요.", 400

    orig_filename = secure_filename(file.filename)
    src_ext = orig_filename.rsplit('.', 1)[-1].lower()

    if src_ext not in ALLOWED_EXTENSIONS:
        return "지원되지 않는 파일 형식입니다.", 400

    if not allowed_file_mime(file.stream, orig_filename):
        return "파일 내용과 확장자가 일치하지 않습니다.", 400

    unique_id = uuid.uuid4().hex
    filename = f"{os.path.splitext(orig_filename)[0]}_{unique_id}.{src_ext}"
    src_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(src_path)

    # Google Drive 업로드
    try:
        drive_url = upload_to_drive(src_path, filename, folder_id=GOOGLE_FOLDER_ID)
    except Exception as e:
        drive_url = None
        print("[Drive 업로드 실패]", e)

    if (src_ext, target_ext) not in CONVERSION_FUNCTIONS:
        return f"변환 불가: {src_ext} → {target_ext} 변환 기능이 없습니다.", 400

    output_filename = f"{os.path.splitext(orig_filename)[0]}_{unique_id}.{target_ext}"
    output_path = os.path.join(UPLOAD_FOLDER, output_filename)

    try:
        CONVERSION_FUNCTIONS[(src_ext, target_ext)](src_path, output_path)
        if target_ext in ['txt', 'csv']:
            with open(output_path, encoding='utf-8') as f:
                content = f.read(3000)
            return jsonify({
                'preview': content,
                'download_url': f"/download/{output_filename}",
                'drive_url': drive_url
            })
        return send_file(output_path, as_attachment=True)
    except Exception as e:
        print("[ERROR] 변환 실패:", str(e))
        traceback.print_exc()
        return f"변환 실패: {str(e)}", 500

@app.route('/download/<filename>')
def download_file(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "파일이 존재하지 않습니다.", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
