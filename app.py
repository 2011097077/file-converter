import os
import csv
import datetime
import traceback
from flask import Flask, request, send_file, jsonify, render_template_string
from werkzeug.utils import secure_filename
from PIL import Image
from docx import Document
import pandas as pd
import magic  # pip install python-magic-bin

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

LOG_FILE = 'conversion_logs.csv'

ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'pdf',
    'doc', 'docx', 'odt', 'rtf', 'txt',
    'xls', 'xlsx', 'csv',
    'ppt', 'pptx',
    'hwp', 'md', 'xml'
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB 제한

EXTENSION_MAP = {
    'jpg': ['pdf', 'png'],
    'jpeg': ['pdf', 'png'],
    'png': ['pdf', 'jpg'],
    'pdf': ['jpg'],
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

def log_conversion(filename, from_ext, to_ext):
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([datetime.datetime.now(), filename, from_ext, to_ext])

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
        'xlsx': [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
            'application/octet-stream'
        ],
        'csv': [
            'text/csv',
            'application/csv',
            'application/vnd.ms-excel',
            'text/plain'
        ],
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

# 변환 함수들
def convert_csv_to_xlsx(input_path, output_path):
    try:
        df = pd.read_csv(input_path, encoding='utf-8')
        df.to_excel(output_path, index=False)
    except Exception as e:
        print("[ERROR] CSV→XLSX 실패:", e)
        traceback.print_exc()
        raise

def convert_xlsx_to_csv(input_path, output_path):
    try:
        df = pd.read_excel(input_path)
        df.to_csv(output_path, index=False)
    except Exception as e:
        print("[ERROR] XLSX→CSV 실패:", e)
        traceback.print_exc()
        raise

def convert_image_to_pdf(input_path, output_path):
    try:
        img = Image.open(input_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(output_path, "PDF")
    except Exception as e:
        print("[ERROR] 이미지→PDF 실패:", e)
        traceback.print_exc()
        raise

def convert_image_to_jpg(input_path, output_path):
    try:
        img = Image.open(input_path)
        rgb_img = img.convert('RGB')
        rgb_img.save(output_path, 'JPEG')
    except Exception as e:
        print("[ERROR] 이미지→JPG 실패:", e)
        traceback.print_exc()
        raise

def convert_docx_to_txt(input_path, output_path):
    try:
        doc = Document(input_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception as e:
        print("[ERROR] DOCX→TXT 실패:", e)
        traceback.print_exc()
        raise

# 등록
CONVERSION_FUNCTIONS = {
    ('csv', 'xlsx'): convert_csv_to_xlsx,
    ('xlsx', 'csv'): convert_xlsx_to_csv,
    ('docx', 'txt'): convert_docx_to_txt,
    ('jpg', 'pdf'): convert_image_to_pdf,
    ('jpeg', 'pdf'): convert_image_to_pdf,
    ('png', 'pdf'): convert_image_to_pdf,
    ('png', 'jpg'): convert_image_to_jpg,
}

# HTML UI
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>파일 변환기</title>
  <style>
    body {
      background: #e6f2fb;
      font-family: Arial, sans-serif;
      max-width: 600px;
      margin: 50px auto;
      padding: 20px;
      border-radius: 10px;
      box-shadow: 0 0 20px rgba(0,0,0,0.1);
    }
    h2 { color: #2c3e50; text-align: center; }
    label, select, input { display: block; margin: 15px 0; width: 100%; }
    button {
      background: #3498db;
      color: white;
      padding: 12px;
      width: 100%;
      font-size: 18px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
    }
    button:hover { background: #2980b9; }
    #errorMsg {
      color: red;
      font-weight: bold;
      margin-top: 15px;
      text-align: center;
    }
  </style>
</head>
<body>
  <h2>파일 변환기</h2>
  <form id="uploadForm">
    <label>파일 선택:</label>
    <input type="file" name="file" id="fileInput" required />

    <label>원본 확장자: <span id="extLabel">알 수 없음</span></label>

    <label>변환할 형식 선택:</label>
    <select name="target_ext" id="targetSelect" required>
      <option value="">-- 파일 먼저 선택하세요 --</option>
    </select>

    <button type="submit">변환 후 다운로드</button>
  </form>

  <div id="errorMsg"></div>

  <script>
    const fileInput = document.getElementById('fileInput');
    const extLabel = document.getElementById('extLabel');
    const targetSelect = document.getElementById('targetSelect');
    const form = document.getElementById('uploadForm');
    const errorMsg = document.getElementById('errorMsg');

    fileInput.addEventListener('change', () => {
      errorMsg.textContent = '';
      const file = fileInput.files[0];
      if (!file) return;

      const ext = file.name.split('.').pop().toLowerCase();
      extLabel.textContent = ext;

      fetch(`/get-targets?ext=${ext}`)
        .then(res => res.json())
        .then(data => {
          targetSelect.innerHTML = '';
          if (data.length === 0) {
            targetSelect.innerHTML = '<option value="">지원 안 됨</option>';
          } else {
            data.forEach(e => {
              const opt = document.createElement('option');
              opt.value = e;
              opt.textContent = '.' + e;
              targetSelect.appendChild(opt);
            });
          }
        });
    });

    form.addEventListener('submit', e => {
      e.preventDefault();
      errorMsg.textContent = '';

      const file = fileInput.files[0];
      const ext = targetSelect.value;
      if (!file || !ext) {
        errorMsg.textContent = '파일과 변환 형식을 선택해주세요.';
        return;
      }

      const formData = new FormData();
      formData.append('file', file);
      formData.append('target_ext', ext);

      fetch('/convert', {
        method: 'POST',
        body: formData
      })
      .then(async res => {
        if (!res.ok) {
          const text = await res.text();
          errorMsg.textContent = `변환 실패: ${text}`;
          throw new Error(text);
        }
        return res.blob();
      })
      .then(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = file.name.split('.')[0] + '.' + ext;
        a.click();
      })
      .catch(err => {
        console.error(err);
      });
    });
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

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

    filename = secure_filename(file.filename)
    src_ext = filename.rsplit('.', 1)[-1].lower()
    print(f"[INFO] 요청 파일명: {filename}, 원본 확장자: {src_ext}, 목표 확장자: {target_ext}")

    if src_ext not in ALLOWED_EXTENSIONS:
        return "지원되지 않는 파일 형식입니다.", 400

    if not allowed_file_mime(file.stream, filename):
        return "파일 내용과 확장자가 일치하지 않습니다.", 400

    src_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(src_path)

    if (src_ext, target_ext) not in CONVERSION_FUNCTIONS:
        return f"변환 불가: {src_ext} → {target_ext} 변환 기능이 없습니다.", 400

    output_filename = os.path.splitext(filename)[0] + '.' + target_ext
    output_path = os.path.join(UPLOAD_FOLDER, output_filename)

    try:
        CONVERSION_FUNCTIONS[(src_ext, target_ext)](src_path, output_path)
        log_conversion(filename, src_ext, target_ext)
        return send_file(output_path, as_attachment=True)
    except Exception as e:
        error_detail = str(e)
        print("[ERROR] 변환 중 예외 발생:", error_detail)
        traceback.print_exc()
        return f"변환 실패: {error_detail}", 500

if __name__ == '__main__':
    app.run(debug=True)
