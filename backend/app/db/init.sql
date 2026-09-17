-- 由 MySQL 容器首次启动执行：创建只读账号给 MySQL MCP Server 使用
CREATE USER IF NOT EXISTS 'readonly'@'%' IDENTIFIED BY 'readonly';
GRANT SELECT ON copilot.* TO 'readonly'@'%';
FLUSH PRIVILEGES;
