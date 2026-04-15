# Telegram-консультант по файлам из `attach`

Проект поднимает:
- Telegram-бота на `aiogram`.
- Админ-панель на `FastAPI` для управления файлами в `attach` (добавление/удаление + переиндексация).
- Интеграцию с Vertex AI через `GOOGLE_API_KEY`.

## 1. Настройка

1. Скопируйте пример env:
```bash
cp .env.example .env
```
2. Заполните обязательные значения в `.env`:
- `BOT_TOKEN`
- `GOOGLE_API_KEY`
- `ADMIN_TOKEN`
- `VERTEX_PROJECT` (ID проекта GCP)
- `VERTEX_LOCATION` (например, `us-central1`)
- `VERTEX_MODEL` (например, `gemini-2.5-flash`)

## 2. Локальный запуск (без Docker)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Рекомендуется именно Python `3.13` (не `3.14`), чтобы избежать проблем со сборкой зависимостей.

Админка будет доступна на:
- `http://localhost:8080/admin` (или ваш `ADMIN_PORT`)

## 3. Запуск в Docker

```bash
docker compose up --build -d
```

Проверка логов:
```bash
docker compose logs -f
```

## 4. Как работает консультация

1. Бот читает все файлы из `attach` (`.docx`, `.txt`, `.md`, `.pdf`).
2. Текст режется на чанки и индексируется (BM25-поиск).
3. По вопросу выбираются релевантные фрагменты.
4. Эти фрагменты передаются в Vertex-модель, и бот формирует ответ с указанием источников.

## 5. Админ-панель

В админке:
- можно загружать новые файлы в `attach`;
- удалять существующие;
- вручную пересобирать индекс.

После добавления/удаления индекс обновляется автоматически.
