import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv('/opt/airflow/scripts/.env')


def load_csv_to_db():
    print("Инициализация подключения...")

    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST')
    port = os.getenv('DB_PORT')
    db = os.getenv('DB_NAME')

    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{db}')
    data_dir = '/opt/airflow/data'

    with engine.begin() as conn:
        # Гарантируем, что схема public существует в чистой базе.
        # В public храним только сырые таблицы проекта:
        # owners, cars, policies, fines
        print("Подготовка схемы public...")
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS public;"))

        # Гарантируем, что схема mart существует.
        # В mart будут лежать только аналитические витрины.
        print("Подготовка схемы mart...")
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS mart;"))

        # Удаляем старые витрины, потому что они зависят от сырых таблиц.
        # Если не удалить витрины заранее, DROP public.* CASCADE тоже их удалит,
        # но так логика более понятная.
        print("Удаление старых витрин...")
        conn.execute(text("DROP TABLE IF EXISTS mart.owner_violations CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS mart.fine_stats CASCADE;"))

        # Удаляем только наши 4 сырые таблицы.
        # ВАЖНО: мы не удаляем всю схему public, чтобы случайно не снести служебные объекты.
        print("Удаление старых raw-таблиц...")
        conn.execute(text("""
            DROP TABLE IF EXISTS
                public.fines,
                public.policies,
                public.cars,
                public.owners
            CASCADE;
        """))

    # Порядок важен:
    # сначала owners, потом cars, потом policies и fines,
    # потому что cars ссылается на owners, а policies/fines ссылаются на cars.
    tables = {
        'owners': 'owners.csv',
        'cars': 'cars.csv',
        'policies': 'policies.csv',
        'fines': 'fines.csv'
    }

    # Загружаем данные по очереди
    for table_name, file_name in tables.items():
        file_path = os.path.join(data_dir, file_name)
        df = pd.read_csv(file_path)

        # schema='public' — Pandas точно знает, куда загружать таблицы.
        # if_exists='replace' тут не используем, потому что выше мы уже явно удалили таблицы.
        df.to_sql(
            table_name,
            engine,
            schema='public',
            if_exists='append',
            index=False
        )

        print(f"Таблица {table_name} успешно загружена в схему public.")

    # После загрузки через pandas.to_sql добавляем ключи и связи.
    # Pandas сам не создает PRIMARY KEY и FOREIGN KEY.
    with engine.begin() as conn:
        print("Добавление первичных и внешних ключей...")

        conn.execute(text("""
            ALTER TABLE public.owners
            ADD PRIMARY KEY (owner_id);
        """))

        conn.execute(text("""
            ALTER TABLE public.cars
            ADD PRIMARY KEY (car_id);
        """))

        conn.execute(text("""
            ALTER TABLE public.policies
            ADD PRIMARY KEY (policy_id);
        """))

        conn.execute(text("""
            ALTER TABLE public.fines
            ADD PRIMARY KEY (fine_id);
        """))

        conn.execute(text("""
            ALTER TABLE public.cars
            ADD CONSTRAINT fk_cars_owner
            FOREIGN KEY (owner_id)
            REFERENCES public.owners(owner_id);
        """))

        conn.execute(text("""
            ALTER TABLE public.policies
            ADD CONSTRAINT fk_policies_car
            FOREIGN KEY (car_id)
            REFERENCES public.cars(car_id);
        """))

        conn.execute(text("""
            ALTER TABLE public.fines
            ADD CONSTRAINT fk_fines_car
            FOREIGN KEY (car_id)
            REFERENCES public.cars(car_id);
        """))

    print("Обновление данных успешно завершено.")


if __name__ == "__main__":
    load_csv_to_db()