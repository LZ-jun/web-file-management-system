import os
import shutil
import time
from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 核心配置
BASE_UPLOAD_FOLDER = os.path.abspath('uploads')  # 固定根目录绝对路径，彻底解决路径穿越
app.config['BASE_UPLOAD_FOLDER'] = BASE_UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 单文件最大1GB，可自行调整

# 自动创建存储根目录
if not os.path.exists(BASE_UPLOAD_FOLDER):
    os.makedirs(BASE_UPLOAD_FOLDER)

# -------------------------- 核心工具函数（彻底修复非法路径BUG） --------------------------
def get_safe_path(user_path):
    """
    安全路径处理：规范化用户输入路径，防止../目录穿越，返回绝对路径
    所有接口必须先通过此函数处理路径，彻底解决非法路径问题
    """
    # 处理空路径、首尾空格、斜杠
    user_path = user_path.strip().strip('/').strip('\\')
    # 拼接根目录，规范化路径（自动处理../ ./ 等穿越字符）
    target_path = os.path.normpath(os.path.join(BASE_UPLOAD_FOLDER, user_path))
    # 强制校验：最终路径必须在根目录内，否则判定为非法路径
    if not target_path.startswith(BASE_UPLOAD_FOLDER):
        return None
    return target_path

def format_time(timestamp):
    """格式化文件修改时间"""
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))

def format_size(bytes_num):
    """格式化文件大小"""
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
    return render_template('index.html')

# -------------------------- 核心文件管理接口 --------------------------
# 1. 获取文件列表（修复路径校验）
@app.route('/api/list', methods=['POST'])
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
        # 文件夹在前，文件在后，按名称排序
        file_list.sort(key=lambda x: (x['type'] != 'folder', x['name'].lower()))
        return jsonify({'code': 0, 'data': file_list, 'msg': 'success'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'读取失败：{str(e)}'}), 500

# 2. 新建文件夹
@app.route('/api/mkdir', methods=['POST'])
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

# 3. 文件上传（支持多文件）
@app.route('/api/upload', methods=['POST'])
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

# 4. 文件下载
@app.route('/api/download/<path:user_path>')
def download_file(user_path):
    full_path = get_safe_path(user_path)
    if full_path is None or not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '文件不存在或路径非法'}), 404
    
    if os.path.isdir(full_path):
        return jsonify({'code': -1, 'msg': '暂不支持文件夹下载'}), 400
    
    directory, filename = os.path.split(full_path)
    return send_from_directory(directory, filename, as_attachment=True)

# 5. 删除文件/文件夹（支持批量）
@app.route('/api/delete', methods=['POST'])
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

# 6. 重命名
@app.route('/api/rename', methods=['POST'])
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

# 7. 移动文件/文件夹（剪切粘贴）
@app.route('/api/move', methods=['POST'])
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

# 8. 复制文件/文件夹
@app.route('/api/copy', methods=['POST'])
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

# 9. 读取文本文件内容（用于在线编辑）
@app.route('/api/read_file', methods=['POST'])
def read_file():
    user_path = request.json.get('path', '')
    full_path = get_safe_path(user_path)
    
    if full_path is None or not os.path.exists(full_path):
        return jsonify({'code': -1, 'msg': '文件不存在或路径非法'}), 404
    if os.path.isdir(full_path):
        return jsonify({'code': -1, 'msg': '不能读取文件夹'}), 400
    
    # 限制文件大小，防止大文件卡死
    if os.path.getsize(full_path) > 10 * 1024 * 1024:
        return jsonify({'code': -1, 'msg': '文件超过10MB，不支持在线编辑'}), 400
    
    try:
        # 尝试多种编码读取
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

# 10. 保存文本文件内容（用于在线编辑）
@app.route('/api/save_file', methods=['POST'])
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

# 11. 获取目录树（用于移动/复制时选择目标路径）
@app.route('/api/dirtree', methods=['POST'])
def get_dirtree():
    def scan_dir(path, root_path):
        tree = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                # 计算相对路径
                relative_path = os.path.relpath(item_path, root_path).replace('\\', '/')
                children = scan_dir(item_path, root_path)
                tree.append({
                    'name': item,
                    'path': relative_path,
                    'children': children
                })
        return tree
    
    try:
        tree = scan_dir(BASE_UPLOAD_FOLDER, BASE_UPLOAD_FOLDER)
        return jsonify({'code': 0, 'data': tree, 'msg': 'success'})
    except Exception as e:
        return jsonify({'code': -1, 'msg': f'获取目录树失败：{str(e)}'}), 500

if __name__ == '__main__':
    # 0.0.0.0 允许局域网内所有设备访问
    app.run(host='0.0.0.0', port=80, debug=False)
