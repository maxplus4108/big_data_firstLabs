import os
import random
import pandas as pd
from faker import Faker
from datetime import datetime, timedelta

def generate_synthetic_data():
    print("Инициализация процесса генерации синтетических данных...")
    

    fake = Faker('ru_RU')

    # Фиксация seed гарантирует воспроизводимость результатов: 
    # при каждом запуске скрипта будут генерироваться одни и те же данные
    Faker.seed(42)      
    random.seed(42)

    # Функция формирования базы автовладельцев
    def generate_owners(n) -> pd.DataFrame:
        owners = []
        for i in range(1, n + 1):
            owners.append({
                'owner_id': i,
                'full_name': fake.name(), 
                # Имитация формата российского водительского удостоверения (серия и номер)
                'driver_license': f"{random.randint(1000, 9999)} {random.randint(100000, 999999)}",
                # Очистка адреса от символов переноса строки для корректного сохранения в CSV
                'address': fake.address().replace('\n', ', '),
                'phone': fake.phone_number()
            })
        return pd.DataFrame(owners)

    # Функция формирования автопарка
    def generate_cars(n, owner_ids) -> pd.DataFrame:
        cars = []
        # Словарь наиболее популярных марок и моделей на рынке
        brands_models = {
            'Lada': ['Vesta', 'Granta', 'Niva'],
            'Toyota': ['Camry', 'Corolla', 'RAV4'],
            'Kia': ['Rio', 'Sportage', 'Optima'],
            'Hyundai': ['Solaris', 'Creta', 'Tucson'],
            'Volkswagen': ['Polo', 'Tiguan', 'Jetta', 'Golf']
        }
        
        for i in range(1, n + 1):
            brand = random.choice(list(brands_models.keys()))
            model = random.choice(brands_models[brand])
            
            cars.append({
                'car_id': i,
                'license_plate': fake.license_plate(), 
                'brand': brand,
                'model': model,
                'year': random.randint(2000, 2026),    
                'vin': fake.vin(),                     
                'color': fake.color_name(),
                # Случайная привязка автомобиля к существующему владельцу по внешнему ключу
                'owner_id': random.choice(owner_ids) 
            })
        return pd.DataFrame(cars)

    # Функция генерации истории нарушений ПДД
    def generate_fines(n, car_ids) -> pd.DataFrame:
        fines = []
        # Справочник нарушений и соответствующих им базовых тарифов
        violations = [
            ("Превышение скорости (12.9 ч.2 КоАП)", 500),
            ("Проезд на запрещающий сигнал (12.12 ч.1 КоАП)", 1000),
            ("Нарушение правил парковки (12.19 КоАП)", 1500),
            ("Выезд на встречную полосу (12.15 ч.4 КоАП)", 5000),
            ("Непристегнутый ремень (12.6 КоАП)", 1000)
        ]
        
        for i in range(1, n + 1):
            violation, amount = random.choice(violations)
            fines.append({
                'fine_id': i,
                'car_id': random.choice(car_ids), 
                # Распределение штрафов за последние 3 года от текущей даты
                'date': fake.date_between(start_date='-3y', end_date='today'), 
                'violation': violation, 
                'amount': amount, 
                # Имитация платежной дисциплины: 70% штрафов оплачиваются, 30% переходят в долг
                'status': random.choices(['оплачен', 'не оплачен'], weights=[0.7, 0.3])[0] 
            })
        return pd.DataFrame(fines)

    # Функция оформления страховых полисов
    def generate_policies(n, car_ids) -> pd.DataFrame:
        policies = []
        companies = ['Росгосстрах', 'АльфаСтрахование', 'Ингосстрах', 'Т-Страхование']
        
        for i in range(1, n + 1):
            # Полис оформляется случайной датой в пределах последних двух лет
            start_date = fake.date_between(start_date='-2y', end_date='today')
            # Срок действия полиса ОСАГО строго 1 год
            end_date = start_date + timedelta(days=365) 
            
            policies.append({
                'policy_id': i,
                'car_id': random.choice(car_ids),
                'company': random.choice(companies),
                'start_date': start_date,
                'end_date': end_date,
                # Разброс стоимости полиса в зависимости от коэффициентов
                'cost': random.randint(5000, 25000) 
            })
        return pd.DataFrame(policies)

    # Определение объемов выборок согласно бизнес-требованиям
    N_OWNERS = 1000
    N_CARS = 1200
    N_FINES = 5000
    N_POLICIES = 1500

    print(f"Формирование датасетов: {N_OWNERS} владельцев, {N_CARS} авто, {N_FINES} штрафов, {N_POLICIES} полисов...")
    
    # Последовательный вызов функций с пробросом внешних ключей (ID) для сохранения связности данных
    owners_df = generate_owners(N_OWNERS)
    cars_df = generate_cars(N_CARS, owners_df['owner_id'].tolist())
    fines_df = generate_fines(N_FINES, cars_df['car_id'].tolist())
    policies_df = generate_policies(N_POLICIES, cars_df['car_id'].tolist())

    # Директория монтирования volumes в конфигурации Docker
    data_dir = '/opt/airflow/data'
    os.makedirs(data_dir, exist_ok=True)

    # Выгрузка сформированных датафреймов в формат CSV без индексов pandas
    owners_df.to_csv(f'{data_dir}/owners.csv', index=False)
    cars_df.to_csv(f'{data_dir}/cars.csv', index=False)
    fines_df.to_csv(f'{data_dir}/fines.csv', index=False)
    policies_df.to_csv(f'{data_dir}/policies.csv', index=False)

    

if __name__ == "__main__":
    generate_synthetic_data()