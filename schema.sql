-- 用户表 schema
-- 文件：schema.sql
-- 位置：/Users/leach/person/AgentHarness/schema.sql

CREATE TABLE IF NOT EXISTS `users` (
    `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键 ID',
    `username`      VARCHAR(50)     NOT NULL                COMMENT '登录用户名',
    `email`         VARCHAR(255)    NOT NULL                COMMENT '邮箱地址',
    `password_hash` VARCHAR(255)    NOT NULL                COMMENT '加密后的密码哈希（不存明文）',
    `display_name`  VARCHAR(100)    DEFAULT NULL            COMMENT '展示昵称',
    `status`        TINYINT         NOT NULL DEFAULT 1      COMMENT '状态：1=正常，0=禁用',
    `created_at`    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_users_username` (`username`),
    UNIQUE KEY `uk_users_email` (`email`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = '用户表';
