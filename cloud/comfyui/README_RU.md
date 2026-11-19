# Comixes Cloud ComfyUI — production без Qwen Image

В этом комплекте Qwen Image, Qwen Image Edit и Noct-Q полностью отключены. Для финальных пикселей используются три production-ветки:

- **WAI Illustrious SDXL v17** — основная ветка для 2D, anime, comic, painterly и другой авторской рисовки. Одна character+style LoCon применяется и к SFW, и к NSFW кадрам.
- **официальный MiniMax-H3-Image** — более сильная замена Qwen Image для фото/realistic 3D, когда важнее точность референса, детализация и редактирование. Это нативный 33B image/edit checkpoint: 5090 получает W4A8/NVFP4 профиль на 8 МП, RTX 6000 Pro — BF16 на 16 МП.
- **10Eros-Max MiniMax H3** — специализированная ветка сложных взаимодействий. RTX 5090 получает HQ activation-learned checkpoint, RTX 6000 Pro — полный 40.27-ГБ checkpoint и BF16 decode VAE.

Это не схема «сначала поза, потом перерисовать». Каждый готовый кадр считается одним sampling workflow. Reference/IPAdapter и ControlNet, если включены, входят в тот же проход.

> H3 upstream использует Qwen3-VL как текстовый энкодер команд. Это не Qwen Image и он не рисует пиксели. Если нужен абсолютный запрет любого Qwen-компонента, запускайте provisioning с `INSTALL_H3=0 INSTALL_H3_IMAGE=0`: WAI-ветка не содержит Qwen вообще.

## Workflow

| Файл | Назначение |
|---|---|
| `workflows/wai_v17_train_character_style_locon.json` | обучение одной LoCon внешности + рисовки, 1024 px, rank 32, snapshots 400/800/1200/1600 |
| `workflows/wai_v17_lora_hq_onepass.json` | основной рендер WAI v17 с обученной LoCon, 1024×1344 + latent hires 1.5× |
| `workflows/wai_v17_reference_hq_onepass.json` | однопроходный WAI v17 до обучения LoCon: IPAdapter переносит рисовку/внешность внутри sampling |
| `workflows/h3_eros_5090_hq_image_edit_refmods.json` | 10Eros-Max H3 production для RTX 5090 |
| `workflows/h3_eros_6000_bf16_image_edit_refmods.json` | полноточный 10Eros-Max H3 для RTX 6000 Pro 96 ГБ |
| `workflows/h3_image_5090_w4a8_hq_edit.json` | официальный MiniMax-H3-Image W4A8/NVFP4, 8 МП, RTX 5090 |
| `workflows/h3_image_6000_bf16_hq_edit.json` | официальный MiniMax-H3-Image BF16, 16 МП, RTX 6000 Pro |

Provisioning устанавливает только H3-профиль выбранной GPU. Оба WAI workflow одинаковы на 5090 и 6000 Pro.

## Ресурсы

### RTX 5090, 32 ГБ

- 64–96 ГБ RAM и swap;
- около 95 ГБ диска для WAI + 10Eros + официального H3-Image;
- WAI: batch 1, 1024×1344, hires 1.5×;
- 10Eros H3: начинайте с 4 МП и batch 1; официальный H3-Image workflow настроен на 8 МП.

### RTX 6000 Pro, 96 ГБ

- желательно 128 ГБ RAM;
- около 190 ГБ диска для полного комплекта;
- WAI LoCon можно обучать на 1024 px rank 32/64;
- 10Eros H3 проверяйте в диапазоне 4–8 МП; официальный H3-Image BF16 workflow настроен на 16 МП.

## Установка

### Что Provisioning Script делает сам

На чистом Ubuntu/Debian GPU-сервере скрипт самостоятельно:

