"""Промпты для взрослых оригинальных персонажей в западном 2D-стиле."""

from __future__ import annotations

import json
import re
from pathlib import Path

from comixes_lib.paths import CHARACTERS, PROJECT

WAI_QUALITY = "masterpiece, best quality, amazing quality"
ADULT_MIN_AGE = 21

WAI_FLAT_NEGATIVE = (
    "painterly, photorealistic, photo, 3d, cgi, sketch, monochrome, greyscale, "
    "silhouette, neon, neon green, green background, lime background, yellow outline, green outline, glowing outline, "
    "4koma, 2koma, multiple panels, split screen, split image, character sheet, multiple views, "
    "comic panel border, subtitles, caption, letters, writing, kanji, hiragana, screenshot, "
    "asymmetrical eyes, uneven eyes, extra eyes, bad hands, extra fingers"
)
COMMON_NEGATIVE = (
    "bad anatomy, bad hands, extra limbs, extra arms, extra legs, extra fingers, missing fingers, "
    "fused fingers, mutated, deformed, malformed, blurry, lowres, watermark, text, signature, "
    "speech bubble, photorealistic, photo, 3d, cgi, render, multiple views, split screen, "
    "comic panel border, extra person, crowd, 3girls, 3boys, "
    "bad eyes, asymmetrical eyes, uneven eyes, missing eye, extra eyes, cross-eyed, "
    "deformed eyes, mismatched eyes"
)

BANNED_PHRASES = (
    "tony",
)
BANNED_WORDS = (
    "minor",
)

CLOTHED_VIEWS = [
    ("01_front_full", "rating_safe", "front view, full body, standing, neutral expression, arms at sides, both eyes visible, symmetrical eyes, simple grey background, clothed, wearing {outfit}"),
    ("02_three_quarter", "rating_safe", "three-quarter view, full body, standing, neutral expression, simple grey background, clothed, wearing {outfit}"),
    ("03_side", "rating_safe", "side view, full body, standing, neutral expression, simple grey background, clothed, wearing {outfit}"),
    ("04_back", "rating_safe", "back view, full body, standing, simple grey background, clothed, wearing {outfit}"),
    ("05_portrait", "rating_safe", "front view, portrait, head and shoulders, slight smile, both eyes visible, symmetrical eyes, simple grey background, clothed"),
    ("06_portrait_3q", "rating_safe", "three-quarter view, portrait, head and shoulders, serious expression, both eyes visible, symmetrical eyes, simple grey background, clothed"),
    ("07_sitting", "rating_safe", "front view, full body, sitting on a stool, neutral expression, simple grey background, clothed, wearing {outfit}"),
    ("08_arms_up", "rating_safe", "front view, full body, standing, arms raised, simple grey background, clothed, wearing {outfit}"),
    ("09_walking", "rating_safe", "full body, walking toward viewer, front view, simple grey background, clothed, wearing {outfit}"),
    ("10_over_shoulder", "rating_safe", "three-quarter view, full body, looking back over the shoulder, simple grey background, clothed, wearing {outfit}"),
    ("11_high_angle", "rating_safe", "slightly high angle, full body, standing, front view, simple grey background, clothed, wearing {outfit}"),
    ("12_low_angle", "rating_safe", "slightly low angle, full body, standing, front view, simple grey background, clothed, wearing {outfit}"),
]

