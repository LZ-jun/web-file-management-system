# 远程存储管理系统

一个基于 Flask 的轻量级文件管理系统，提供简洁的 Web 界面进行文件和文件夹的管理操作。

## 功能特性

- **身份认证**：安全的登录系统，使用 SHA256 哈希和挑战响应机制
- **文件管理**：
  - 文件上传/下载
  - 文件夹创建/删除
  - 文件重命名
  - 文件/文件夹复制和移动
  - 批量操作（批量删除）
- **在线编辑**：支持文本文件在线编辑（10MB 以内）
- **文件预览**：支持图片、视频、音频和文本文件预览
- **目录树**：直观的目录树导航
- **文件分享**：支持创建临时或永久分享链接，无需登录即可访问下载
- **系统设置**：可修改账号、密码、上传文件大小限制和分享有效期
- **安全机制**：防止目录穿越攻击，会话超时保护

## 快速开始

### 环境要求

- Python 3.x
- Flask

### 安装依赖

```bash
pip install flask
```

### 运行项目

```bash
python app.py
```

默认运行在 `http://0.0.0.0:80`

### 默认账号

- 账号：`admin`
- 密码：`admin123`

## 项目结构

```
/workspace/
├── app.py              # Flask 后端应用
├── templates/
│   ├── index.html      # 主界面
│   ├── login.html      # 登录页面
│   └── share.html      # 分享页面
├── uploads/            # 上传文件存储目录（自动创建）
├── config.json         # 系统配置文件（自动生成）
└── shares.json         # 分享链接数据（自动生成）
```

## 配置说明

系统配置存储在 `config.json` 文件中（首次运行自动生成）：

```json
{
  "upload_max_size": 1073741824,  // 最大上传大小（字节，默认 1GB）
  "username": "admin",            // 登录账号
  "password": "sha256_hash",      // 密码的 SHA256 哈希
  "base_upload_folder": "/workspace/uploads",  // 上传目录
  "share_expire_minutes": 30      // 分享有效期（分钟，0 表示永久）
}
```

## API 接口

### 认证接口

- `POST /api/get_challenge` - 获取登录挑战值
- `POST /api/login` - 用户登录
- `POST /api/logout` - 用户登出
- `POST /api/check_login` - 检查登录状态

### 文件管理接口

- `POST /api/list` - 列出目录内容
- `POST /api/dirtree` - 获取目录树结构
- `POST /api/mkdir` - 创建文件夹
- `POST /api/create_file` - 创建空文件
- `POST /api/upload` - 上传文件
- `GET /api/download/<path>` - 下载文件
- `POST /api/delete` - 删除文件/文件夹
- `POST /api/rename` - 重命名
- `POST /api/move` - 移动文件/文件夹
- `POST /api/copy` - 复制文件/文件夹
- `POST /api/read_file` - 读取文件内容
- `POST /api/save_file` - 保存文件内容

### 配置接口

- `POST /api/get_config` - 获取系统配置
- `POST /api/save_config` - 保存系统配置

### 分享接口

- `POST /api/create_share` - 创建文件分享链接
- `GET /share/<share_id>` - 访问分享页面
- `GET /share/download/<share_id>` - 下载分享的文件

## 安全特性

1. **密码保护**：密码使用 SHA256 哈希存储
2. **挑战响应**：登录使用随机 salt 和时间戳防止重放攻击
3. **会话管理**：默认 5 分钟会话超时
4. **路径安全**：防止目录穿越攻击
5. **HTTPOnly Cookie**：防止 XSS 攻击窃取 Cookie
6. **SameSite Cookie**：防止 CSRF 攻击

## 许可证

MIT License