1. Проверяет доступность NVIDIA GPU и соответствие VRAM профилю `rtx5090` или `rtx6000`.
2. Через `apt-get` ставит системные зависимости: Python 3/venv/pip, git, curl, ffmpeg, build-essential,
   cmake/ninja и библиотеки OpenGL/GLib, нужные OpenCV и custom nodes.
3. Создаёт отдельный Python venv (`/venv/main`, если он уже существует, иначе
   `${WORKSPACE}/.venv`) и обновляет pip/setuptools/wheel.
4. Клонирует и закрепляет ComfyUI на заданном `COMFYUI_REF`, затем ставит его Python requirements.
5. Клонирует все нужные custom nodes на закреплённых commits и ставит requirements каждого узла.
6. Для H3 устанавливает требуемый PyTorch/CUDA wheel; для WAI — зависимости обучения LoCon,
   включая diffusers/peft/bitsandbytes.
7. Скачивает выбранные checkpoints, encoders, VAE, IPAdapter, ControlNet и upscaler. Каждая загрузка
   возобновляется из `.part`, проверяется по точному размеру и SHA-256.
8. Создаёт `canonical.png` и `pose_placeholder.png`, устанавливает только workflow выбранного GPU-профиля
   в `ComfyUI/user/default/workflows/comixes` и удаляет устаревшие управляемые Qwen/Noct workflow.
9. Запускает ComfyUI на `0.0.0.0:${PORT}`. При `PROVISION_ONLY=1` только готовит сервер и завершает работу.

Модели, Python-пакеты, custom nodes или workflow вручную доустанавливать не нужно.

### Что должно предоставить облако

Скрипт намеренно не пытается устанавливать драйвер ядра NVIDIA внутри контейнера. До запуска нужны только:

- Linux x86-64 с уже проброшенным NVIDIA runtime (`nvidia-smi` работает);
- RTX 5090 с 32 ГБ либо RTX 6000 Pro с 80+ ГБ VRAM;
- достаточно RAM, диска и доступ в интернет;
- root/passwordless sudo для действительно чистого образа. На готовом ComfyUI-образе sudo не требуется,
  если Python 3, git, curl, ffmpeg и build tools уже установлены;
- принятые вами license flags и, при rate limit Hugging Face, `HF_TOKEN`.

### Запуск из полного bundle

Если весь репозиторий уже находится, например, в `/workspace/comixes-workflow`:

```bash
export WORKSPACE=/workspace
export GPU_PROFILE=rtx5090        # либо rtx6000
export INSTALL_WAI=1
export INSTALL_H3=1              # 10Eros interaction profile
export INSTALL_H3_IMAGE=1        # official high-fidelity still-image model
export ACCEPT_WAI_LICENSE=1
export ACCEPT_MINIMAX_H3_LICENSE=1
export ACCEPT_MINIMAX_H3_IMAGE_LICENSE=1
export HF_TOKEN=""                # желательно для стабильной загрузки HF

bash /workspace/comixes-workflow/cloud/comfyui/PROVISIONING_SCRIPT.sh
```

### Запуск одного raw-скрипта

Raw-URL загружает только сам `.sh`, поэтому скрипту нужен URL репозитория, из которого он автоматически
заберёт workflow, Comixes custom node и тренер LoCon. Никакого ручного копирования после этого не требуется:

```bash
export WORKSPACE=/workspace
export COMIXES_REPO_URL=https://github.com/OWNER/REPOSITORY.git
export COMIXES_REF=PINNED_COMMIT_OR_TAG
export GPU_PROFILE=rtx6000
export INSTALL_WAI=1 INSTALL_H3=1 INSTALL_H3_IMAGE=1
export ACCEPT_WAI_LICENSE=1
export ACCEPT_MINIMAX_H3_LICENSE=1
export ACCEPT_MINIMAX_H3_IMAGE_LICENSE=1

curl -fsSL https://raw.githubusercontent.com/OWNER/REPOSITORY/BRANCH/cloud/comfyui/PROVISIONING_SCRIPT.sh \
  -o /tmp/comixes-provision.sh
bash /tmp/comixes-provision.sh
```