NUDE_VIEWS = [
    ("13_nude_front", "rating_explicit", "front view, full body, standing, completely naked, no clothes, fully nude, uncensored, bare skin, nipples and vulva visible, coherent anatomy in the same drawing style as the reference, both eyes visible, symmetrical eyes, simple grey background"),
    ("14_nude_three_quarter", "rating_explicit", "three-quarter view, full body, standing, completely naked, no clothes, fully nude, uncensored, bare skin, nipples and vulva visible, coherent anatomy in the same drawing style as the reference, simple grey background"),
    ("15_nude_side", "rating_explicit", "side view, full body, standing, completely naked, no clothes, fully nude, uncensored, bare skin, breasts and buttocks visible, coherent anatomy in the same drawing style as the reference, simple grey background"),
    ("16_nude_back", "rating_explicit", "back view, full body, standing, completely naked, no clothes, fully nude, uncensored, bare back and buttocks visible, coherent anatomy in the same drawing style as the reference, simple grey background"),
    ("17_nude_portrait", "rating_explicit", "front view, portrait, head and bare chest, completely naked, no clothes, fully nude, uncensored, nipples visible, coherent anatomy in the same drawing style as the reference, both eyes visible, symmetrical eyes, simple grey background"),
    ("18_nude_sitting", "rating_explicit", "front view, full body, sitting with knees apart, completely naked, no clothes, fully nude, uncensored, bare skin, nipples and vulva visible, coherent anatomy in the same drawing style as the reference, simple grey background"),
    ("19_oral", "rating_explicit", "side view, close medium shot, two adults, completely naked, no clothes, fully nude, uncensored, the character kneels and performs fellatio, a second adult stands, penis in her mouth, both bodies visible and separate, the penis stays on the standing partner, coherent contact in the same drawing style as the reference, simple grey background"),
    ("20_cowgirl", "rating_explicit", "side view, close medium shot, two adults, completely naked, no clothes, fully nude, uncensored, cowgirl position, the character straddles a reclining second adult, vaginal sex, the partner's penis enters her vulva, both bodies visible and separate, coherent contact in the same drawing style as the reference, simple grey background"),
]
PARTNER_DATASET_VIEWS = {"19_oral", "20_cowgirl"}

# 0 is flat and 5 is gigantic. 1, small, is the default because these models inflate the chest.
BREAST_TAGS = (
    "flat chest",
    "small breasts",
    "medium breasts",
    "large breasts",
    "huge breasts",
    "gigantic breasts",
)
NUDE_POSITIVE = (
    "(completely naked:1.45), (fully nude:1.4), (no clothes:1.4), (no underwear:1.35), "
    "(bare skin:1.3), (nipples:1.25), uncensored"
)
CLOTHES_NEGATIVE = (
    "(clothed:1.45), (clothes:1.4), (dressed:1.4), (clothing:1.4), (shirt:1.35), (jacket:1.35), "
    "(coat:1.3), (pants:1.3), (skirt:1.3), (dress:1.35), (underwear:1.4), (bra:1.4), (panties:1.4), "
    "(lingerie:1.3), (swimsuit:1.3), (bikini:1.3), (covered breasts:1.4), (covered nipples:1.4), "
    "(censored:1.45), (bar censor:1.3), (mosaic censoring:1.3), (pasties:1.25), (towel:1.2)"
)
_CLOTHING_CLAUSE = re.compile(r"(?:,\s*)?\b(?:wears?|wearing|dressed in|clothed in)\b[^,.]*", re.IGNORECASE)
_GARMENT = re.compile(
    r"\b(?:top|shirt|jacket|coat|hoodie|pants|trousers|skirt|dress|uniform|bra|panties|underwear|"
    r"lingerie|swimsuit|bikini|blouse|clothes|outfit|leggings?|boots?|shoes?|sleeves?)\b",
    re.IGNORECASE,
)
_POSE_CLAUSE = re.compile(
    r"^(?:the\s+)?(?:arms?|hands?|legs?|feet|body|head|pose)\b.*\b(?:crossed|raised|lowered|"
    r"folded|extended|bent|at the sides?|behind the back|on the hips?)\b",
    re.IGNORECASE,
)
_FULLY_NUDE = ("completely naked", "fully nude", "completely nude", "no clothes")
_PARTIAL_CLOTHING = (
    "wearing", "lingerie", "bikini", "underwear", "topless", "bottomless", "half-dressed",
    "partially clothed", "open shirt", "open jacket", "pulled down", "pulled aside", "swimsuit",
    "bra", "panties",
)


