# План запуска: X + YouTube Live → Discord (бесплатно)

Локальный проект: `C:\Users\burachonak\projectmoon-discord-relay`  
На GitHub **ещё ничего не залито** — это сделаешь ты по шагам ниже.

## Что получится

| Источник | Куда | Как часто |
|----------|------|-----------|
| `ProjMoonStudio` (X) | webhook #1 | ~каждую минуту |
| `Ham_PangPang` (X) | webhook #2 | ~каждую минуту |
| `LimbusCompany_B` (X) | webhook #3 | ~каждую минуту (важно) |
| `@projectmoonofficial` **только LIVE** | webhook #4 | ~каждую минуту |

Стек: **Python (stdlib) + Discord webhooks + GitHub Actions + cron-job.org**.  
ПК после настройки не нужен.

```
FxTwitter API / RSS          ─┐
YouTube /@handle/live page   ─┼─→  GitHub Action (каждую мин)  →  4 Discord webhooks
cron-job.org триггерит Action─┘
```

---

## Шаг 0. Подготовка Discord (4 webhook)

В своём сервере Discord создай **4 канала** (или используй существующие).

Для **каждого** канала:

1. Шестерёнка канала → **Integrations** → **Webhooks** → **New Webhook**
2. Имя любое (например `X Limbus`)
3. **Copy Webhook URL**
4. Сохрани URL куда-нибудь временно (блокнот)

Нужны 4 URL:

- `DISCORD_WEBHOOK_PROJMOON` ← канал для ProjMoonStudio  
- `DISCORD_WEBHOOK_HAM` ← канал для Ham_PangPang  
- `DISCORD_WEBHOOK_LIMBUS` ← канал для LimbusCompany_B  
- `DISCORD_WEBHOOK_YOUTUBE` ← канал для YouTube live  

> Webhook URL — секрет. Не публикуй его в Issues / чатах.

---

## Шаг 1. (Опционально) Локальный тест на ПК

Только чтобы проверить, что скрипт живой. Потом ПК можно выключить.

1. Скопируй `.env.example` → `.env`
2. Вставь 4 webhook URL в `.env`
3. В терминале:

```powershell
cd C:\Users\burachonak\projectmoon-discord-relay
python run.py --dry-run
```

Первый запуск **ничего не шлёт** в Discord — только запоминает текущие посты (`data/state.json`), чтобы не заспамить историю.

Потом обычный прогон:

```powershell
python run.py
```

Проверка одного источника:

```powershell
python run.py --only limbus
python run.py --only youtube_pm
```

> Если с домашнего IP FxTwitter отвечает 404 — это бывает. На GitHub Actions (серверы в США) обычно работает. Локальный фейл X не значит, что на Actions будет плохо.

---

## Шаг 2. Создать репозиторий на GitHub

1. Зайди на https://github.com/new  
2. Имя, например: `projectmoon-discord-relay`  
3. Visibility: **Private** (рекомендуется — там будет state и история)  
4. **Не** добавляй README/license (у нас уже есть файлы)  
5. Create repository  

---

## Шаг 3. Залить этот проект на GitHub

В PowerShell:

```powershell
cd C:\Users\burachonak\projectmoon-discord-relay

git add .
git status
git commit -m "Initial Project Moon Discord relay"

# подставь СВОЙ URL репозитория:
git remote add origin https://github.com/ТВОЙ_ЛОГИН/projectmoon-discord-relay.git
git branch -M main
git push -u origin main
```

Если GitHub попросит логин — удобнее Personal Access Token или GitHub CLI (`gh auth login`).

---

## Шаг 4. Secrets в GitHub

1. Репозиторий → **Settings** → **Secrets and variables** → **Actions**  
2. **New repository secret** — создай ровно эти 4 имени:

| Name | Value |
|------|-------|
| `DISCORD_WEBHOOK_PROJMOON` | URL webhook #1 |
| `DISCORD_WEBHOOK_HAM` | URL webhook #2 |
| `DISCORD_WEBHOOK_LIMBUS` | URL webhook #3 |
| `DISCORD_WEBHOOK_YOUTUBE` | URL webhook #4 |

Имена должны совпадать **буква в букву** с `config.json` / workflow.

---

## Шаг 5. Включить GitHub Actions

