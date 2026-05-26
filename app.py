import os
import shutil
import time
import json
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, make_response, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 用于加密Cookie

# -------------------------- 配置管理 --------------------------
CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
    'upload_max_size': 1024 * 1024 * 1024,  # 单文件最大1GB
    'username': 'admin',
    'password_hash': generate_password_hash('admin123'),  # 默认账号admin，密码admin123
    'base_upload_folder': os.path.abspath('uploads')
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()
BASE_UPLOAD_FOLDER = config['base_upload_folder']
app.config['MAX_CONTENT_LENGTH'] = config['upload_max_size']

# 自动创建存储根目录
if not os.path.exists(BASE_UPLOAD_FOLDER):
    os.makedirs(BASE_UPLOAD_FOLDER)

# -------------------------- 登录鉴权装饰器 --------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({'code': -2, 'msg': '未登录'}), 401
        return f(*args, **kwargs)
    return decorated_function

# -------------------------- 核心工具函数 --------------------------
def get_safe_path(user_path):
    user_path = user_path.strip().strip('/').strip('\\')
    target_path = os.path.normpath(os.path.join(BASE_UPLOAD_FOLDER, user_path))
    if not target_path.startswith(BASE_UPLOAD_FOLDER):
        return None
    return target_path

def format_time(timestamp):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))

def format_size(bytes_num):
    if bytes_num == 0:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    idx = 0
    while bytes_num >= 1024 and idx < len(units)-1:
        bytes_num /= 1024
        idx += 1
    return f"{round(bytes_num, 2)} {units[idx]}"

# -------------------------- 页面路由 --------------------------
@app.route('/')
def index():
    if 'logged_in' in session:
        return render_template('index.html')
    return render_template('login.html')

# -------------------------- 登录接口 --------------------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    
    if username == config['username'] and check_password_hash(config['password_hash'], password):
        session['logged_in'] = True
        return jsonify({'code': 0, 'msg': '登录成功'})
    return jsonify({'code': -1, 'msg': '账号或密码错误'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('logged_in', None)
    return jsonify({'code': 0, 'msg': '退出成功'})

@app.route('/api/check_login', methods=['POST'])
def check_login():
    return jsonify({'code': 0, 'data': {'logged_in': 'logged_in' in session}})

# -------------------------- 配置接口 --------------------------
@app.route('/api/get_config', methods=['POST'])
@login_required
def get_config():
    return jsonify({
        'code': 0,
        'data': {
            'upload_max_size': config['upload_max_size'],
            'username': config['username']
        }
    })

@app.route('/api/save_config', methods=['POST'])
@login_required
def save_config_api():
    global config, BASE_UPLOAD_FOLDER
    data = request.json
    
    new_config = config.copy()
    if 'upload_max_size' in data:
        new_config['upload_max_size'] = data['upload_max_size']
    if 'username' in data:
        new_config['username'] = data['username']
    if 'password' in data and data['password']:
        new_config['password_hash'] = generate_password_hash(data['password'])
    
    save_config(new_config)
    config = new_config
    BASE_UPLOAD_FOLDER = config['base_upload_folder']
    app.config['MAX_CONTENT_LENGTH'] = config['upload_max_size']
    
    return jsonify({'code': 0, 'msg': '保存成功'})

# -------------------------- 核心文件管理接口（全加@login_required） --------------------------
@app.route('/api/list', methods=['POST'])
@login_required
def list_files():
    user_path = request.json.get('path', '')
    full_path = get_safe_path(user_path)
    
    if full_path is None:
        return jsonify({'code': -1, 'msg': '非法路径，禁止目录穿越'}), 403
    if not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '路径不存在'}), 404
    if not os.path.isdir(full_path):
        return jsonify({'code': -1, 'msg': '目标不是文件夹'}), 400
    
    file_list = []
    try:
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            stat_info = os.stat(item_path)
            is_dir = os.path.isdir(item_path)
            
            file_list.append({
                'name': item,
                'type': 'folder' if is_dir else 'file',
                'size': stat_info.st_size if not is_dir else 0,
                'size_format': format_size(stat_info.st_size) if not is_dir else '-',
                'mtime': format_time(stat_info.st_mtime),
                'ext': os.path.splitext(item)[1].lower() if not is_dir else ''
            })
        file_list.sort(key=lambda x: (x['type'] != 'folder', x['name'].lower()))
        return jsonify({'code': 0, 'data': file_list, 'msg': 'success'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'读取失败：{str(e)}'}), 500

