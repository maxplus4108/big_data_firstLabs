-- init.sql
-- Этот файл выполняется только один раз при первом создании volume PostgreSQL.


-- Схема public нужна для сырых данных:
-- owners, cars, policies, fines
CREATE SCHEMA IF NOT EXISTS public;

-- Схема mart нужна для аналитических витрин:
-- owner_violations, fine_stats
CREATE SCHEMA IF NOT EXISTS mart;