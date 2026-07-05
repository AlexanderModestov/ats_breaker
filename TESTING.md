# Запуск тестов

Инструкция по запуску юнит-тестов и бенчмарков проекта hr-breaker.

## Требования

- **uv** — менеджер окружения (`uv run ...` сам поднимет `.venv` и зависимости).
- Для **бенчмарков** (реальные вызовы LLM) — настроенный доступ к Vertex AI:
  - либо переменные `GOOGLE_CLOUD_PROJECT` + `GOOGLE_APPLICATION_CREDENTIALS`,
  - либо service-account JSON в корне репозитория (`hr-breaker-*.json`) — подхватывается автоматически,
  - либо `GOOGLE_APPLICATION_CREDENTIALS_JSON` с содержимым ключа.
  - Опционально: `GOOGLE_CLOUD_LOCATION` (по умолчанию `global`).

---

## 1. Обычные тесты (без LLM)

Быстрые юнит-тесты. Бенчмарки помечены маркером `benchmark` и **пропускаются по умолчанию**.

```bash
# все обычные тесты
uv run pytest

# один файл
uv run pytest tests/test_audit_scoring.py

# один тест
uv run pytest tests/test_audit_scoring.py::test_name -q
```

---

## 2. Бенчмарки (реальные вызовы LLM)

Помечены `@pytest.mark.benchmark`. Запускаются только с флагом `-m benchmark`.
`-s` показывает живой прогресс (без него вывод буферизуется).

Пропускаются, если: нет флага `-m benchmark`, не найдены входные файлы или не настроен Vertex.

Общий вид:

```bash
uv run pytest tests/<файл>.py -s -m benchmark
```

### Входные файлы (локальные, в git не коммитятся)

- **Резюме (CV):** PDF, из которого извлекается текст. По умолчанию `output/Alexander Modestov.pdf`.
- **Вакансии:** текстовый файл, вакансии разделены строкой из `---`.
  По умолчанию `positions.txt`. URL скрейпятся автоматически; свободный текст парсится как есть.

Пример формата файла вакансий:

```
https://example.com/job/123
---
https://example.com/job/456
---
Свободный текст вакансии без URL...
```

---

## 3. Список бенчмарков

| Файл | Что делает |
|------|-----------|
| `test_optimizer_comparison.py` | Сравнивает оптимизаторы v1 vs v2 (скорость + качество), сохраняет финальные PDF. |
| `test_caps_comparison.py` | Сравнивает лимиты итераций 2/3/4/5 — **выводит** их из одного прогона cap=5 (метрики, PDF не сохраняет). |
| `test_caps_cvs.py` | Реально прогоняет цикл на каждом cap 2/3/4/5 и **сохраняет CV для каждого cap** по каждой вакансии. |
| `test_steps_comparison.py` | Сравнение по шагам. |
| `test_flash_comparison.py` | Сравнение flash-модели. |
| `test_iterations_trajectory.py` | Траектория качества по итерациям. |
| `test_pipeline_benchmark.py` | Бенчмарк всего пайплайна. |

Выходные PDF складываются в `output/comparison/` (тоже в git не коммитится).

---

## 4. Пример: CV по каждому cap (2/3/4/5) для своего CV и списка вакансий

Пути к CV и списку вакансий переопределяются переменными окружения
`CAPS_RESUME` и `CAPS_POSITIONS` (по умолчанию — `output/Alexander Modestov.pdf`
и `positions.txt`). Это не трогает исходные файлы.

**bash / Git Bash:**

```bash
CAPS_RESUME="output/CV GM_Пятых ЮА.pdf" CAPS_POSITIONS=positions_edtech.txt \
  uv run pytest tests/test_caps_cvs.py -s -m benchmark
```

**PowerShell:**

```powershell
$env:CAPS_RESUME="output/CV GM_Пятых ЮА.pdf"; $env:CAPS_POSITIONS="positions_edtech.txt"; `
  uv run pytest tests/test_caps_cvs.py -s -m benchmark
```

Результат: для каждой вакансии — 4 файла в `output/comparison/`:

```
<job-slug>_cap2.pdf
<job-slug>_cap3.pdf
<job-slug>_cap4.pdf
<job-slug>_cap5.pdf
```

Плюс в конце печатается таблица (качество %, число итераций, время).
Один прогон = 6 вакансий × 4 cap = до 24 реальных оптимизаций, поэтому идёт долго.

---

## 5. Полезное

```bash
# запустить в фоне с логом
uv run pytest tests/test_caps_cvs.py -s -m benchmark 2>&1 | tee output/run.log

# проверить, что тест собирается (без запуска)
uv run pytest tests/test_caps_cvs.py -m benchmark --collect-only -q
```

- `Fontconfig error: Cannot load default config file` в выводе — безобидный шум
  рендера PDF (WeasyPrint подставляет шрифт по умолчанию), не ошибка.
- Вакансии за логин-стеной (напр. посты LinkedIn) обычно не скрейпятся и
  пропускаются — это отражается в логе строкой `SKIPPED`.
