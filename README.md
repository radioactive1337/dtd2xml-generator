# QA XML Generator Tool

Локальный QA-инструмент для генерации XML по большим DTD-схемам, заполнения данными из БД и LLM и проверки результата.

## Быстрый старт

Типичный сценарий — за несколько минут получить валидный XML под вашу DTD.

### 1. Подготовка окружения

1. Установите зависимости backend и frontend (см. [Установка](#установка)).
2. Скопируйте `backend/connections.json.example` → `connections.json` в корне репозитория и укажите алиасы БД и LLM.
3. Запустите оба процесса в dev-режиме и откройте [http://localhost:5173](http://localhost:5173).

### 2. Проверка подключений

На странице **Настройки** нажмите «Проверить БД» и «Проверить LLM» для нужных алиасов. Секреты остаются в `connections.json` на сервере — в UI видны только имена алиасов.

### 3. Загрузка DTD

На главной странице (**Генератор**) загрузите `.dtd` (или архив со схемой). После загрузки появятся вкладки **Структура**, **Данные** и **Результат**. Схема сохраняется в `dtd_schemas/` и поднимается при следующем старте backend.

### 4. Сборка каркаса XML

Вкладка **Структура**:


| Параметр         | Назначение                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| Корневой элемент | Точка входа в дерево DTD                                                                                           |
| Режим сборки     | **Минимальный** — обязательные узлы; **Максимальный** — с повторами `+`/`*`; **Свой** — выбор веток в дереве схемы |


Нажмите **Сгенерировать XML** — справа появится каркас с пустыми или placeholder-значениями.

### 5. Заполнение данными

Вкладка **Данные** — выберите стратегию:


| Стратегия              | Когда использовать                             |
| ---------------------- | ---------------------------------------------- |
| **Faker**              | Быстрые тестовые данные без внешних сервисов   |
| **AI / LLM**           | Контекстное заполнение по смыслу полей         |
| **Гибрид: БД + Faker** | Часть полей из SQL-запросов, остальное — Faker |
| **Гибрид: БД + AI**    | Данные из БД + догенерация через LLM           |


Для гибридных режимов настройте **маппинг** (поле XML → SQL) через мастер или сохранённый пресет. Пресеты лежат в `mapping_presets/` и привязаны к алиасу БД.

Нажмите **Заполнить данными**. Опционально включите «Проверять DTD после заполнения».

### 6. Проверка и экспорт

- **Проверить по DTD** — валидация текущего XML; ошибки видны на вкладке **Результат** с переходом к проблемному месту.
- Редактируйте XML вручную в правой панели.
- Скачайте результат или восстановите предыдущую версию из истории генераций.

## Установка

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

### Конфигурация

Все учётные данные и настройки runtime хранятся в одном локальном файле — `**connections.json**`.

```bash
copy backend\connections.json.example connections.json
```

Файл добавлен в `.gitignore`.

Пример структуры:

```json
{
  "app": {
    "host": "0.0.0.0",
    "port": 8080,
    "log_level": "INFO"
  },
  "oracle_thick_mode": true,
  "oracle_client_lib_dir": "C:\\Oracle\\client19_64\\bin",
  "oracle_home": "C:\\Oracle\\client19_64",
  "ora_tzfile": null,
  "databases": {
    "PGSQL_DB": {
      "driver": "postgresql",
      "host": "localhost",
      "port": 5432,
      "database": "qa_auto",
      "user": "qa_user",
      "password": "change-me"
    },
    "ORACLE_DB": {
      "driver": "oracle",
      "host": "db-host.example.com",
      "port": 1521,
      "database": "ORCLPDB1",
      "user": "app_user",
      "password": "change-me"
    }
  },
  "llm": {
    "default": {
      "base_url": "http://localhost:11434/v1",
      "api_key": "your-token-here",
      "model": "gpt-4o-mini"
    }
  }
}
```

В UI (страница Settings) отображаются только **алиасы** подключений. Пароли и API-ключи остаются на сервере.

## Oracle Instant Client (обязателен для Oracle 11g)

Backend использует **python-oracledb**. Есть два режима:


| Режим                      | Когда подходит                                                |
| -------------------------- | ------------------------------------------------------------- |
| **Thin** (по умолчанию)    | Oracle Database **12.1+** — дополнительная установка не нужна |
| **Thick** (Instant Client) | Oracle **11.2 и старше**                                      |


Если видите ошибку `DPY-3010: connections to this database server version are not supported by python-oracledb in thin mode` — нужен thick mode.

### 1. Установка Oracle Instant Client

На Windows:

1. Скачайте **Oracle Client 19.x** (Basic или Light).
2. Распакуйте в постоянный путь, например `C:\Oracle\client19_64\`.
3. Убедитесь, что `oci.dll` на месте:
  ```powershell
   dir C:\Oracle\client19_64\bin\oci.dll
  ```

### 2. Настройка алиаса Oracle в `connections.json`

Используйте `"driver": "oracle"` (или `"oracledb"`).

**Service name** (PDB/CDB, самый частый случай):

```json
{
  "driver": "oracle",
  "host": "db-host.example.com",
  "port": 1521,
  "database": "ORCLPDB1",
  "user": "app_user",
  "password": "your-password"
}
```

Поле `database` — это **service name**, а не имя схемы.

**SID** (устаревшие инстансы):

```json
{
  "driver": "oracle",
  "host": "db-host.example.com",
  "port": 1521,
  "database": "",
  "sid": "ORCL",
  "user": "app_user",
  "password": "your-password"
}
```

### 4. Полный перезапуск backend

Thick mode инициализируется при старте процесса (`bootstrap_oracle_client()` в `main.py`).

После изменения `connections.json`:

1. Остановите все процессы backend (Ctrl+C; на Windows проверьте, не остались ли лишние `python.exe` после hot-reload).
2. Запустите uvicorn заново.

Одного hot-reload может быть недостаточно — Oracle client может не переинициализироваться.

### 5. Файлы часовых поясов (`ORA-01804`)

При ошибке `ORA-01804: failure to initialize timezone information`:

- **Сначала попробуйте:** оставить `"ora_tzfile": null` в `connections.json`.
- Значение `v$timezone_file` на **сервере БД** не обязано совпадать с файлами в **локальном** Instant Client. У Client 19 часто есть `timezlrg_32.dat`, а не `timezlrg_1.dat`.
- Если всё же нужно указать файл — используйте `.dat`, который реально лежит в:
  ```
  %ORACLE_HOME%\oracore\zoneinfo\
  ```
- В крайнем случае скопируйте нужный `.dat` с сервера БД в эту папку.

## Поддерживаемые БД


| Значение `driver`     | Движок                       | Примечания                                                                           |
| --------------------- | ---------------------------- | ------------------------------------------------------------------------------------ |
| `postgresql`          | PostgreSQL через asyncpg     | Сессия переводится в режим **READ ONLY**                                             |
| `oracle` / `oracledb` | Oracle через python-oracledb | Для 11g нужен thick mode; на Windows запросы идут через sync-драйвер в worker thread |


Имена колонок в ответах API приводятся к **нижнему регистру** (Oracle отдаёт `INN`, приложение — `inn`).

## DTD-схемы

Загруженные DTD сохраняются в `dtd_schemas/` (в `.gitignore`). При старте backend папка сканируется и основная схема поднимается в память — после перезапуска повторная загрузка через UI не нужна.

При загрузке новой схемы файлы от предыдущих схем удаляются автоматически.

## Пресеты маппинга

Именованные маппинги полей БД → XML сохраняются в `mapping_presets/` (в `.gitignore`). У каждого пресета свой алиас БД, поэтому разные маппинги могут ходить в разные подключения.

## Запуск

### Docker (production)

Один контейнер собирает frontend и запускает backend на порту **8080**.

**Требования:** Docker и Docker Compose.

1. Подготовьте конфигурацию:

```bash
copy config\connections.json.example config\connections.json
```

В Docker `localhost` указывает на сам контейнер. Для сервисов на хосте (PostgreSQL, Ollama и т.д.) используйте `host.docker.internal` — это уже задано в примере.

> **Важно:** не монтируйте `connections.json` как отдельный файл — если его нет на хосте, Docker создаст **папку** с таким именем и приложение упадёт с `IsADirectoryError`. Используйте каталог `config/`.

2. Создайте каталоги для данных (если их ещё нет):

```bash
mkdir dtd_schemas mapping_presets presets
```

3. Соберите и запустите:

```bash
docker compose up --build -d
```

Откройте [http://localhost:8080](http://localhost:8080)

**Полезные команды:**

```bash
docker compose logs -f app    # логи
docker compose down           # остановка
docker compose up --build     # пересборка после изменений кода
```

**Тома:** `config/`, `dtd_schemas/`, `mapping_presets/`, `presets/` монтируются с хоста и сохраняются между перезапусками.

**Oracle в Docker (без volume):**

1. Скачайте `instantclient-basic-linux.x64-19.31.0.0.0dbru.zip`.
2. Положите архив в `docker/oracle/` (не распаковывайте).
3. Пересоберите контейнер:
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

Во время сборки `Dockerfile` автоматически распакует клиент в `/opt/oracle/instantclient`.

В `config/connections.json` укажите:

```json
{
  "oracle_client_lib_dir": "/opt/oracle/instantclient",
  "oracle_home": "/opt/oracle/instantclient"
}
```

И добавьте алиас Oracle с `host: "host.docker.internal"` (или именем сервиса в compose-сети).

### Разработка (два терминала)

```bash
# Терминал 1 — API на порту 8080
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Терминал 2 — UI на порту 5173
cd frontend
npm run dev
```

Откройте [http://localhost:5173](http://localhost:5173)

### Production (один процесс)

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Откройте [http://localhost:8080](http://localhost:8080)

## Тесты

```bash
cd backend
pytest tests/ -v
```

## Решение проблем


| Симптом                                  | Вероятная причина                      | Что сделать                                                                                          |
| ---------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `Unsupported database driver: oracle`    | Старый backend или неверный `driver`   | Укажите `"driver": "oracle"`, переустановите зависимости, перезапустите                              |
| `DPY-3010` / thin mode                   | Oracle 11g без Instant Client          | Установите Instant Client, задайте `oracle_client_lib_dir`, полный перезапуск                        |
| `Oracle thick mode failed to initialize` | Неверный путь или нет `oci.dll`        | Исправьте `oracle_client_lib_dir`, проверьте наличие `oci.dll`                                       |
| `ORA-01804`                              | Отсутствует или неверный timezone-файл | Сначала `"ora_tzfile": null`; если задаёте файл — только тот, что есть локально в `oracore\zoneinfo` |
| `Database alias '…' not found`           | Опечатка или нет `connections.json`    | Скопируйте example, проверьте совпадение алиаса с пресетом                                           |
| DTD пропала после перезапуска            | Пустая `dtd_schemas/`                  | Загрузите снова; папка должна сохраняться между запусками                                            |


В логах backend при ошибках есть контекст: алиас, driver, host, усечённый SQL. Для подробностей задайте `"log_level": "DEBUG"` в `connections.json` → `app`.