-- 1. Вывод 5 случайных строк из логов
SELECT * FROM user_logs ORDER BY RANDOM() LIMIT 5;

-- 2. Очистка данных: замена запятых на точки в колонке s_all_avg
UPDATE user_logs 
SET s_all_avg = REPLACE(s_all_avg, ',', '.') 
WHERE s_all_avg LIKE '%,%';


UPDATE user_logs 
SET 
    s_course_viewed_avg = REPLACE(s_course_viewed_avg::text, ',', '.'),
    s_q_attempt_viewed_avg = REPLACE(s_q_attempt_viewed_avg::text, ',', '.'),
    s_a_course_module_viewed_avg = REPLACE(s_a_course_module_viewed_avg::text, ',', '.'),
    s_a_submission_status_viewed_avg = REPLACE(s_a_submission_status_viewed_avg::text, ',', '.')
WHERE 
    s_course_viewed_avg::text LIKE '%,%' OR 
    s_q_attempt_viewed_avg::text LIKE '%,%' OR 
    s_a_course_module_viewed_avg::text LIKE '%,%' OR 
    s_a_submission_status_viewed_avg::text LIKE '%,%';


-- 3. Изменение типа данных колонки со строкового на числовой (REAL)
ALTER TABLE user_logs 
ALTER COLUMN s_all_avg TYPE REAL USING s_all_avg::REAL;

ALTER TABLE user_logs 
    ALTER COLUMN s_course_viewed_avg TYPE REAL USING NULLIF(s_course_viewed_avg::text, '')::REAL,
    ALTER COLUMN s_q_attempt_viewed_avg TYPE REAL USING NULLIF(s_q_attempt_viewed_avg::text, '')::REAL,
    ALTER COLUMN s_a_course_module_viewed_avg TYPE REAL USING NULLIF(s_a_course_module_viewed_avg::text, '')::REAL,
    ALTER COLUMN s_a_submission_status_viewed_avg TYPE REAL USING NULLIF(s_a_submission_status_viewed_avg::text, '')::REAL;

-- 4. Расчет среднего значения по очищенной колонке
SELECT AVG(s_all_avg) AS total_average_activity 
FROM user_logs;