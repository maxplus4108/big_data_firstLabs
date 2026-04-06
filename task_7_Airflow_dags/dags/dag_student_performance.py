import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import psycopg2

# Импортируем модули Airflow (это новые библиотеки для тебя)
from airflow import DAG
from airflow.operators.python import PythonOperator

# Загружаем переменные из .env файла
load_dotenv()


# Подключение к бд

def connect_to_db():

    #Создает подключение к базе 'Plusnin'. См Dbeaver

    try:
        connection = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        connection.autocommit = False
        return connection
    except Exception as error:
        print(f"Ошибка подключения: {error}")
        raise # В Airflow обязательно нужно вызывать raise при ошибке, чтобы таск загорелся красным (Failed)




def init_data_mart_schema():
    conn = connect_to_db()
    try:
        queries = """
        CREATE SCHEMA IF NOT EXISTS dmr;
        CREATE TABLE IF NOT EXISTS dmr.analytics_student_performance (
            student_id         INTEGER NOT NULL,
            course_id          INTEGER NOT NULL,
            department_id      INTEGER,
            department_name    VARCHAR(255),
            education_level    VARCHAR(255),
            education_base     VARCHAR(255),
            semester           INTEGER,
            course_year        INTEGER,
            final_grade        INTEGER,
            total_events       INTEGER,
            avg_weekly_events  DECIMAL(10,2),
            total_course_views INTEGER,
            total_quiz_views   INTEGER,
            total_module_views INTEGER,
            total_submissions  INTEGER,
            peak_activity_week INTEGER,
            consistency_score  DECIMAL(5,2),
            activity_category  VARCHAR(50),
            last_update        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (student_id, course_id)
        );
        """
        with conn.cursor() as cursor:
            cursor.execute(queries)
        conn.commit()
    finally:
        conn.close()

def load_initial_student_data():
    conn = connect_to_db()
    try:
        query = """
        INSERT INTO dmr.analytics_student_performance 
            (student_id, course_id, department_id, semester, course_year, final_grade)
        SELECT DISTINCT ON (userid, courseid) 
            userid, courseid, Depart, Num_Sem, Kurs, NameR_Level
        FROM public.user_logs
        WHERE NameR_Level IS NOT NULL
        ORDER BY userid, courseid, num_week DESC
        ON CONFLICT (student_id, course_id) DO NOTHING; 
        """
        with conn.cursor() as cursor:
            cursor.execute(query)
        conn.commit()
    finally:
        conn.close()

def enrich_categorical_data():
    conn = connect_to_db()
    try:
        query_deps = """
        UPDATE dmr.analytics_student_performance AS target
        SET department_name = dict.name
        FROM public.departments dict
        WHERE target.department_id = dict.id;
        """
        query_edu = """
        UPDATE dmr.analytics_student_performance AS target
        SET education_level = CASE CAST(source.LevelEd AS VARCHAR) 
                WHEN '1' THEN 'бакалавриат' WHEN '2' THEN 'магистратура' ELSE 'иное' END,
            education_base = CASE CAST(source.Name_OsnO AS VARCHAR) 
                WHEN '1' THEN 'бюджет' WHEN '2' THEN 'контракт' ELSE 'иное' END
        FROM (
            SELECT DISTINCT ON (userid, courseid) userid, courseid, LevelEd, Name_OsnO 
            FROM public.user_logs
        ) source
        WHERE target.student_id = source.userid AND target.course_id = source.courseid;
        """
        with conn.cursor() as cursor:
            cursor.execute(query_deps)
            cursor.execute(query_edu)
        conn.commit()
    finally:
        conn.close()

def calculate_activity_sums():
    conn = connect_to_db()
    try:
        query = """
        UPDATE dmr.analytics_student_performance target
        SET total_events = source.t_events,
            total_course_views = source.t_course,
            total_quiz_views = source.t_quiz,
            total_module_views = source.t_module,
            total_submissions = source.t_sub
        FROM (
            SELECT userid, courseid, 
                   SUM(s_all) as t_events,
                   SUM(s_course_viewed) as t_course,
                   SUM(s_q_attempt_viewed) as t_quiz,
                   SUM(s_a_course_module_viewed) as t_module,
                   SUM(s_a_submission_status_viewed) as t_sub
            FROM public.user_logs
            GROUP BY userid, courseid
        ) as source
        WHERE target.student_id = source.userid AND target.course_id = source.courseid;
        """
        with conn.cursor() as cursor:
            cursor.execute(query)
        conn.commit()
    finally:
        conn.close()