Если скрипт и bundle лежат в одном уже клонированном репозитории, `COMIXES_REPO_URL` не нужен. Для
принудительной повторной проверки/обновления используйте `FORCE_PROVISION=1`. Обычный повторный запуск
идемпотентен: корректные файлы не скачиваются заново.

Только WAI без любого Qwen-компонента:

```bash
INSTALL_WAI=1 INSTALL_H3=0 INSTALL_H3_IMAGE=0 GPU_PROFILE=rtx5090 \
ACCEPT_WAI_LICENSE=1 \
bash cloud/comfyui/PROVISIONING_SCRIPT.sh
```

Только 10Eros-Max H3:

```bash
INSTALL_WAI=0 INSTALL_H3=1 INSTALL_H3_IMAGE=0 GPU_PROFILE=rtx6000 \
ACCEPT_MINIMAX_H3_LICENSE=1 \
bash cloud/comfyui/PROVISIONING_SCRIPT.sh
```

Только официальный MiniMax-H3-Image без 10Eros:

```bash
INSTALL_WAI=0 INSTALL_H3=0 INSTALL_H3_IMAGE=1 GPU_PROFILE=rtx6000 \
ACCEPT_MINIMAX_H3_IMAGE_LICENSE=1 \
bash cloud/comfyui/PROVISIONING_SCRIPT.sh
```

Только подготовка без запуска:

```bash
PROVISION_ONLY=1 GPU_PROFILE=rtx6000 \
ACCEPT_WAI_LICENSE=1 ACCEPT_MINIMAX_H3_LICENSE=1 ACCEPT_MINIMAX_H3_IMAGE_LICENSE=1 \
bash cloud/comfyui/PROVISIONING_SCRIPT.sh
```

Скрипт закрепляет commits ComfyUI/custom nodes, URL моделей, размеры и SHA-256. Незавершённая загрузка остаётся в `.part` и возобновляется. Существующий файл неверного размера не удаляется автоматически.

## Подготовка character+style LoCon

LoCon здесь намеренно обучает не только attention, но и convolution-блоки UNet. Старый attention-only тренер запоминал лицо, но позволял базовой WAI-модели переписать толщину контура, шейдинг и форму тела.

1. Подготовьте минимум 8, лучше 16–30 одобренных кадров одного взрослого персонажа в одной рисовке.
2. Положите изображения в `datasets/<name>/images`.
3. Рядом с каждым изображением должен лежать одноимённый `.txt`. Первая часть каждой подписи — один неизменный trigger, например `chr_katara`.
4. Не подписывайте словами особенности рисовки, которые должна поглотить LoCon: trigger должен связать и внешность, и визуальную технику. Позу, одежду, ракурс и фон подписывайте.
5. Создайте/обновите `characters/<character>.json`: `name`, `trigger`, `age >= 21`, `anatomy`, `style`, `lora`.
6. Откройте `wai_v17_train_character_style_locon.json`, выберите карточку и запустите. На RTX 5090 начинайте с rank 32; на RTX 6000 Pro можно сравнить rank 32 и 64.
7. Сравните snapshots 400/800/1200/1600 на одном seed. Выбирайте не последний автоматически, а тот, где лицо и линии уже совпали, но ещё не копируются позы датасета.

## Основной WAI v17 workflow

`wai_v17_lora_hq_onepass.json` настроен по рекомендациям автора WAI v17:

- Euler ancestral;
- 30 базовых шагов, CFG 6;
- исходный кадр 1024×1344;
- latent hires 1.5×, 20 шагов, denoise 0.4;
- короткий negative prompt — длинные списки ухудшают детализацию и дают blur;
- одна и та же LoCon и один checkpoint для SFW/NSFW.

ControlNet по умолчанию имеет strength 0. Для заданной позы загрузите pose reference и поднимите strength примерно до 0.55–0.75. Это всё ещё один sampling pipeline, а не промежуточная генерация.