@app.route('/api/mkdir', methods=['POST'])
@login_required
def create_folder():
    user_path = request.json.get('path', '')
    folder_name = secure_filename(request.json.get('name', ''))
    
    if not folder_name:
        return jsonify({'code': -1, 'msg': '文件夹名称不能为空'}), 400
    
    full_path = get_safe_path(user_path)
    if full_path is None:
        return jsonify({'code': -1, 'msg': '非法路径'}), 403
    
    target_path = os.path.join(full_path, folder_name)
    if os.path.exists(target_path):
        return jsonify({'code': -1, 'msg': '文件夹已存在'}), 400
    
    os.makedirs(target_path)
    return jsonify({'code': 0, 'msg': '创建成功'})

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    user_path = request.form.get('path', '')
    full_path = get_safe_path(user_path)
    
    if full_path is None:
        return jsonify({'code': -1, 'msg': '非法路径'}), 403
    if not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '路径不存在'}), 404
    
    if 'files' not in request.files:
        return jsonify({'code': -1, 'msg': '未选择文件'}), 400
    
    files = request.files.getlist('files')
    success_count = 0
    fail_list = []
    
    for file in files:
        if file.filename == '':
            continue
        filename = secure_filename(file.filename)
        save_path = os.path.join(full_path, filename)
        try:
            file.save(save_path)
            success_count += 1
        except Exception as e:
            fail_list.append(f"{filename}：{str(e)}")
    
    if success_count > 0:
        return jsonify({'code': 0, 'msg': f'成功上传{success_count}个文件', 'fail': fail_list})
    else:
        return jsonify({'code': -1, 'msg': '上传失败', 'fail': fail_list}), 500

@app.route('/api/download/<path:user_path>')
@login_required
def download_file(user_path):
    full_path = get_safe_path(user_path)
    if full_path is None or not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '文件不存在或路径非法'}), 404
    
    if os.path.isdir(full_path):
        return jsonify({'code': -1, 'msg': '暂不支持文件夹下载'}), 400
    
    directory, filename = os.path.split(full_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/api/delete', methods=['POST'])
@login_required
def delete_item():
    paths = request.json.get('paths', [])
    if not paths:
        return jsonify({'code': -1, 'msg': '未选择目标'}), 400
    
    success_count = 0
    fail_list = []
    
    for user_path in paths:
        full_path = get_safe_path(user_path)
        if full_path is None or not os.path.exists(full_path):
            fail_list.append(f"{user_path}：路径非法或不存在")
            continue
        
        try:
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            success_count += 1
        except Exception as e:
            fail_list.append(f"{user_path}：{str(e)}")
    
    return jsonify({
        'code': 0 if success_count > 0 else -1,
        'msg': f'成功删除{success_count}个项目',
        'fail': fail_list
    })

@app.route('/api/rename', methods=['POST'])
@login_required
def rename_item():
    user_path = request.json.get('path', '')
    new_name = secure_filename(request.json.get('new_name', ''))
    
    if not new_name:
        return jsonify({'code': -1, 'msg': '新名称不能为空'}), 400
    
    full_path = get_safe_path(user_path)
    if full_path is None or not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '路径非法或不存在'}), 404
    
    parent_dir = os.path.dirname(full_path)
    new_path = os.path.join(parent_dir, new_name)
    
    if os.path.exists(new_path):
        return jsonify({'code': -1, 'msg': '名称已存在'}), 400
    
    os.rename(full_path, new_path)
    return jsonify({'code': 0, 'msg': '重命名成功'})

@app.route('/api/move', methods=['POST'])
@login_required
def move_item():
    source_paths = request.json.get('source_paths', [])
    target_path = request.json.get('target_path', '')
    
    if not source_paths:
        return jsonify({'code': -1, 'msg': '未选择源文件'}), 400
    
    target_full_path = get_safe_path(target_path)
    if target_full_path is None or not os.path.exists(target_full_path):
        return jsonify({'code': -1, 'msg': '目标路径非法或不存在'}), 404
    
    success_count = 0
    fail_list = []
    
    for source_path in source_paths:
        source_full_path = get_safe_path(source_path)
        if source_full_path is None or not os.path.exists(source_full_path):
            fail_list.append(f"{source_path}：源文件不存在")
            continue
        
        filename = os.path.basename(source_full_path)
        dest_path = os.path.join(target_full_path, filename)
        
        if os.path.exists(dest_path):
            fail_list.append(f"{filename}：目标路径已存在同名文件")
            continue
        
        try:
            shutil.move(source_full_path, dest_path)
            success_count += 1
        except Exception as e:
            fail_list.append(f"{filename}：{str(e)}")
    
    return jsonify({
        'code': 0 if success_count > 0 else -1,
        'msg': f'成功移动{success_count}个项目',
        'fail': fail_list
    })

