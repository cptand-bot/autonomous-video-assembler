# Autonomous Video Assembler

Первый вертикальный прототип автономного сборщика: SRT → `scenes.json` → статический dashboard.

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

Поиск источников реализован через адаптеры Openverse, Wikimedia Commons, Internet Archive и Pexels Video. Pexels включается переменной окружения `PEXELS_API_KEY`; ключи не хранятся в репозитории.

Полный pipeline имеет отдельный gate утверждения:

```powershell
python -m assembler.pipeline --root build
python -m assembler.pipeline --root build --approve --captions --audio voice.mp3 --output build/output.mp4
```

Без `--approve` создаётся только `pipeline_state.json` со статусом `review_required`; MP4 не собирается.

В Actions review-файлы и финальный MP4 публикуются разными артефактами. Финальный артефакт имеет короткий срок хранения и содержит только MP4 и манифесты рендера.
