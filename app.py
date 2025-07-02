import os
from flask import Flask, request, render_template, send_file, redirect, flash
from werkzeug.utils import secure_filename
import pandas as pd
from PIL import Image
from fpdf import FPDF
from docx import Document

app = Flask(__name__)
app.secret_key = "supersecretkey"

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {
    'csv': ['xlsx', 'txt'],
    'xlsx': ['csv', 'txt'],
    'png': ['jpg', 'pdf'],
    'jpg': ['png', 'pdf'],
    'docx': ['txt'],
}
BLOCKED_EXTENSIONS = ['exe', 'sh', 'bat', 'js']
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return '.' in filename and ext not in BLOCKED_EXTENSIONS

def get_possible_conversions(ext):
    return ALLOWED_EXTENSIONS.get(ext, [])

def convert_file(filepath, original_ext, target_ext):
    try:
        if original_ext == 'csv' and target_ext == 'xlsx':
            df = pd.read_csv(filepath)
            new_path = filepath.replace('.csv', '.xlsx')
            df.to_excel(new_path, index=False)
            return new_path

        elif original_ext == 'xlsx' and target_ext == 'csv':
            df = pd.read_excel(filepath)
            new_path = filepath.replace('.xlsx', '.csv')
            df.to_csv(new_path, index=False)
            return new_path

        elif original_ext == 'png' and target_ext == 'jpg':
            img = Image.open(filepath)
            new_path = filepath.replace('.png', '.jpg')
            img.convert('RGB').save(new_path)
            return new_path

        elif original_ext == 'jpg' and target_ext == 'png':
            img = Image.open(filepath)
            new_path = filepath.replace('.jpg', '.png')
            img.save(new_path)
            return new_path

        elif original_ext == 'png' and target_ext == 'pdf':
            img = Image.open(filepath)
            new_path = filepath.replace('.png', '.pdf')
            img.convert('RGB').save(new_path, "PDF", resolution=100.0)
            return new_path

        elif original_ext == 'docx' and target_ext == 'txt':
            doc = Document(filepath)
            text = "\n".join([p.text for p in doc.paragraphs])
            new_path = filepath.replace('.docx', '.txt')
            with open(new_path, 'w', encoding='utf-8') as f:
                f.write(text)
            return new_path

        elif original_ext == 'csv' and target_ext == 'txt':
            df = pd.read_csv(filepath)
            new_path = filepath.replace('.csv', '.txt')
            df.to_string(open(new_path, 'w', encoding='utf-8'), index=False)
            return new_path

        elif original_ext == 'xlsx' and target_ext == 'txt':
            df = pd.read_excel(filepath)
            new_path = filepath.replace('.xlsx', '.txt')
            df.to_string(open(new_path, 'w', encoding='utf-8'), index=False)
            return new_path

        else:
            return None
    except Exception as e:
        print(f"[ERROR] 변환 중 오류 발생: {str(e)}")
        return f"__ERROR__:{str(e)}"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('파일이 없습니다.')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('선택된 파일이 없습니다.')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            ext = filename.rsplit('.', 1)[-1].lower()
            possible_targets = get_possible_conversions(ext)

            if not possible_targets:
                flash(f'이 확장자({ext})는 변환을 지원하지 않습니다.')
                return redirect(request.url)

            target_ext = request.form.get("target_ext")
            if target_ext not in possible_targets:
                flash(f'선택한 변환 확장자({target_ext})는 사용할 수 없습니다.')
                return redirect(request.url)

            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)

            result_path = convert_file(save_path, ext, target_ext)
            if result_path and not str(result_path).startswith("__ERROR__"):
                return send_file(result_path, as_attachment=True)
            else:
                error_msg = result_path.split("__ERROR__:")[-1] if result_path else "알 수 없는 오류"
                flash(f'변환 실패: {error_msg}')
                return redirect(request.url)
        else:
            flash('허용되지 않는 파일 형식입니다.')
            return redirect(request.url)

    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