@app.route('/api/copy', methods=['POST'])
@login_required
def copy_item():
    source_paths = request.json.get('source_paths', [])
    target_path = request.json.get('target_path', '')
    
    if not source_paths:
        return jsonify({'code': -1, 'msg': '未选择源文件'}), 400
    
    target_full_path = get_safe_path(target_path)
    if target_full_path is None or not os.path.exists(target_full_path):
        return jsonify({'code': -1, 'msg': '目标路径非法或不存在'}), 404
    
    success_count = 0
    fail_list = []
    
    for source_path in source_paths:
        source_full_path = get_safe_path(source_path)
        if source_full_path is None or not os.path.exists(source_full_path):
            fail_list.append(f"{source_path}：源文件不存在")
            continue
        
        filename = os.path.basename(source_full_path)
        dest_path = os.path.join(target_full_path, filename)
        
        if os.path.exists(dest_path):
            fail_list.append(f"{filename}：目标路径已存在同名文件")
            continue
        
        try:
            if os.path.isdir(source_full_path):
                shutil.copytree(source_full_path, dest_path)
            else:
                shutil.copy2(source_full_path, dest_path)
            success_count += 1
        except Exception as e:
            fail_list.append(f"{filename}：{str(e)}")
    
    return jsonify({
        'code': 0 if success_count > 0 else -1,
        'msg': f'成功复制{success_count}个项目',
        'fail': fail_list
    })

@app.route('/api/read_file', methods=['POST'])
@login_required
def read_file():
    user_path = request.json.get('path', '')
    full_path = get_safe_path(user_path)
    
    if full_path is None or not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '文件不存在或路径非法'}), 404
    if os.path.isdir(full_path):
        return jsonify({'code': -1, 'msg': '不能读取文件夹'}), 400
    
    if os.path.getsize(full_path) > 10 * 1024 * 1024:
        return jsonify({'code': -1, 'msg': '文件超过10MB，不支持在线编辑'}), 400
    
    try:
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        content = ''
        for enc in encodings:
            try:
                with open(full_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        return jsonify({'code': 0, 'data': content, 'msg': '读取成功'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'读取失败：{str(e)}'}), 500

@app.route('/api/save_file', methods=['POST'])
@login_required
def save_file():
    user_path = request.json.get('path', '')
    content = request.json.get('content', '')
    
    full_path = get_safe_path(user_path)
    if full_path is None:
        return jsonify({'code': -1, 'msg': '路径非法'}), 403
    if os.path.isdir(full_path):
        return jsonify({'code': -1, 'msg': '不能保存到文件夹'}), 400
    
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'code': 0, 'msg': '保存成功'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'保存失败：{str(e)}'}), 500

@app.route('/api/dirtree', methods=['POST'])
@login_required
def get_dirtree():
    def scan_dir(path, root_path):
        tree = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                relative_path = os.path.relpath(item_path, root_path).replace('\\', '/')
                children = scan_dir(item_path, root_path)
                tree.append({
                    'name': item,
                    'path': relative_path,
                    'children': children
                })
        return tree
    
    try:
        # 新增：在最顶层包一层根目录节点
        root_tree = [{
            'name': '根目录/',
            'path': '',
            'children': scan_dir(BASE_UPLOAD_FOLDER, BASE_UPLOAD_FOLDER)
        }]
        return jsonify({'code': 0, 'data': root_tree, 'msg': 'success'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'获取目录树失败：{str(e)}'}), 500
@app.route('/api/create_file', methods=['POST'])
@login_required
def create_file():
    user_path = request.json.get('path', '')
    filename = secure_filename(request.json.get('filename', ''))
    
    if not filename:
        return jsonify({'code': -1, 'msg': '文件名不能为空'}), 400
    
    full_path = get_safe_path(user_path)
    if full_path is None:
        return jsonify({'code': -1, 'msg': '非法路径'}), 403
    if not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '路径不存在'}), 404
    
    target_file = os.path.join(full_path, filename)
    if os.path.exists(target_file):
        return jsonify({'code': -1, 'msg': '文件已存在'}), 400
    
    try:
        # 创建0字节空文件
        open(target_file, 'w', encoding='utf-8').close()
        return jsonify({'code': 0, 'msg': '创建成功'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'创建失败：{str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
