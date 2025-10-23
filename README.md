# Gorky Maps API

FastAPI‑сервис для подбора пеших маршрутов по интересам пользователя и доступному времени. Данные берутся из `objects.csv` (список объектов) и `durations.csv` (матрица времени хода между объектами). Возвращаются 3 варианта маршрутов, если удаётся подобрать достаточно разнообразные и валидные варианты.

## Задача

- Принять запрос с интересами пользователя, опциональной геолокацией старта и бюджетом времени на прогулку.
- Отфильтровать объекты по интересам (тегам), извлечь соответствующую подматрицу времени между ними.
- Найти несколько лучших маршрутов с ограничениями по количеству точек и общему времени.
- Вернуть 3 маршрута (списки точек с координатами и описаниями) или объяснимую ошибку, если построить нельзя.

## Структура проекта

- `main.py` — инициализация FastAPI‑приложения, CORS и подключение роутов (`/api`).
- `routes/route_planner.py` — эндпоинт `POST /api/routes`:
  - Загружает объекты и матрицу, фильтрует по интересам,
  - Возвращает до 3 маршрутов либо 404/400 при проблемах.
- `schemas/route.py` — Pydantic‑схемы:
  - `RouteRequest` (interests, user_location?, walking_time),
  - `RouteResponse` (список маршрутов), `RoutePoint`, `Location`.
- `utils/config.py` — конфигурация и переменные окружения (пути к данным/логам, лимиты оптимизации, `ORS_KEY`).
- `utils/logger.py` — настройка логирования в консоль/файл.
- `utils/data_provider.py` — чтение `data/objects.csv` и `data/durations.csv` с кэшированием.
- `utils/route_support.py` — утилиты для матриц/тегов: нормализация, выборка ID по тегам, выделение подматриц.
- `utils/route_optimizer.py` — ядро подбора маршрутов, контроль разнообразия, ограничения по времени/кандидатам.
- `utils/ors_client.py` — интеграция с OpenRouteService для расчёта времени от пользовательской точки старта (по API‑ключу).
- `scripts/route_pipeline.py` — CLI‑пайплайн для локальной проверки подбора маршрутов по CSV.
- `scripts/normalize_xlsx.py` — нормализация выгрузки в `points.csv` (из XLSX/CSV с колонкой WKT `POINT(...)`).
- `scripts/ors_building.py` — построение полной матрицы длительностей через ORS батчами.
- `data/` — входные данные:
  - `objects.csv` — справочник объектов (id, lon, lat, title, description, time, tag, ...),
  - `durations.csv` — квадратная матрица длительностей (секунды), обычно с заголовками по ID.
- `requirements.txt` — зависимости.

## Быстрый старт (Docker)

- Подготовка: скопируйте `.env.example` в `.env` и заполните при необходимости (`ORS_KEY`, `GIGACHAT_CLIENT_ID`, `GIGACHAT_CLIENT_SECRET`).
- Запуск API: `make up` (для остановки: `make down`, перезапуск: `make restart`)
- Откройте Swagger UI: `http://localhost:8000/docs`

Примечания:
- В контейнер пробрасывается только каталог данных `./data` как том (`./data:/app/data`). Логи не сохраняются на хосте.
- Сервер запускается через `uvicorn` на порту `8000`.

Приложение поднимет `/api` с CORS и роутом `/api/routes`.

## API

- Метод: `POST /api/routes`
- Тело запроса (`application/json`):

```
{
  "interests": ["ARCHITECTURE", "URBAN_ART"],
  "walking_time": 2.5,          // часы, > 0
  "user_location": {            // опционально, если старт не от объекта
    "latitude": 56.329,
    "longitude": 44.009
  }
}
```

- Успешный ответ: `200 OK`

```
{
  "routes":
    [
      {"latitude": 56.3, "longitude": 44.0, "title": "...", "description": "...", "address": "..."},
      {"latitude": 56.31, "longitude": 44.01, "title": "...", "description": "...", "address": "..."}
    ],
    "explanation": "Маршрут начинается с ..."
}
```

Поле `explanation` может быть опущено

- Возможные ошибки:
  - `404 Not Found` — нет объектов по интересам; недостаточно валидных/разнообразных маршрутов; у точек нет координат.
  - `400 Bad Request` — запрошенные ID отсутствуют в матрице длительностей.

См. реализацию: `routes/route_planner.py`, схемы: `schemas/route.py`.

## Данные

- `objects.csv` — обязательные колонки: как минимум `id`, `lon`, `lat`, а также `tag` для фильтрации по интересам и (опц.) `time` — время на посещение точки (минуты, может быть 0).
- `durations.csv` — длительности между объектами (секунды). Поддерживаются форматы:
  - с заголовками (первая строка/колонка — ID),
  - без заголовков (чистая квадратная матрица). См. парсинг в `utils/route_support.py`.

Где брать матрицу:
- `scripts/ors_building.py` — создаёт полную матрицу через OpenRouteService (нужен `ORS_KEY`).

Как нормализовать исходные выгрузки в CSV:
- `scripts/normalize_xlsx.py` — парсит WKT `POINT(lon lat)` и готовит `points.csv`.

## Переменные окружения

Задаются через `.env` или окружение, читаются в `utils/config.py:1`:

- `DATA_DIR` — путь к каталогу данных (по умолчанию `./data`).
- `LOG_DIR` — путь к каталогу логов (по умолчанию `./logs`).
- `ORS_KEY` — API‑ключ OpenRouteService (нужен для расчёта времени от пользовательской точки старта).
- Тюнинг оптимизатора:
  - `MAX_ROUTE_CANDIDATES` (по умолчанию `12`),
  - `CANDIDATE_EXPANSION_STEP` (по умолчанию `12`),
  - `ROUTE_DIFFERENCE_RATIO` (по умолчанию `0.3`),
  - `MAX_ROUTE_EVALUATIONS` (по умолчанию `20000`),
  - `MAX_COMBINATIONS_PER_LENGTH` (по умолчанию `400`).

## Скрипты CLI

- `scripts/route_pipeline.py` — локальная проверка подбора:

```
python scripts/route_pipeline.py --tags 'ARCHITECTURE,URBAN_ART' \
  --max-time 120 \
  --objects-path data/objects.csv \
  --durations-path data/durations.csv
```

- `scripts/normalize_xlsx.py` — подготовка `points.csv` из XLSX/CSV:

```
python scripts/normalize_xlsx.py --input data/cultural_objects_mnn.xlsx \
  --sheet cultural_sites_202509191434 \
  --output data/points.csv
```

- `scripts/ors_building.py` — построение матрицы ORS (нужен `ORS_KEY`):

```
python scripts/ors_building.py data/points.csv --out data/durations.csv
```

## Интеграция GigaChat

- Назначение: генерация краткого описания маршрута на естественном языке.
- Точки входа: `gpt_api/get_description.py` (функция `build_route_explanation`).
- Переменные окружения: задайте `GIGACHAT_CLIENT_ID` и `GIGACHAT_CLIENT_SECRET` в `.env` или как системные переменные (см. шаблон `.env.example`).
- Сетевые требования: по умолчанию используется `verify=False` для HTTPS‑запросов к GigaChat. Для строгой проверки укажите путь к корневому сертификату Сбера и передайте его как `verify` в `build_route_explanation` в `routes/route_planner.py`, либо добавьте сертификат в доверенные корневые в системе.
