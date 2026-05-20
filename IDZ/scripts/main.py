import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('/opt/airflow/scripts/.env')


def build_owner_violations_mart():
    print("Создаем витрину mart.owner_violations")
    conn = None

    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )

        # Отключаем авто-сохранение, чтобы запрос выполнился либо целиком, либо никак.
        # Если где-то будет ошибка, сделаем rollback.
        conn.autocommit = False

        query = """
        -- Создаем отдельную схему для аналитики, если ее еще нет.
        -- В public лежат сырые данные, а в mart — готовые витрины.
        CREATE SCHEMA IF NOT EXISTS mart;

        -- Удаляем старую версию таблицы, чтобы создать новую.
        -- Это полная пересборка витрины, а не INSERT новых строк.
        DROP TABLE IF EXISTS mart.owner_violations;

        -- Создаем новую таблицу-витрину.
        CREATE TABLE mart.owner_violations AS

        -- 1) Считаем количество машин у каждого владельца
        WITH car_counts AS (
            SELECT
                owner_id,
                COUNT(car_id) AS num_cars
            FROM public.cars
            GROUP BY owner_id
        ),

        -- 2) Считаем общее количество штрафов и сумму неоплаченных штрафов
        fine_stats AS (
            SELECT
                c.owner_id,
                COUNT(f.fine_id) AS total_fines,
                COALESCE(
                    SUM(
                        CASE
                            WHEN LOWER(f.status) = 'не оплачен'
                            THEN f.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_amount_unpaid
            FROM public.cars c
            LEFT JOIN public.fines f
                ON c.car_id = f.car_id
            GROUP BY c.owner_id
        ),

        -- 3) Считаем количество просроченных страховок
        insurance_stats AS (
            SELECT
                c.owner_id,
                COUNT(p.policy_id) AS expired_insurances
            FROM public.cars c
            LEFT JOIN public.policies p
                ON c.car_id = p.car_id
               AND p.end_date::date < CURRENT_DATE
            GROUP BY c.owner_id
        )

        -- Собираем все данные в одну витрину по владельцам
        SELECT
            o.owner_id,
            o.full_name,
            COALESCE(fs.total_fines, 0) AS total_fines,
            COALESCE(fs.total_amount_unpaid, 0) AS total_amount_unpaid,
            COALESCE(cc.num_cars, 0) AS num_cars,
            COALESCE(i.expired_insurances, 0) AS expired_insurances
        FROM public.owners o
        LEFT JOIN car_counts cc
            ON o.owner_id = cc.owner_id
        LEFT JOIN fine_stats fs
            ON o.owner_id = fs.owner_id
        LEFT JOIN insurance_stats i
            ON o.owner_id = i.owner_id;

        -- Ключ для ускорения поиска и уникальности владельцев в витрине
        ALTER TABLE mart.owner_violations
        ADD PRIMARY KEY (owner_id);
        """

        with conn.cursor() as cursor:
            cursor.execute(query)

        conn.commit()
        print("Витрина mart.owner_violations обновлена")

    except Exception as e:
        print(f"ОШИБКА: {e}")

        if conn:
            conn.rollback()

        # Важно пробрасывать ошибку дальше,
        # чтобы Airflow увидел падение задачи и покрасил ее в красный.
        raise e

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    build_owner_violations_mart()