# GitHub Actions setup

Репозиторий не требует Cloud Code для запуска. Workflow `.github/workflows/test-srt-dashboard.yml` запускается вручную через `workflow_dispatch`.

## Secrets

- `PEXELS_API_KEY` — необязательный ключ Pexels Video.
- `FLICKR_API_KEY` — необязательный ключ Flickr API.

DVIDS, Openverse, Internet Archive, Wikimedia Commons и web search работают без ключей. Ключи добавляются только в GitHub Settings → Secrets and variables → Actions и не коммитятся.

## Inputs

- `srt_path` — путь к SRT внутри репозитория;
- `audio_path` — необязательный путь к MP3 внутри репозитория;
- `channel` — имя канала;
- `approve` — `false` для получения review-артефакта, `true` только после проверки кадров.

При `approve=false` Actions публикует `storyboard` и `review` на один день. При `approve=true` после self-check публикуется только `final-video` с MP4 и render manifest, также на один день.

## Первый запуск

1. Создать public repository и добавить содержимое этого каталога.
2. Добавить secrets при необходимости.
3. Запустить `Autonomous video pipeline` с `approve=false`.
4. Проверить review-артефакт и повторить запуск с `approve=true`.

Локальный ПК используется только для git и просмотра артефактов; поиск, скачивание и FFmpeg выполняются на GitHub runner.
