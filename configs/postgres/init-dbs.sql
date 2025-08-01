-- 这个脚本将在 PostgreSQL 容器首次启动时自动执行

-- 创建供 Authentik 使用的数据库
CREATE DATABASE authentik_db;

-- 将这个新数据库的所有权限，赋予我们已有的用户 (该用户由 .env 中的 POSTGRES_USER 定义)
GRANT ALL PRIVILEGES ON DATABASE authentik_db TO "visify_ssw_user";