## WAI reference workflow до LoCon

`wai_v17_reference_hq_onepass.json` нужен только для подготовки первых SFW-ракурсов:

- замените `canonical.png` своим референсом;
- IPAdapter starts at 0 и заканчивается на 0.60 с весом 0.32;
- не поднимайте вес выше 0.5 без сравнения: иначе он начинает копировать исходную позу и композицию;
- после качественной LoCon используйте основной `wai_v17_lora_hq_onepass.json`, не складывайте сильный IPAdapter и сильную LoCon одновременно.

## 10Eros-Max H3

H3 оставлен только как специализированная ветка фото/3D:

- 8 steps, Euler, scheduler `beta_57`;
- P-H3 edit LoRA strength 1.0;
- LynnReal VAE для RefMod encode;
- P-H3 VAE выбранного GPU-профиля для финального decode;
- RefMod создаётся один раз из 2–4 согласованных ракурсов и переиспользуется.

Для рисованного 2D персонажа не переключайтесь на H3 только ради анатомии: это снова приведёт к изменению rendering medium. Используйте WAI v17 + character/style LoCon.

## Официальный MiniMax-H3-Image

Это нативная still-image модель, а не P-H3 адаптер поверх видеомодели. Она поддерживает единый text-to-image/image-edit checkpoint, до 16 референсов и рабочий диапазон 4–20 МП; производитель рекомендует примерно 16 МП. В bundled workflow отдельный prompt-expander удалён, поэтому пользовательский prompt идёт прямо в H3 conditioning.

- `h3_image_5090_w4a8_hq_edit.json`: W4A8 DiT, NVFP4-AWQ H3 encoder, 8 МП;
- `h3_image_6000_bf16_hq_edit.json`: BF16 DiT и BF16 H3 encoder, 16 МП;
- для mixed SFW/NSFW датасета не переключайте H3-Image и 10Eros между кадрами: сначала выберите один профиль на фиксированном наборе seed и оставьте его для всего проекта;
- публичные adult-LoRA для нового H3-Image пока ранние и узкие. Они намеренно не ставятся автоматически как «универсальное исправление» без подтверждённого качества.

## Проверка качества без тяжёлого валидатора

Для сравнения достаточно фиксированного набора из 6 seed: портрет, полный рост, сложный ракурс, две фигуры без контакта, две фигуры с контактом и один explicit interaction test только со взрослыми вымышленными персонажами.

Сравнивайте snapshots при одинаковых seed, prompt, CFG и размерах. Не обучайте на кадрах, где изменились лицо, пропорции, толщина линий или материал кожи.

## Лицензии и источники

Это техническая памятка, не юридическое заключение. Перед публикацией/монетизацией проверьте условия каждой модели.

- WAI Illustrious SDXL v17: <https://huggingface.co/feiaitou/waiIllustriousSDXL_v170>
- Illustrious XL base: <https://huggingface.co/OnomaAIResearch/Illustrious-xl-early-release-v0>
- IPAdapter: <https://huggingface.co/h94/IP-Adapter>
- Xinsir Union SDXL ControlNet: <https://huggingface.co/xinsir/controlnet-union-sdxl-1.0>
- PlagueKind H3 ImageEdit + RefMods: <https://huggingface.co/Plaguekind/H3-ImageEdit>
- 10Eros-Max: <https://huggingface.co/TenStrip/10Eros-Max>
- optimized 5090 H3: <https://huggingface.co/LokkenJP/TenEros_Max_optimized_learned>
- P-H3 Image: <https://huggingface.co/PrunaAI/P-H3-Image-Comfy>
- official MiniMax-H3-Image: <https://huggingface.co/MiniMaxAI/MiniMax-H3-Image>
- ComfyUI MiniMax-H3-Image weights: <https://huggingface.co/Comfy-Org/MiniMax-H3-Image>
