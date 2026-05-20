from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

# Базовые настройки для нашего расписания (DAG)
default_args = {
    'owner': 'admin',                 
    # Запускать ли задачу, если вчерашний запуск упал с ошибкой? False - запускать независимо.
    'depends_on_past': False,         
    'start_date': datetime(2023, 1, 1), 
    # Если скрипт выдаст ошибку, Airflow попробует запустить его еще 1 раз
    'retries': 1,                     
    # сделает это через 1 минуту после падения
    'retry_delay': timedelta(minutes=1), 
}

# Создаем сам конвейер задач
with DAG(
    dag_id='traffic_data_marts_etl',       
    default_args=default_args,
    description='Конвейер: Создаем данные -- Грузим в БД -- Считаем витрины',
    #  @daily означает каждый день запускать процесс
    schedule_interval='@daily',            
    # catchup=False значит, что Airflow не будет пытаться запустить скрипт за все 
    # пропущенные дни с 1 января 2023 года при самом первом включении.
    catchup=False,                         
    tags=['traffic', 'idz', 'bigdata'],    
) as dag:

    #  Запускаем скрипт генерации новых файлов с данными (Faker)
    task_generate_data = BashOperator(
        task_id='generate_data',
        bash_command='python /opt/airflow/scripts/generate_data.py',
    )

    #  Запускаем скрипт, который берет эти файлы и записывает в таблицы PostgreSQL
    task_load_raw = BashOperator(
        task_id='load_raw',
        bash_command='python /opt/airflow/scripts/load_raw.py',
    )

    #  Запускаем расчет первой витрины (досье на каждого водителя)
    task_create_owner_mart = BashOperator(
        task_id='create_owner_violations_mart',
        bash_command='python /opt/airflow/scripts/main.py',
    )

    # Задача 4: Запускаем расчет второй витрины (статистика по статьям ПДД)
    task_create_stats_mart = BashOperator(
        task_id='create_fine_stats_mart',
        bash_command='python /opt/airflow/scripts/fine_stats_mart.py',
    )

    # Указываем, в каком порядке задачи должны выполняться.
    # Стрелочки (>>) означают строго после
    # Квадратные скобки означают, что эти две задачи нужно запустить одновременно
    task_generate_data >> task_load_raw >> [task_create_owner_mart, task_create_stats_mart]