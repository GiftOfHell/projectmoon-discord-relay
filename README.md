# Project Moon → Discord Relay

Бесплатный релей постов X и **YouTube Live** в Discord webhooks.

Источники:

- [ProjMoonStudio](https://x.com/ProjMoonStudio)
- [Ham_PangPang](https://x.com/Ham_PangPang) (source id / webhook: `hhpp`)
- [LimbusCompany_B](https://x.com/LimbusCompany_B) (приоритет ~1 мин)
- [YouTube @projectmoonofficial](https://youtube.com/@projectmoonofficial) — **только прямые эфиры**

## Быстрый старт

Подробный план «куда и что заливать»: **[SETUP.md](SETUP.md)**

Локально (опционально):

```powershell
copy .env.example .env
# заполни webhook URL в .env
python run.py --dry-run
python run.py
```

Зависимостей pip нет — только Python 3.10+.

## Структура

```
run.py                 # точка входа
config.json            # аккаунты и webhook env names
relay/                 # код
data/state.json        # что уже отправили (пишет Actions)
.github/workflows/     # минутный прогон на GitHub
SETUP.md               # пошаговая инструкция
```
