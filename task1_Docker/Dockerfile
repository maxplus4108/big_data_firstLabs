# Используем официальный образ PostgreSQL
FROM postgres:13

# Копируем папку с наборами данных внутрь образа
# Она будет доступна для скрипта инициализации
COPY datasets /datasets/

# Копируем скрипт инициализации, который будет исполнен при старте
COPY init.sh /docker-entrypoint-initdb.d/

# ВАЖНО: Даем права на выполнение скрипта
RUN chmod +x /docker-entrypoint-initdb.d/init.sh