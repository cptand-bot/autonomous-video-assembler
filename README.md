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

Поиск источников реализован водопадом: Яндекс → Google → Internet Archive в крайнем случае. DVIDS, Openverse, Flickr, Wikimedia Commons и DuckDuckGo не используются. Результаты веб-поиска — только ссылки на страницы и не считаются лицензированными кадрами.

Георадар подключается только на чтение через Google Sheets API. Репозиторий использует таблицу `GEO2_ARCHIVE_TEST` по ID `1BuaBPZQyIkpzXnRGK3cbIsLqRcTJy_sPR49_dDx71o4`; ключ сервисного аккаунта передаётся через GitHub Secret `GOOGLE_SERVICE_ACCOUNT_JSON`, а не хранится в коде. Адаптер `assembler/georadar.py` подтягивает `Archive` и связанные `AuthorNotes`, `AuthorReasoning`, `Productions`; запись в Google Drive не выполняется.

`images/manifest.json` хранит для каждого кадра `status: ok | placeholder | FAILED`, источник, тип и путь. Self-check не пропускает `placeholder` и `FAILED`. Любая правка кадра или overlay инвалидирует прежнее утверждение в `approval.json`.

Полный pipeline имеет отдельный gate утверждения:

```powershell
python -m assembler.pipeline --root build
python -m assembler.pipeline --root build --approve --captions --audio voice.mp3 --output build/output.mp4
```

Без `--approve` создаётся только `pipeline_state.json` со статусом `review_required`; MP4 не собирается.

В Actions review-файлы и финальный MP4 публикуются разными артефактами. Финальный артефакт имеет короткий срок хранения и содержит только MP4 и манифесты рендера.

## Guards (`assembler/guards.py`)

The pipeline reproduces the path; `guards.py` carries the filters that reject
bad material before a human sees it. Every threshold comes from a measurement
on real builds:

| guard | what it refuses | why |
|---|---|---|
| `filter_candidates` | hosts that only return watermarked stock, catalogue shots on white or AI pictures | these pass an "is it a real photo" check at thumbnail size |
| `load_bans` / `banned_files` | a frame banned earlier, anywhere in the build | a banned frame returns through the **cache**, not through search; and the list changes while a build is in flight |
| `quality_warnings` | width under 1600 px, density under 0.08 B/px | a narrow frame is stretched to 1920 and the person stops being recognisable |
| `lint_query` | ~13 classes of query that reliably return junk, plus non-Russian press queries | the defect is ordered *by the query*, so it cannot be audited away afterwards |
| `cross_check_queries` | the same query on two layers | search honestly returns one file for one meaning |
| `repeated_objects` | one object ordered many times with different wording | 35 scenes out of 69 on five objects, with 64 of 64 query strings unique |
| `storyboard_warnings` | scene count against narration, card spacing, stock share | the storyboard is where cheap fixes live; after the fetch they cost rounds |
| `check_round` / `record_round` | a third fix round, and a reworded query on an already-replaced scene | a round costs ~3 min regardless of size, and a quarter of replacements were rewordings |

`validate.storyboard_review(payload, narration_sec)` answers "is this a
storyboard we can shoot", separately from `validate_payload`, which answers "is
this file well-formed". `selfcheck.check_job` runs the ban sweep and the
quality sweep last, on purpose.
