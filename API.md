# Review backend API

Backend job запускается на localhost и хранит состояние в каталоге job.

## Read

`GET /health` — проверка, что отвечает именно автономный сборщик.

`GET /state` — динамическое состояние сцен, кадров, overlays, жёлтых карточек и общего approval.

`GET /images/<file>`, `/videos/<file>`, `/overlays/<file>` — медиа. MP4 поддерживает HTTP Range.

## Frames

`POST /search_opts?id=N`

```json
{"q":"запрос по-русски"}
```

`POST /pick_opt?id=N`

```json
{"full":"https://...","thumb":"https://...","kind":"photo","src":"openverse","target":"scene"}
```

`target` — `scene` или `overlay`. Remote-кандидат скачивается backend’ом, проверяется и записывается в manifest.

`POST /upload?id=N` — бинарный файл изображения в body, имя в `X-Filename`.

`POST /overlay_photo?id=N` — бинарный файл фото-всплывашки.

`POST /keepimg?id=N`, `POST /ban_asset?id=N` — оставить или заблокировать кадр.

## Overlays

`POST /overlay?id=N` — параметры фото-overlay: `sound`, `at`, `shape`, `style`, `anchor`, `scale`, `approved`.

`POST /overlay?id=N&clear=1` — удаляет запись и файл всплывашки.

`POST /overlay_text?id=N` — текст, `color`, `font`, `pos`, `at`, `scale`, `sound`.

`POST /ticker?id=N` — ticker с текстом, временем и звуком.

## Approval and logs

`POST /approve` с `{"approved":true|false}` фиксирует общее решение автора в `approval.json`.

`POST /reject?id=N` пишет обучающий журнал `rejections.jsonl` и не запускает сборку.

Render разрешается только отдельным pipeline-gate `approve=true`.
