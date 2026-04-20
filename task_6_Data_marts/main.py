import os
import sys
from dotenv import load_dotenv
import psycopg2

# Загружаем настройки из файла .env
load_dotenv()

def connect_to_db():
    """Создает подключение к базе данных строго через переменные окружения."""
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
        sys.exit(1)

def init_data_mart_schema(conn):
    """Шаг 1: Подготавливаем схему и пустой каркас витрины."""
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
    print("Схема dmr и таблица витрины готовы.")

def load_initial_student_data(conn):
    """Вытягиваем уникальных студентов и их базовые данные."""
    query = """
    INSERT INTO dmr.analytics_student_performance 
        (student_id, course_id, department_id, semester, course_year, final_grade)
    
    SELECT DISTINCT ON (userid, courseid) 
        userid, courseid, Depart, Num_Sem, Kurs, 
        NameR_Level
    FROM public.user_logs
    WHERE NameR_Level IS NOT NULL
    ORDER BY userid, courseid, num_week DESC
    ON CONFLICT (student_id, course_id) DO NOTHING; 
    -- в случае повторного запуска скрипта ошибки не будет 
    """
    with conn.cursor() as cursor:
        cursor.execute(query)
    conn.commit()
    print(" Базовые ID студентов загружены.")

def enrich_categorical_data(conn):
    """ Добавляем в витрину текстовую часть (кафедры, форма обучения)."""
    query_deps = """
    UPDATE dmr.analytics_student_performance AS target
    SET department_name = dict.name
    FROM public.departments dict
    WHERE target.department_id = dict.id;
    """

    query_edu = """
    UPDATE dmr.analytics_student_performance AS target
    -- переводим данные в VARCHAR перед сравнением, чтобы избежать ошибок типов
    SET education_level = CASE 
    CAST(source.LevelEd AS VARCHAR) 
    WHEN '1' THEN 'бакалавриат' 
    WHEN '2' THEN 'магистратура' 
    ELSE 'иное' 
    END,
        education_base = CASE CAST(source.Name_OsnO AS VARCHAR) 
        WHEN '1' THEN 'бюджет' 
        WHEN '2' THEN 'контракт' 
        ELSE 'иное' END
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
    print("Категориальные текстовые данные обновлены.")

def calculate_activity_sums(conn):
    """Считаем суммарную активность за весь семестр."""
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
    print("Итоговые суммы действий рассчитаны.")

def calculate_advanced_metrics(conn):
    """
    1. Среднее количество событий
    2. Неделя пиковой активности
    3. Коэффициент стабильности
    4. Категория активности
    """

    # Среднее количество событий в неделю 
    # делим общую сумму на количество недель
    query_avg_events = """
    UPDATE dmr.analytics_student_performance AS target
    SET 
        avg_weekly_events = ROUND(
        -- Округляем до 2 знаков. CAST превращает целое в число с запятой (чтобы не потерять точность).
            CAST(target.total_events AS NUMERIC) / NULLIF(source.week_count, 0), 
            2
    FROM (
    -- Считаем, сколько всего разных недель студент проявлял активность
        SELECT 
            userid, 
            courseid, 
            COUNT(DISTINCT num_week) AS week_count 
        FROM public.user_logs 
        GROUP BY userid, courseid
    ) AS source
    WHERE target.student_id = source.userid 
      AND target.course_id = source.courseid;
    """

    # Пиковая неделя активности 
    # Используем временную таблицу, чтобы найти лучшую неделю
    query_peak_week = """
    WITH RankedWeeks AS (
        SELECT 
            userid, 
            courseid, 
            num_week, 
            -- Оконная функция ROW_NUMBER раздаёт места неделям (от самой активной до слабой)
            ROW_NUMBER() OVER (
                PARTITION BY userid, courseid  -- Группируем по студенту и курсу
                ORDER BY s_all DESC            -- Сортируем: больше всего событий = 1-е место
            ) AS rn 
        FROM public.user_logs
    )
    UPDATE dmr.analytics_student_performance AS target
    SET 
        peak_activity_week = source.num_week
    FROM RankedWeeks AS source
    WHERE source.rn = 1  -- Берем только неделю 1 по количеству событий
      AND target.student_id = source.userid 
      AND target.course_id = source.courseid;
    """

    # Коэффициент стабильности 
    # Вычисляем отношение активных недель к общему количеству недель
    query_consistency = """


    -- Обновляем данные в таблице витрины
    UPDATE dmr.analytics_student_performance AS target
    SET 
        -- Рассчитываем коэффициент стабильности: делим число активных недель на общее число недель
        consistency_score = ROUND(
            CAST(source.act_weeks AS NUMERIC) / NULLIF(source.tot_weeks, 0), 
            2 
        )
    FROM (
        -- Подзапрос (source): собираем сводную статистику по активности из сырых логов
        SELECT 
            userid, 
            courseid, 
            -- Считаем общее количество уникальных недель (сколько всего недель длится/идет курс)
            COUNT(DISTINCT num_week) AS tot_weeks, 
            -- Считаем только те уникальные недели, на которых у студента было хотя бы одно действие (s_all > 0)
            COUNT(DISTINCT CASE WHEN s_all > 0 THEN num_week END) AS act_weeks 
        FROM public.user_logs 
        -- Группируем все данные так, чтобы получить итоги отдельно для каждого студента на каждом курсе
        GROUP BY userid, courseid
    ) AS source
    
    
    
    -- Условие объединения: записываем рассчитанный коэффициент именно тому студенту и в тот курс, к которому он относится
    WHERE target.student_id = source.userid 
      AND target.course_id = source.courseid;
    """

    # Категория активности 
    # Сравниваем студентов между собой и делим на группы
    query_category = """
    WITH ActivityRanks AS (
    -- PERCENT_RANK вычисляет место студента в общем рейтинге (от 0.0 до 1.0)
        SELECT 
            student_id, 
            course_id, 
            PERCENT_RANK() OVER (ORDER BY total_events) AS pr 
        FROM dmr.analytics_student_performance
    )
    UPDATE dmr.analytics_student_performance AS target
    SET 
        activity_category = CASE 
            WHEN source.pr <= 0.25 THEN 'низкая' 
            WHEN source.pr <= 0.75 THEN 'средняя' 
            ELSE 'высокая' 
        END
    FROM ActivityRanks AS source
    WHERE target.student_id = source.student_id 
      AND target.course_id = source.course_id;
    """

    # Выполнение всех запросов по очереди
    with conn.cursor() as cursor:
        cursor.execute(query_avg_events)
        cursor.execute(query_peak_week)
        cursor.execute(query_consistency)
        cursor.execute(query_category)
    
    conn.commit()

def main():
    connection = None
    try:
        #Подключение к БД
        connection = connect_to_db()
        
        # Запускаем конвейер сборки витрины
        init_data_mart_schema(connection)
        load_initial_student_data(connection)
        enrich_categorical_data(connection)
        calculate_activity_sums(connection)
        calculate_advanced_metrics(connection)
        
        print("\nАналитическая витрина собрана!")
    except Exception as e:
        print(f"\nОшибка выполнения: {e}")
        if connection:
            connection.rollback()
    finally:
        if connection:
            connection.close()
            print("Соединение с БД закрыто.")

if __name__ == "__main__":
    main()


