def clean_prompt(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(?:,\s*)+", ", ", text)
    return text.strip(" ,")


def assert_allowed(text: str) -> None:
    """Отклоняет запросы с несовершеннолетними и каноном детских шоу."""
    low = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            raise ValueError(
                "Промпт отклонён: персонажи только оригинальные и взрослые, 21+. "
                "Стиль задаётся описанием линии и заливки, без имён детских шоу."
            )
    for word in BANNED_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            raise ValueError(
                f"Промпт отклонён из-за «{word}». В сцене только взрослые персонажи 21+."
            )
    for match in re.finditer(r"\b(\d{1,2})\s*(?:years?\s*old|yo|y/o)\b", low):
        if int(match.group(1)) < 21:
            raise ValueError("Возраст персонажа должен быть 21 год или старше.")
    for match in re.finditer(r"\b(?:age|aged)\s*(\d{1,2})\b", low):
        if int(match.group(1)) < 21:
            raise ValueError("Возраст персонажа должен быть 21 год или старше.")


def card_path(name: str) -> Path:
    raw = Path(name)
    if raw.is_file():
        return raw
    candidate = CHARACTERS / raw.name
    if candidate.suffix.lower() != ".json":
        candidate = candidate.with_suffix(".json")
    if not candidate.is_file():
        raise FileNotFoundError(f"Нет карточки персонажа: {candidate}")
    return candidate


def load_card(name: str) -> dict:
    path = card_path(name)
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("trigger", "age_anchor", "appearance"):
        if not str(data.get(key, "")).strip():
            raise ValueError(f"В карточке {path.name} пустое поле {key}.")
    identity = f"{data['age_anchor']} {data['appearance']}"
    assert_allowed(identity)
    if "adult" not in identity.lower():
        raise ValueError("В age_anchor напиши слово adult и возраст, например: adult woman, 28 years old.")
    ages = [int(item) for item in re.findall(r"(\d+)\s*years?\s*old", identity.lower())]
    if not ages or min(ages) < 21:
        raise ValueError("В age_anchor нужен возраст в виде '28 years old', от 21 года.")
    data["_path"] = str(path)
    data.setdefault("lora", "none")
    data.setdefault("lora_strength_model", 0.85)
    data.setdefault("lora_strength_clip", 0.75)
    data.setdefault("default_outfit", "casual clothes")
    data.setdefault("negative_extra", "")
    data.setdefault("style", "")
    data.setdefault("style_preset", "")
    return data


def resolve_style(card: dict, *, characters: bool = True) -> str:
    custom = str(card.get("style") or "").strip()
    if custom:
        return custom
    path = PROJECT / "styles" / "presets.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    presets = data.get("presets") or {}
    name = str(card.get("style_preset") or data.get("active") or "flat_tv").strip()
    if name not in presets:
        known = ", ".join(presets) or "нет ни одного"
        raise ValueError(f"Нет стиля «{name}». В styles/presets.json есть: {known}.")
    base = presets[name]
    if not isinstance(base, str) or not base.strip():
        raise ValueError(f"В пресете «{name}» нужен текст стиля.")
    if not characters:
        return base
    details = (data.get("character_details") or {}).get(name, "")
    if not isinstance(details, str):
        raise ValueError(f"В character_details для «{name}» нужен текст внешности.")
    return clean_prompt(f"{base}, {details}") if details.strip() else base


def dataset_caption(card: dict, scene: str) -> str:
    """Подпись для LoRA: внешность и ракурс, без стиля и без score-тегов."""
    parts = [card["trigger"], card["age_anchor"], card["appearance"], scene]
    caption = clean_prompt(", ".join(str(part) for part in parts if str(part).strip()))
    assert_allowed(caption)
    return caption


def solo_clauses(card: dict, weighted: bool = True) -> tuple[str, str]:
    blob = f"{card['age_anchor']} {card['appearance']}".lower()
    if "woman" in blob or "female" in blob:
        positive = (
            "(1girl:1.6), (woman:1.55), (female:1.45), (solo:1.5), (single character:1.35), one person"
            if weighted
            else "1girl, woman, female, solo, single character, one person"
        )
        return (
            positive,
            "(1boy:1.5), (man:1.4), (male:1.3), (2girls:1.5), (multiple girls:1.4), twins, extra person, duo, two people",
        )
    if re.search(r"\b(man|male)\b", blob):
        positive = (
            "(solo:1.5), (1boy:1.45), (single character:1.35), one person"
            if weighted
            else "solo, 1boy, single character, one person"
        )
        return (
            positive,
            "(2boys:1.5), (multiple boys:1.4), twins, extra person, duo, two people",
        )
    positive = "(solo:1.5), (single character:1.35), one person" if weighted else "solo, single character, one person"
    return positive, "twins, extra person, duo, two people"


def build_prompts(card: dict, scene: str, rating: str, family: str, solo: bool = True,
                  *, external_style: bool = False) -> tuple[str, str]:
    family = family.strip().lower()
    if family != "wai":
        raise ValueError("Для SDXL выберите WAI.")
    if rating not in ("rating_safe", "rating_questionable", "rating_explicit"):
        raise ValueError("Неизвестный rating.")
    solo_positive = ""
    solo_negative = ""
    if solo:
        solo_positive, solo_negative = solo_clauses(card, weighted=False)
    identity = ", ".join(
        part.strip().strip(",")
        for part in (solo_positive, card["trigger"], card["age_anchor"], card["appearance"], resolve_style(card), scene)
        if str(part).strip()
    )
    tone = {
        "rating_explicit": "explicit, nsfw",
        "rating_questionable": "suggestive",
        "rating_safe": "clothed, non-explicit",
    }[rating]
    positive = f"{WAI_QUALITY}, {tone}, {identity}"
    base_negative = "bad quality, worst quality, worst detail, sketch, censor, jpeg artifacts"
    negative_parts = [base_negative, WAI_FLAT_NEGATIVE, COMMON_NEGATIVE, solo_negative, card.get("negative_extra", "")]
    if external_style:
        # Flat-cartoon presets exclude media such as pencil, paint and grayscale.
        common = [tag for tag in COMMON_NEGATIVE.split(", ") if tag not in {"photorealistic", "photo", "3d", "cgi", "render"}]
        negative_parts = [*common, "worst quality, jpeg artifacts, character sheet, reference sheet, turnaround",
                          solo_negative, card.get("negative_extra", "")]
    positive = clean_prompt(positive)
    negative = clean_prompt(", ".join(part for part in negative_parts if str(part).strip()))
    assert_allowed(positive)
    return positive, negative


def breast_size_value(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
        raise ValueError("Размер груди должен быть целым числом от 0 до 5.")
    return value


def breast_tag(size: int) -> str:
    return BREAST_TAGS[breast_size_value(size)]


def breast_prompt(size: int, family: str) -> tuple[str, str]:
    """Weight the chosen chest size and push every other size into the negative."""
    chosen = breast_tag(size)
    avoided = [tag for tag in BREAST_TAGS if tag != chosen]
    if size <= 1:
        avoided.extend(["hyper breasts", "massive breasts", "oversized breasts"])
    if family in ("flux", "noctq_v4"):
        prose = {
            0: "flat chest",
            1: "small breasts, modest chest",
            2: "medium breasts",
            3: "large breasts",
            4: "huge breasts",
            5: "gigantic breasts",
        }[size]
        return f"{prose}, " + ", ".join(f"not {tag}" for tag in avoided), ""
    return f"({chosen}:1.4)", ", ".join(f"({tag}:1.35)" for tag in avoided)


_CONTACT = re.compile(r"\b(fellatio|vaginal|cowgirl|penetrat\w*|oral|sex)\b", re.IGNORECASE)
_MALE = re.compile(
    r"\b(?:man|male|adult\s+boy|1boy|мужчина|мужчины|мужчину|мужчиной|мужской|парень)\b",
    re.IGNORECASE,
)
_FEMALE = re.compile(
    r"\b(?:woman|female|adult\s+girl|1girl|женщина|женщины|женщину|женщиной|женский|девушка)\b",
    re.IGNORECASE,
)


def edit_realism_clause() -> str:
    """Keep generated skin at the reference's level of stylization."""
    return (
        "Match the realism of picture 1 on the whole figure, including bare skin. "
        "Do not make the body more photographic than the face and the rendering already in picture 1. "
        "Use the same contours, shading transitions, surface texture and degree of stylization."
    )


def edit_face_clause(cast: int = 1, *, generated_partner: bool = False) -> str:
    """Stop the edit model from inventing a new face while it redraws the body."""
    if generated_partner:
        return (
            "Keep the face of the adult character from picture 1 identical: same eye shape and spacing, nose, "
            "jaw, mouth, hairline and hairstyle. The second adult is a different person with a clearly different "
            "face, hairstyle and body silhouette. Do not clone the reference character onto the partner."
        )
    if cast > 1:
        return (
            "Keep every adult face identical to its corresponding person in picture 1: preserve each person's "
            "own eye shape, nose, jaw, mouth, hairline and hairstyle. Never copy one person's face onto another."
        )
    subject = "the adult face"
    return (
        f"Keep {subject} identical to picture 1: same eye shape and spacing, nose, jaw, mouth, hairline and hairstyle. "
        "Do not beautify, age, blur or replace the face."
    )


def is_male_appearance(appearance: str) -> bool:
    """Recognize an explicitly male adult description in English or Russian."""
    return bool(_MALE.search(appearance or "")) and not bool(_FEMALE.search(appearance or ""))


def is_female_appearance(appearance: str) -> bool:
    """Recognize an explicitly female adult description in English or Russian."""
    return bool(_FEMALE.search(appearance or "")) and not bool(_MALE.search(appearance or ""))


def body_chest_tag(appearance: str, size: int) -> str:
    """Do not leak the female breast-size control into male dataset prompts."""
    breast_size_value(size)
    return "flat masculine chest, natural pectorals, no breasts" if is_male_appearance(appearance) else breast_tag(size)


def body_chest_prompt(appearance: str, size: int, family: str) -> tuple[str, str]:
    if not is_male_appearance(appearance):
        return breast_prompt(size, family)
    breast_size_value(size)
    if family in ("flux", "noctq_v4"):
        return "flat masculine chest, natural pectorals, no breasts", ""
    return "(flat masculine chest:1.35), (natural pectorals:1.2)", "(breasts:1.4), (female chest:1.3)"


def _is_male(appearance: str) -> bool:
    """Compatibility alias for the anatomy prompt helpers below."""
    return is_male_appearance(appearance)


def own_anatomy_clause(appearance: str) -> str:
    """The character's own anatomy, in the same strokes as the rest of the body."""
    if _is_male(appearance):
        return (
            "Draw this adult's own penis and scrotum as clear shapes with the same contours and shading as the torso. "
            "Do not add a vulva and do not attach a second set of genitals."
        )
    return (
        "Draw this adult vulva and nipples as clear shapes with the same contours and shading as the torso. "
        "Do not add a penis and do not attach a second set of genitals."
    )


def partner_anatomy_clause(appearance: str) -> str:
    """Two bodies. Genitals stay on the person they belong to."""
    if _is_male(appearance):
        owner = (
            "The character from picture 1 is an adult man with a flat masculine chest, penis and scrotum, and no "
            "vulva or breasts. The second adult is a woman with a clearly feminine face and body, breasts and a "
            "vulva, and no penis. The penis belongs only to the character from picture 1. "
            "The vulva belongs only to the second adult woman."
        )
    else:
        owner = (
            "The character from picture 1 is an adult woman with a clearly feminine face and body, breasts and a "
            "vulva, and no penis. The second adult is a man with a masculine face and body, flat male chest, penis "
            "and scrotum, and no vulva or breasts. The penis belongs only to the second adult man. "
            "The vulva belongs only to the character from picture 1."
        )
    return (
        "The sex partner is a second, visibly different adult with a separate body and a different face and hair. " + owner + " "
        "A penis keeps a distinct shaft and glans. A vulva keeps a distinct shape. "
        "Show both bodies and a clear junction large in the center of the frame. "
        "Do not grow the partner's genitals out of the character from picture 1. "
        "Do not fuse the bodies or hide the contact in a smear."
    )


def edit_anatomy_clause(appearance: str, scene: str, interaction: bool) -> str:
    """Ask for coherent adult anatomy in the reference medium, including sexual contact."""
    blob = f"{appearance or ''} {scene or ''}"
    contact = interaction or bool(_CONTACT.search(blob))
    if contact:
        return partner_anatomy_clause(appearance)
    return own_anatomy_clause(appearance)


def dataset_edit_prompt(pose: str, appearance: str, *, nude: bool, interaction: bool, framing: str,
                        chest: str, medium_prefix: str = "", medium_finish: str = "") -> str:
    """One instruction for clothed and nude edits. Only the wardrobe and the act change."""
    if nude and interaction:
        wardrobe = (
            "Remove the source costume and any underwear from both adults. "
            "Keep natural adult proportions and coherent limbs. "
            "Bare skin stays at the same level of realism as picture 1. "
            f"Chest proportions: {chest}."
        )
        anatomy = partner_anatomy_clause(appearance)
    elif nude:
        wardrobe = (
            "Remove the source costume and any underwear. Keep natural adult proportions and coherent limbs. "
            "Bare skin stays at the same level of realism as picture 1. "
            f"Chest proportions: {chest}."
        )
        anatomy = own_anatomy_clause(appearance)
    else:
        wardrobe = "Keep the character fully dressed. Preserve the exact costume design, markings, accessories and colors."
        anatomy = ""
    text = (
        f"{medium_prefix}Edit picture 1 into one new image of the same adult character, {framing}. "
        "Preserve the face, age, eye color and hair silhouette from picture 1. "
        "Preserve the reference shoulder width, torso length, waist-to-hip ratio, limb thickness, chest volume and "
        "overall body silhouette. Do not enlarge or shrink the chest, hips, waist or thighs between views. "
        "Keep its original rendering medium, lighting technique and material texture. "
        "Preserve the original level of realism. "
        f"{edit_realism_clause()} {edit_face_clause(2 if interaction else 1, generated_partner=interaction)} "
        "Keep the lighting of picture 1. "
        f"{wardrobe} Intimate skin uses the same hue family, saturation, line treatment, shader and surface "
        "roughness as the surrounding body; do not add isolated red coloring, wet gloss or white specular streaks "
        "that do not exist in picture 1. "
        f"Change the pose and camera angle as requested. {pose} {anatomy} {medium_finish}"
    )
    return clean_prompt(text)


def qwen_anatomy_tokens(appearance: str, scene: str, interaction: bool) -> str:
    """Training tokens for the low-strength Qwen anatomy corrective LoRA."""
    text = f"{scene or ''}".lower()
    tokens = ["n5fw"]
    if _is_male(appearance):
        tokens.extend(("z40peni penis",))
    else:
        tokens.extend(("z41vagn vulva",))
    if "fellatio" in text or "oral" in text:
        tokens.extend(("z10fell fellatio", "z40peni penis", "z60erct erection"))
    if "vaginal" in text or "cowgirl" in text:
        tokens.extend(("z01vpen vaginal penetration", "z40peni penis", "z41vagn vulva", "z60erct erection"))
    if "anal" in text:
        tokens.extend(("z02apen anal penetration", "z42anus anus"))
    if interaction and "z40peni penis" not in tokens:
        tokens.append("z40peni penis")
    return ", ".join(dict.fromkeys(tokens))


def dataset_wai_prompt(pose: str, appearance: str, *, nude: bool, interaction: bool, chest: str,
                       medium_finish: str = "", using_lora: bool = False, outfit: str = "") -> str:
    """Same rules as the edit instruction, short enough that WAI does not drop the pose."""
    identity = appearance_identity(appearance)
    if nude and interaction:
        if _is_male(appearance):
            ownership = (
                "the learned character is the only adult man and owns the only penis and scrotum, "
                "the visibly different partner is the only adult woman and owns the only breasts and vulva"
            )
        else:
            ownership = (
                "the primary adult woman has medium brown skin and is the only adult woman and owns the only breasts and vulva, "
                "the visibly different light-skinned partner is the only adult man, has a masculine face, flat masculine chest, "
                "short dark hair and a plain bare neck, and owns the only penis and scrotum"
            )
        contact = ""
        low_pose = pose.lower()
        if "cowgirl" in low_pose or "vaginal" in low_pose:
            contact = (
                ", cowgirl position, vaginal intercourse, pelvises joined naturally in one external side view"
            )
        elif "fellatio" in low_pose or "oral" in low_pose:
            contact = (
                ", (fellatio:1.4), (penis in mouth:1.35), the man's penis visibly enters the woman's mouth, "
                "oral contact centered and unobscured"
            )
        rule = (
            "(1girl:1.35), (1boy:1.35), heterosexual, exactly one adult woman and exactly one adult man, "
            f"exactly two separate adult bodies, {ownership}, different faces and hair, uncensored, coherent sexual contact{contact}, "
            "single full-frame composition showing the two complete bodies"
        )
    elif nude:
        rule = "solo, exactly one adult, one body, one head, uncensored, own genitals only"
    else:
        costume = f"wearing {outfit.strip()}" if outfit.strip() else (
            "same learned costume" if using_lora else "same costume as the reference"
        )
        rule = f"solo, exactly one adult, one body, one head, clothed, {costume}"
    identity_lock = (
        "same learned character, same learned art style, preserve the reference skin tone and facial proportions" if using_lora
        else "same art style as the reference, same primary face"
    )
    medium_lock = "keep the original rendering medium of the reference"
    chest_lock = f"({chest}:1.25)" if nude else chest
    return clean_prompt(
        f"masterpiece, best quality, one continuous image, {identity_lock}, "
        f"{identity}, {chest_lock}, {rule}, {pose}, "
        f"{medium_lock}, {medium_finish}"
    )


def anatomy_refine_prompt(appearance: str, interaction: bool) -> str:
    """Second pass on a close crop. The first pass already set the style."""
    keep = (
        "Edit picture 1 in place. Keep this exact crop, pose, linework, colors and shading. "
        "Do not change the art style and do not add limbs."
    )
    if interaction:
        return (
            keep + " Redraw the sexual contact so it is sharp. The penis stays on one adult only. "
            "The vulva stays on the other adult. The junction is clear, not fused and not a smear."
        )
    if _is_male(appearance):
        return keep + " Redraw this adult's penis and scrotum as clear separate shapes. Do not add a vulva."
    return keep + " Redraw this adult vulva as a clear shape with the same line weight as the navel. Do not add a penis."


def genital_wording(scene: str, appearance: str) -> str:
    """Use male anatomy when the adult character is male. Partner acts keep both participants."""
    if not is_male_appearance(appearance):
        return scene
    replacements = (
        ("nipples and vulva visible", "penis and scrotum visible"),
        ("breasts and buttocks visible", "chest, penis and buttocks visible"),
        (
            "the character kneels and performs fellatio, a second adult stands, penis in her mouth, both bodies visible and separate, the penis stays on the standing partner",
            "the character stands and receives fellatio, a second adult kneels, the character's penis is in the partner's mouth, both bodies visible and separate, the penis stays on the character",
        ),
        (
            "cowgirl position, the character straddles a reclining second adult, vaginal sex, the partner's penis enters her vulva",
            "cowgirl position, a second adult straddles the reclining character, vaginal sex, the character's penis enters the partner's vulva",
        ),
    )
    for old, new in replacements:
        scene = scene.replace(old, new)
    return scene


def explicit_is_fully_nude(scene: str) -> bool:
    """NSFW is naked unless the scene itself asks for clothing or a partial state."""
    low = scene.lower()
    if any(marker in low for marker in _FULLY_NUDE):
        return True
    if any(marker in low for marker in _PARTIAL_CLOTHING):
        return False
    return True


def appearance_without_clothes(appearance: str) -> str:
    """Drop garment clauses so a clothed description is not copied onto a naked frame."""
    text = _CLOTHING_CLAUSE.sub("", appearance or "")
    parts = [part.strip() for part in text.split(",")]
    kept = [part for part in parts if part and not _GARMENT.search(part)]
    return clean_prompt(", ".join(kept))


def appearance_identity(appearance: str) -> str:
    """Keep invariant anatomy and facial traits, not wardrobe or the pose captured by the source image."""
    sentences = re.split(r"(?<=[.!?])\s+", appearance or "")
    stable = []
    for sentence in sentences:
        stripped = sentence.strip(" ,.")
        if not stripped or re.match(r"^(?:wears?|wearing|dressed|clothed)\b", stripped, re.IGNORECASE):
            continue
        parts = [part.strip(" .") for part in stripped.split(",")]
        stable.extend(part for part in parts if part and not _GARMENT.search(part) and not _POSE_CLAUSE.search(part))
    return clean_prompt(", ".join(stable))


def scene_with_outfit(scene: str, rating: str, outfit: str) -> str:
    """Clothed and half-dressed frames share one outfit. Fully naked frames do not mention it."""
    clothes = (outfit or "casual clothes").strip()
    text = scene.strip()
    if rating == "rating_explicit" and explicit_is_fully_nude(text):
        return text
    if clothes.lower() not in text.lower():
        text = f"{text}, wearing {clothes}"
    if rating == "rating_explicit":
        text = f"{text}, same clothes"
    return text


def dataset_views(include_nude: bool) -> list[tuple[str, str, str]]:
    views = list(CLOTHED_VIEWS)
    if include_nude:
        views.extend(NUDE_VIEWS)
    return views