def calculate_advanced_metrics():
    conn = connect_to_db()
    try:
        query_avg_events = """
        UPDATE dmr.analytics_student_performance AS target
        SET avg_weekly_events = ROUND(CAST(target.total_events AS NUMERIC) / NULLIF(source.week_count, 0), 2)
        FROM (SELECT userid, courseid, COUNT(DISTINCT num_week) AS week_count FROM public.user_logs GROUP BY userid, courseid) AS source
        WHERE target.student_id = source.userid AND target.course_id = source.courseid;
        """
        query_peak_week = """
        WITH RankedWeeks AS (
            SELECT userid, courseid, num_week, ROW_NUMBER() OVER (PARTITION BY userid, courseid ORDER BY s_all DESC) AS rn 
            FROM public.user_logs
        )
        UPDATE dmr.analytics_student_performance AS target
        SET peak_activity_week = source.num_week
        FROM RankedWeeks AS source
        WHERE source.rn = 1 AND target.student_id = source.userid AND target.course_id = source.courseid;
        """
        query_consistency = """
        UPDATE dmr.analytics_student_performance AS target
        SET consistency_score = ROUND(CAST(source.act_weeks AS NUMERIC) / NULLIF(source.tot_weeks, 0), 2)
        FROM (SELECT userid, courseid, COUNT(DISTINCT num_week) AS tot_weeks, COUNT(DISTINCT CASE WHEN s_all > 0 THEN num_week END) AS act_weeks FROM public.user_logs GROUP BY userid, courseid) AS source
        WHERE target.student_id = source.userid AND target.course_id = source.courseid;
        """
        query_category = """
        WITH ActivityRanks AS (
            SELECT student_id, course_id, PERCENT_RANK() OVER (ORDER BY total_events) AS pr FROM dmr.analytics_student_performance
        )
        UPDATE dmr.analytics_student_performance AS target
        SET activity_category = CASE WHEN source.pr <= 0.25 THEN 'низкая' WHEN source.pr <= 0.75 THEN 'средняя' ELSE 'высокая' END
        FROM ActivityRanks AS source
        WHERE target.student_id = source.student_id AND target.course_id = source.course_id;
        """
        with conn.cursor() as cursor:
            cursor.execute(query_avg_events)
            cursor.execute(query_peak_week)
            cursor.execute(query_consistency)
            cursor.execute(query_category)
        conn.commit()
    finally:
        conn.close()




# 1. Базовые аргументы для всех задач в этом DAG'е.
# Если какая-то задача упадет, Airflow подождет 1 минуту и попробует перезапустить её 1 раз.
default_args = {
    'owner': 'airflow',                 # Владелец процесса
    'depends_on_past': False,           # Запуск не зависит от того, успешно ли прошел вчерашний запуск
    'start_date': datetime(2024, 1, 1), # Точка отсчета для расписания (в прошлом)
    'retries': 1,                       # Количество попыток перезапуска при ошибке
    'retry_delay': timedelta(minutes=1),# Пауза перед повторной попыткой
}

# 2. Объявляем сам граф (DAG)
# Параметр schedule_interval=None означает, что он не будет запускаться сам по таймеру, запускаем вручную

with DAG(
    'create_student_performance_mart', # Имя в Airflow
    default_args=default_args,
    description='Сборка витрины успеваемости',
    schedule_interval=None, 
    catchup=False # False означает, что Airflow не будет пытаться запустить скрипт за все пропущенные дни с 2024 года (т.е он видит пропуск даты и запустит самое новое, не создавая таблицы в промежутке 2024-н.в)
) as dag:

    # 3. Создаем "Таски" (задачи). 
    # PythonOperator — это инструмент Airflow, который берет обычную Python-функцию 
    # и превращает её в квадратик в интерфейсе.
    


    task_init_schema = PythonOperator(
        task_id='init_schema',
        python_callable=init_data_mart_schema
    )

    task_load_initial = PythonOperator(
        task_id='load_initial_data',
        python_callable=load_initial_student_data
    )

    task_enrich_categorical = PythonOperator(
        task_id='enrich_categorical_data',
        python_callable=enrich_categorical_data
    )

    task_calculate_sums = PythonOperator(
        task_id='calculate_activity_sums',
        python_callable=calculate_activity_sums
    )

    task_calculate_advanced = PythonOperator(
        task_id='calculate_advanced_metrics',
        python_callable=calculate_advanced_metrics
    )

    # 4. Устанавливаем зависимости (порядок выполнения)
    # Оператор ">>" (bitshift right) в Airflow переопределен. 
    # Он говорит: "Выполни левую задачу, и ТОЛЬКО ЕСЛИ она успешна, запускай правую".
    # Это выстроит наши квадратики в одну красивую последовательную линию.
    
    (
        
        task_init_schema 
        >> task_load_initial 
        >> task_enrich_categorical 
        >> task_calculate_sums 
        >> task_calculate_advanced
    )