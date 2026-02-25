# Task 3: Очистка данных и расчет метрик в PostgreSQL

## Описание задачи
В данном задании выполнено подключение к базе данных через DBeaver. Проведена очистка сырых данных в таблице `user_logs` от некорректных символов (запятых), приведение типов данных к числовому формату и расчет агрегированных метрик.

## SQL-скрипт (data_modifire.sql)
Все этапы преобразования данных:

```sql
-- 1. Вывод 5 случайных строк из логов
SELECT * FROM user_logs ORDER BY RANDOM() LIMIT 5;

-- 2. Очистка данных: замена запятых на точки в колонке s_all_avg
UPDATE user_logs 
SET s_all_avg = REPLACE(s_all_avg, ',', '.') 
WHERE s_all_avg LIKE '%,%';

-- 3. Изменение типа данных колонки со строкового на числовой (REAL)
ALTER TABLE user_logs 
ALTER COLUMN s_all_avg TYPE REAL USING s_all_avg::REAL;

-- 4. Расчет среднего значения по очищенной колонке
SELECT AVG(s_all_avg) AS total_average_activity 
FROM user_logs;