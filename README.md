# Autonomous Video Assembler

Автономный сборщик: SRT → `scenes.json` → review dashboard → проверенные медиа → MP4.

Тяжёлые операции проекта должны выполняться в GitHub Actions. Локальный запуск ниже нужен только для разработки и проверки контракта.

## Запуск прототипа

```powershell
python -m assembler.cli sample/test.srt --channel ПЛАНЕТА --output build
```

Результат появится в `build/scenes.json`, `build/dashboard.html`, `build/review.html` и `build/manifest.json`.

## Проверка

```powershell
python -m unittest discover -s tests -v
```

## Контракт первого этапа

Входом является SRT. Сцены не перекрываются, начинаются с нулевой секунды и заканчиваются на последнем таймкоде. `manifest.json` фиксирует готовность job и позволяет следующему шагу продолжить работу по файлам, а не по состоянию чата. На этом этапе визуальные поля создаются как безопасные placeholders; поиск материалов добавляется следующим этапом.

Поиск источников реализован водопадом: сначала Яндекс-веб-поиск, затем DVIDS → Openverse → Flickr CC → Internet Archive → Pexels Video. Wikimedia Commons и DuckDuckGo не используются. Pexels включается переменной окружения `PEXELS_API_KEY`, Flickr — `FLICKR_API_KEY`; ключи не хранятся в репозитории. Результаты веб-поиска — только ссылки на страницы и не считаются лицензированными кадрами.

Георадар подключается только на чтение через Google Sheets API. Репозиторий использует таблицу `GEO2_ARCHIVE_TEST` по ID `1BuaBPZQyIkpzXnRGK3cbIsLqRcTJy_sPR49_dDx71o4`; ключ сервисного аккаунта передаётся через GitHub Secret `GOOGLE_SERVICE_ACCOUNT_JSON`, а не хранится в коде. Адаптер `assembler/georadar.py` подтягивает `Archive` и связанные `AuthorNotes`, `AuthorReasoning`, `Productions`; запись в Google Drive не выполняется.

`images/manifest.json` хранит для каждого кадра `status: ok | placeholder | FAILED`, источник, тип и путь. Self-check не пропускает `placeholder` и `FAILED`. Любая правка кадра или overlay инвалидирует прежнее утверждение в `approval.json`.

Полный pipeline имеет отдельный gate утверждения:

```powershell
python -m assembler.pipeline --root build
python -m assembler.pipeline --root build --approve --captions --audio voice.mp3 --output build/output.mp4
```

Без `--approve` создаётся только `pipeline_state.json` со статусом `review_required`; MP4 не собирается.

В Actions review-файлы и финальный MP4 публикуются разными артефактами. Финальный артефакт имеет короткий срок хранения и содержит только MP4 и манифесты рендера.