1. Вкладка **Actions** в репозитории  
2. Если GitHub спросит разрешение на workflows — **Enable**  
3. Найди workflow **Project Moon Discord Relay**  
4. **Run workflow** → Run (ручной тест)

В логе должно быть что-то вроде:

```
[limbus] initialized with N posts (no send)
[youtube_pm] initialized (live=no; no send)
done: sent=0 failures=0
```

Второй ручной Run уже будет ловить только **новые** посты.

Проверь, что в репозитории появился коммит `chore: update relay state` и файл `data/state.json`.

---

## Шаг 6. Надёжный тик каждую минуту (cron-job.org)

Встроенный `schedule: * * * * *` у GitHub **часто опаздывает** (иногда на несколько минут).  
Для Limbus это плохо — поэтому ставим внешний бесплатный cron.

1. Зарегистрируйся на https://cron-job.org (бесплатно)  
2. Создай **Personal Access Token** на GitHub:  
   https://github.com/settings/tokens  
   - Classic token → scope **`repo`** (для private repo)  
   - Или fine-grained: доступ к этому репо + Actions: Read and write  
3. В cron-job.org → Create cronjob:

**Title:** `Project Moon Relay`  

**URL:**
```
https://api.github.com/repos/ТВОЙ_ЛОГИН/projectmoon-discord-relay/actions/workflows/relay.yml/dispatches
```

**Schedule:** Every minute (`* * * * *`)

**Request method:** `POST`

**Headers:**

```
Accept: application/vnd.github+json
Authorization: Bearer ТВОЙ_GITHUB_TOKEN
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

**Body:**
```json
{"ref":"main"}
```

4. Save → Enable  

После этого Actions будет стартовать примерно каждую минуту.

> Лимит бесплатных минут GitHub: для **private** репо у бесплатного аккаунта есть месячный пакет. Один прогон ~10–20 сек → порядка **~7–15 часов/мес**. Обычно хватает. Если упрёшься в лимит — сделай репо **Public** (Actions бесплатны для public) и не клади секреты в код (они и так в Secrets).

---

## Шаг 7. Проверка «в бою»

1. Дождись нового поста Limbus / ProjMoon / Ham — должен появиться embed в нужном канале.  
2. YouTube: уведомление уйдёт **только когда канал реально в эфире** (`/@projectmoonofficial/live`). Обычные видео и премьеры без live — игнор.  
3. Один и тот же эфир не дублируется. Новый эфир после окончания предыдущего — снова уведомит.

---

## Куда что «заливается» (кратко)

| Куда | Что |
|------|-----|
| **Discord** | Только 4 webhook URL (настройки каналов) |
| **GitHub репозиторий** | Весь этот проект (код + workflow) |
| **GitHub Secrets** | 4 webhook URL |
| **cron-job.org** | POST на GitHub API раз в минуту + твой GitHub token |
| **ПК** | Ничего постоянно. Можно удалить папку после `git push` |

Никакого «сайта» не нужно. GitHub Actions = бесплатный раннер скрипта.

---

## Настройки под себя

Файл `config.json`:

- поменять каналы / хендлы  
- `exclude_replies` / `exclude_reposts`  
- цвет embed (`color`)  
- для YouTube: `"mention_everyone": true` — если нужен пинг `@everyone` при старте стрима  

После правок:

```powershell
git add config.json
git commit -m "Update relay config"
git push
```

---

## Если сломается

| Симптом | Что проверить |
|---------|----------------|
| Actions красный, Discord webhook missing | Secrets названы правильно? |
| X: Failed to fetch @handle | Временный даун FxTwitter. Подожди / смотри логи. В `config.json` уже есть запасные `fxtwitter_hosts` / `rss_hosts` |
| Посты дублируются | Не удаляй `data/state.json` без нужды; не делай `git reset` этого файла |
| Задержка > 2–3 мин | Работает ли cron-job.org? Смотри историю job |
| YouTube не ловит эфир | Открой `youtube.com/@projectmoonofficial/live` в браузере — страница должна показывать live. Парсер ищет `isLiveNow` |
| Git push state failed | У ветки `main` не должно быть запрета на push от `github-actions` |

---

## Чего сознательно нет

- Официального X API (платный)  
- Постоянного VPS / «сайта»  
- Уведомлений о обычных YouTube-видео (только live)  
- Гарантии «в ту же секунду» — цель: **в ту же минуту**
