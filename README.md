# XML Generator Tool

Локальный инструмент для генерации XML по большим DTD-схемам, заполнения данными из БД и LLM и проверки результата.

## Быстрый старт

### 1. Подготовка окружения

1. Установите зависимости backend и frontend (см. [Установка](#установка)).
2. Скопируйте `config/app.json.example` → `config/app.json` и `config/connections.json.example` → `config/connections.json`; укажите алиасы БД и LLM.
3. Запустите приложение в [режиме разработки](#разработка-два-терминала) и откройте [http://localhost:5173](http://localhost:5173).

### 2. Проверка подключений

На странице **Настройки** нажмите «Проверить БД» и «Проверить LLM» для нужных алиасов. Секреты остаются в `config/connections.json` на сервере — в UI видны только имена алиасов.

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

### 7. Библиотека XML

На вкладке **Результат** доступна **Библиотека XML**:

- **Эталоны** — документы из внешнего Git-репозитория (`xml-library/{category}/{name}.txt` или `.xml`). Обновление вручную кнопкой «Обновить из Git».
- **Мои документы** — личные сохранённые XML на сервере (`data/users/{id}/xml_documents/`).

Кнопка **Открыть** подставляет XML в редактор и обновляет staging cache для заполнения. История генераций в браузере (`localStorage`) не затрагивается.

Настройка эталонов в `config/app.json`:

```json
{
  "reference_xml": {
    "enabled": true,
    "repo_url": "git@github.com:org/xml-library.git",
    "branch": "main",
    "subdir": "xml-library",
    "cache_dir": "data/reference-xml"
  }
}
```

- **`cache_dir`** — путь относительно корня проекта; клон Git хранится здесь.
- **`subdir`** — подпапка внутри клона с категориями эталонов.
- Для private HTTPS-репозиториев каждый пользователь задаёт **Git-токен** на странице **Настройки** (хранится в per-user `connections.json` на сервере). Для GitLab укажите пользователя `oauth2` (по умолчанию). Администратор может задать fallback **`REFERENCE_XML_GIT_TOKEN`** / **`REFERENCE_XML_GIT_USER`** в окружении.
- Для SSH используйте deploy key в контейнере/на сервере.

При первом запуске нажмите «Обновить из Git» в UI или выполните `git clone` в `data/reference-xml/` вручную.

## Установка

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements-dev.txt
```

### Frontend

```bash
cd frontend
npm install
```

### Конфигурация

Локальные файлы (в `.gitignore`, в репозитории только `*.example`):

| Файл | Содержимое |
| ---- | ---------- |
| **`config/app.json`** | Глобальные настройки: host/port, `log_level`, Oracle Instant Client, `allow_self_registration`, `session_secret`, `reference_xml` (эталонная библиотека) |
| **`config/connections.json`** | Legacy single-user: алиасы БД/LLM с паролями и API-ключами (в мультипользовательском режиме заменяется per-user файлами в `data/`) |

```bash
copy config\app.json.example config\app.json
copy config\connections.json.example config\connections.json
```

При первом запуске backend допишет в `app.json` сгенерированный **`session_secret`** (подпись cookie-сессий). На production задайте свой ключ через переменную окружения **`SESSION_SECRET`** — тогда секрет не попадёт в файл.

**`config/app.json`** — глобальные настройки. Thick mode для Oracle включается автоматически, если задан `oracle_client_lib_dir` (или `oracle_home`); отдельного флага нет.

```json
{
  "app": {
    "host": "0.0.0.0",
    "port": 8080,
    "log_level": "INFO",
    "allow_self_registration": true
  },
  "oracle_client_lib_dir": "C:\\Oracle\\client19_64\\bin",
  "oracle_home": "C:\\Oracle\\client19_64",
  "ora_tzfile": null
}
```

**`config/connections.json`** — алиасы БД и LLM. Секция `app` здесь хранит только `default_llm_alias` (какой LLM использовать по умолчанию при нескольких алиасах). Для локального запуска используйте `localhost`; для Docker — `host.docker.internal` (см. [Docker](#docker)).

```json
{
  "app": {
    "default_llm_alias": null
  },
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

### 2. Настройка алиаса Oracle в `config/connections.json`

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

### 3. Полный перезапуск backend

Thick mode инициализируется при старте процесса (`bootstrap_oracle_client()` в `main.py`).

После изменения `config/connections.json`:

1. Остановите все процессы backend (Ctrl+C; на Windows проверьте, не остались ли лишние `python.exe` после hot-reload).
2. Запустите uvicorn заново.

Одного hot-reload может быть недостаточно — Oracle client может не переинициализироваться.

### 4. Файлы часовых поясов (`ORA-01804`)

При ошибке `ORA-01804: failure to initialize timezone information`:

- **Сначала попробуйте:** оставить `"ora_tzfile": null` в `config/app.json`.
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

Три сценария — выберите под задачу:

| Сценарий | Когда использовать | UI | Backend |
| -------- | ------------------ | -- | ------- |
| [Разработка](#разработка-два-терминала) | Активная работа над кодом, hot-reload | `:5173` (Vite) | `:8080` (uvicorn `--reload`) |
| [Docker](#docker) | Деплой, демо, окружение без Python/Node | `:8080` | в контейнере |
| [Локальный production](#локальный-production) | Прод без Docker | `:8080` | `:8080` (статика из `frontend/dist`) |

Конфиг для всех сценариев: **`config/app.json`** (глобально) и подключения к БД/LLM (per-user в `data/` через UI или legacy **`config/connections.json`**).

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

### Docker

Один контейнер собирает frontend и запускает backend на порту **8080**. Подходит для деплоя и демо, когда не нужен hot-reload.

**Мультипользовательский режим:** при первом открытии введите логин. Если пользователя нет — система предложит подтвердить создание (защита от опечаток). У каждого пользователя своё пространство: DTD, пресеты, алиасы БД/LLM. Глобальные настройки Oracle — в `config/app.json`.

**Требования:** Docker и Docker Compose.

1. Подготовьте глобальную конфигурацию:

```bash
copy config\app.json.example config\app.json
mkdir data
```

При первом старте `session_secret` сгенерируется автоматически и сохранится в смонтированный `config/app.json`. На production передайте свой ключ: `SESSION_SECRET` в `docker-compose.yml` или `.env`.

В Docker `localhost` указывает на сам контейнер. Для сервисов на хосте (PostgreSQL, Ollama и т.д.) используйте `host.docker.internal` при настройке алиасов в UI (**Настройки**) или в per-user `connections.json`.

2. Соберите и запустите:

```bash
docker compose up --build -d
```

Откройте [http://localhost:8080](http://localhost:8080) и войдите под своим логином.

**Полезные команды:**

```bash
docker compose logs -f app    # логи
docker compose down           # остановка
docker compose up --build     # пересборка после изменений кода
```

**Тома:** `config/` (глобальные настройки) и `data/` (пользователи, их DTD и пресеты) монтируются с хоста.

**Миграция со старой single-user версии:** при первой регистрации пользователя legacy-данные из корневых `dtd_schemas/`, `presets/`, `mapping_presets/` и `config/connections.json` автоматически копируются в его пространство (один раз).

**Oracle в Docker (без volume):**

1. Скачайте `instantclient-basic-linux.x64-19.31.0.0.0dbru.zip`.
2. Положите архив в `docker/oracle/` (не распаковывайте).
3. Пересоберите контейнер:
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

Во время сборки `Dockerfile` автоматически распакует клиент в `/opt/oracle/instantclient`.

В `config/app.json` укажите:

```json
{
  "oracle_client_lib_dir": "/opt/oracle/instantclient",
  "oracle_home": "/opt/oracle/instantclient",
  "ora_tzfile": null
}
```

И добавьте алиас Oracle с `host: "host.docker.internal"` (или именем сервиса в compose-сети).

> Для Docker не указывайте `ora_tzfile` вручную (оставьте `null`) — иначе Instant Client может не найти timezone-файл внутри контейнера.

### Локальный production

Альтернатива Docker: один процесс uvicorn раздаёт собранный frontend. Подходит, когда Docker недоступен.

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Откройте [http://localhost:8080](http://localhost:8080)

## Тесты

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Решение проблем


| Симптом                                  | Вероятная причина                      | Что сделать                                                                                          |
| ---------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `Unsupported database driver: oracle`    | Старый backend или неверный `driver`   | Укажите `"driver": "oracle"`, переустановите зависимости, перезапустите                              |
| `DPY-3010` / thin mode                   | Oracle 11g без Instant Client          | Установите Instant Client, задайте `oracle_client_lib_dir`, полный перезапуск                        |
| `Oracle thick mode failed to initialize` | Неверный путь или нет `oci.dll`        | Исправьте `oracle_client_lib_dir`, проверьте наличие `oci.dll`                                       |
| `ORA-01804`                              | Отсутствует или неверный timezone-файл | Сначала `"ora_tzfile": null`; если задаёте файл — только тот, что есть локально в `oracore\zoneinfo` |
| `Database alias '…' not found`           | Опечатка или нет `config/connections.json` | Скопируйте example, проверьте совпадение алиаса с пресетом                                           |
| DTD пропала после перезапуска            | Пустая `dtd_schemas/`                  | Загрузите снова; папка должна сохраняться между запусками                                            |


В логах backend при ошибках есть контекст: алиас, driver, host, усечённый SQL. Для подробностей задайте `"log_level": "DEBUG"` в `config/app.json` → `app`.