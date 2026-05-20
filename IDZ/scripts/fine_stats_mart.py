import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('/opt/airflow/scripts/.env')


def build_fine_stats_mart():
    print("Создаем витрину mart.fine_stats")
    conn = None

    try:
        # Подключаемся к базе
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )

        # Отключаем авто-сохранение, чтобы все прошло или целиком, или никак.
        # Если где-то будет ошибка, делаем rollback.
        conn.autocommit = False

        query = """
        -- Создаем схему для аналитики, если ее нет.
        -- В public лежат сырые таблицы, в mart — аналитические витрины.
        CREATE SCHEMA IF NOT EXISTS mart;

        -- Удаляем старую таблицу, если она была.
        -- Это полная пересборка витрины, а не INSERT новых строк.
        DROP TABLE IF EXISTS mart.fine_stats;

        -- Создаем новую таблицу с результатами.
        CREATE TABLE mart.fine_stats AS

        -- 1) Считаем базовые цифры по каждому виду нарушения
        WITH stats AS (
            SELECT
                violation,
                COUNT(fine_id) AS total_fines,
                ROUND(AVG(amount), 2) AS avg_amount,

                -- Считаем только те штрафы, где статус 'оплачен'
                SUM(
                    CASE
                        WHEN LOWER(status) = 'оплачен'
                        THEN 1
                        ELSE 0
                    END
                ) AS paid_count
            FROM public.fines
            GROUP BY violation
        )

        -- 2) Выводим итоговую таблицу и считаем процент оплат
        SELECT
            violation AS article,
            total_fines,
            avg_amount,

            -- Считаем процент: оплачено / всего * 100.
            -- Если штрафов 0, ставим 0, чтобы не было деления на ноль.
            CASE
                WHEN total_fines > 0
                THEN ROUND((paid_count::numeric / total_fines::numeric) * 100, 2)
                ELSE 0
            END AS payment_rate
        FROM stats
        WHERE violation IS NOT NULL;

        -- Делаем колонку с названием нарушения уникальным ключом
        ALTER TABLE mart.fine_stats
        ADD PRIMARY KEY (article);
        """

        with conn.cursor() as cursor:
            cursor.execute(query)

        # Фиксируем изменения в базе
        conn.commit()
        print("Витрина mart.fine_stats обновлена")

    except Exception as e:
        print(f"ОШИБКА: {e}")

        if conn:
            # Если возникла ошибка, отменяем все изменения
            conn.rollback()

        # Важно пробрасывать ошибку дальше,
        # чтобы Airflow увидел падение задачи.
        raise e

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    build_fine_stats_mart()