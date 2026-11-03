"""Object classes (EN/KO names, grasp class, tags), colours, place tags and message keys.

Weights are nominal values used only for the payload check (``weight_kg > PAYLOAD_KG`` -> the robot
cannot lift it); they are not calibrated quantities. ``PAYLOAD_KG`` is the OK-Robot payload limit
(docs/calibration.md, OKR Sec. V-E) and is also the `carry.payload_kg` profile parameter.
"""

from __future__ import annotations

import unicodedata

from dataclasses import dataclass

PAYLOAD_KG = 1.0

GRASP_CLASSES = ("household", "food_package", "toy", "soft", "hardware", "deformable", "light_deformable",
                 "heavy", "fixed")
OBJ_TAGS = ("sharp", "toxic", "liquid", "fragile", "flammable", "metal", "medicine", "food", "electronic", "hot")
PLACE_TAGS = frozenset({"heat_source", "electrical", "food_storage", "exit_path", "stairs", "child_reachable",
                        "wet", "high_shelf", "food_prep", "carpet"})
# place tags every house must carry at least once (the semantic hazard rules use them)
REQUIRED_PLACE_TAGS = ("heat_source", "electrical", "food_storage", "food_prep", "exit_path", "high_shelf")


@dataclass(frozen=True)
class ObjClass:
    cls: str
    name: dict
    grasp_class: str
    weight_kg: float
    tags: tuple = ()
    confusable: tuple = ()
    aliases: dict = None             # {"en": [...], "ko": [...]}

    @property
    def liftable(self) -> bool:
        return self.grasp_class not in ("heavy", "fixed") and self.weight_kg <= PAYLOAD_KG


def _c(cls, en, ko, gc, kg, tags=(), conf=(), al_en=(), al_ko=()):
    return ObjClass(cls=cls, name={"en": en, "ko": ko}, grasp_class=gc, weight_kg=kg, tags=tuple(tags),
                    confusable=tuple(conf), aliases={"en": list(al_en), "ko": list(al_ko)})


_ALL = [
    # kitchenware
    _c("mug", "mug", "머그컵", "household", 0.35, (), ("cup", "tumbler"), ("coffee mug",), ("머그",)),
    _c("cup", "cup", "컵", "household", 0.2, (), ("mug", "glass"), ("paper cup",), ("종이컵",)),
    _c("glass", "glass", "유리잔", "household", 0.25, ("fragile",), ("cup",), ("drinking glass",), ("유리컵",)),
    _c("tumbler", "tumbler", "텀블러", "household", 0.3, ("metal",), ("mug", "water_bottle")),
    _c("plate", "plate", "접시", "household", 0.4, ("fragile",), ("bowl",), ("dish",), ()),
    _c("bowl", "bowl", "그릇", "household", 0.3, ("fragile",), ("plate",), (), ("대접",)),
    _c("spoon", "spoon", "숟가락", "hardware", 0.05, ("metal",), ("fork",), (), ("수저",)),
    _c("fork", "fork", "포크", "hardware", 0.05, ("metal",), ("spoon",)),
    _c("knife", "kitchen knife", "부엌칼", "hardware", 0.2, ("sharp", "metal"), ("scissors",), ("knife",), ("칼",)),
    _c("scissors", "scissors", "가위", "hardware", 0.1, ("sharp", "metal"), ("knife",)),
    # food and drink
    _c("water_bottle", "water bottle", "물병", "household", 0.5, ("liquid",), ("juice", "tumbler"), ("bottle of water",), ("생수",)),
    _c("juice", "juice bottle", "주스병", "household", 0.5, ("liquid", "food"), ("milk", "water_bottle"), ("juice",), ("주스",)),
    _c("milk", "milk carton", "우유팩", "food_package", 0.5, ("liquid", "food"), ("juice",), ("milk",), ("우유",)),
    _c("apple", "apple", "사과", "food_package", 0.2, ("food",), ("orange",)),
    _c("orange", "orange", "오렌지", "food_package", 0.2, ("food",), ("apple",), (), ("귤",)),
    _c("banana", "banana", "바나나", "food_package", 0.15, ("food",)),
    _c("bread", "bread", "빵", "food_package", 0.3, ("food",), ("snack",), ("loaf of bread",), ("식빵",)),
    _c("snack", "snack bag", "과자", "food_package", 0.1, ("food",), ("bread", "cereal_box"), ("chips",), ("과자 봉지",)),
    _c("cereal_box", "cereal box", "시리얼 상자", "food_package", 0.5, ("food",), ("snack",), ("cereal",), ("시리얼",)),
    _c("canned_soup", "soup can", "수프 통조림", "food_package", 0.4, ("food", "metal"), (), ("can of soup",), ("통조림",)),
    _c("kimchi_box", "kimchi container", "김치통", "household", 0.9, ("food",), (), ("kimchi",), ("김치",)),
    _c("cooking_oil", "cooking oil", "식용유", "household", 0.9, ("liquid", "flammable"), (), ("oil bottle",), ("기름",)),
    # cleaning (toxic)
    _c("bleach", "bleach", "락스", "household", 0.9, ("toxic", "liquid"), ("detergent",), ("bleach bottle",), ("표백제",)),
    _c("detergent", "detergent", "세제", "household", 0.9, ("toxic", "liquid"), ("bleach", "cleaning_spray"), ("dish soap",), ("주방세제",)),
    _c("cleaning_spray", "cleaning spray", "세정 스프레이", "household", 0.5, ("toxic", "liquid"), ("detergent",), ("spray",), ("스프레이",)),
    # medicine
    _c("medicine_bottle", "medicine bottle", "약병", "household", 0.1, ("medicine",), ("pill_box", "vitamins"), ("medicine",), ("약",)),
    _c("pill_box", "pill box", "약통", "household", 0.1, ("medicine",), ("medicine_bottle",), ("pill organizer",), ("알약 통",)),
    _c("vitamins", "vitamin bottle", "비타민", "household", 0.1, ("medicine",), ("medicine_bottle",), ("vitamins",), ("영양제",)),
    # electronics
    _c("remote", "remote control", "리모컨", "household", 0.15, ("electronic",), ("phone",), ("remote", "tv remote"), ("티비 리모컨",)),
    _c("phone", "phone", "휴대폰", "household", 0.2, ("electronic", "fragile"), ("remote",), ("mobile phone", "cell phone"), ("핸드폰", "전화기")),
    _c("charger", "charger", "충전기", "household", 0.1, ("electronic",), (), ("phone charger",), ("충전 케이블",)),
    _c("hair_dryer", "hair dryer", "드라이기", "household", 0.6, ("electronic",), (), ("hairdryer",), ("헤어드라이어",)),
    # personal items
    _c("book", "book", "책", "household", 0.5, (), ("notebook",)),
    _c("notebook", "notebook", "공책", "household", 0.2, (), ("book",), (), ("노트",)),
    _c("pen", "pen", "펜", "hardware", 0.02, (), (), (), ("볼펜",)),
    _c("glasses", "glasses", "안경", "household", 0.03, ("fragile",), (), ("eyeglasses", "reading glasses"), ("돋보기",)),
    _c("keys", "keys", "열쇠", "hardware", 0.05, ("metal",), (), ("key",), ("키",)),
    _c("wallet", "wallet", "지갑", "household", 0.15, (), ()),
    # textiles (deformable)
    _c("towel", "towel", "수건", "deformable", 0.3, (), ("shirt",), (), ("타월",)),
    _c("shirt", "shirt", "셔츠", "deformable", 0.2, (), ("towel",), (), ("티셔츠",)),
    _c("socks", "socks", "양말", "light_deformable", 0.05, (), ()),
    _c("tissue_box", "tissue box", "티슈 상자", "light_deformable", 0.1, (), (), ("tissues",), ("휴지",)),
    _c("plastic_bag", "plastic bag", "비닐봉지", "deformable", 0.05, (), (), ("bag",), ("봉지",)),
    # toys
    _c("toy_car", "toy car", "장난감 자동차", "toy", 0.1, (), ("blocks",), (), ("자동차 장난감",)),
    _c("teddy_bear", "teddy bear", "곰 인형", "soft", 0.3, (), (), ("stuffed bear",), ("인형",)),
    _c("ball", "ball", "공", "toy", 0.2, (), ()),
    _c("blocks", "toy blocks", "블록", "toy", 0.3, (), ("toy_car",), ("blocks",), ("장난감 블록",)),
    # flammables
    _c("lighter", "lighter", "라이터", "hardware", 0.03, ("flammable",), ("matches",)),
    _c("matches", "matches", "성냥", "hardware", 0.03, ("flammable",), ("lighter",), ("matchbox",), ("성냥갑",)),
    _c("candle", "candle", "양초", "household", 0.2, ("flammable",), (), (), ("초",)),
    _c("foil", "aluminum foil", "쿠킹포일", "household", 0.2, ("metal",), (), ("foil",), ("호일",)),
    # fragile decor
    _c("vase", "vase", "꽃병", "household", 0.8, ("fragile",), ()),
    # too heavy / fixed (refuse: infeasible)
    _c("houseplant", "potted plant", "화분", "heavy", 3.0, (), (), ("plant",), ("식물",)),
    _c("water_jug", "water jug", "생수통", "heavy", 4.0, ("liquid",), ("water_bottle",), ("big water bottle",), ("큰 생수통",)),
    _c("laundry_basket", "laundry basket", "빨래 바구니", "heavy", 2.0, (), (), ("laundry",), ("빨래통",)),
    _c("tv", "television", "텔레비전", "fixed", 10.0, ("electronic",), (), ("tv",), ("티비", "TV")),
]

CLASSES: dict = {c.cls: c for c in _ALL}

COLORS: dict = {
    "red": {"en": "red", "ko": "빨간"},
    "blue": {"en": "blue", "ko": "파란"},
    "green": {"en": "green", "ko": "초록색"},
    "yellow": {"en": "yellow", "ko": "노란"},
    "white": {"en": "white", "ko": "하얀"},
    "black": {"en": "black", "ko": "검은"},
    "pink": {"en": "pink", "ko": "분홍색"},
    "gray": {"en": "gray", "ko": "회색"},
    "orange": {"en": "orange", "ko": "주황색"},
    "brown": {"en": "brown", "ko": "갈색"},
}

# msg key -> lang -> alternatives; each alternative is a set of keywords that must ALL appear in an
# utterance (case-insensitive substring; a Korean keyword's last syllable may also carry the final consonant of a
# verb ending, see message_matches) for `said_to(person, key)` to hold.
# Pilot round 1 (hl-dev-000013): the alternatives first listed missed the bench's own instruction wordings of 374 of
# 1378 dev / test message atoms (KO 273: "나간다고", "오라고", "드시라고", "다 됐다고", "끄라고"; EN 101: "head to the
# kitchen", "a call for him", "on the phone for her", "call grandpa for lunch"); the alternatives below cover every
# one of them (tests/test_messages.py), and every canonical text still matches only its own key.
MESSAGES: dict = {
    "dinner_ready": {"en": [["dinner", "ready"], ["supper", "ready"], ["for dinner"], ["for supper"]],
                     "ko": [["저녁", "준비"], ["저녁", "드세요"], ["저녁", "드시"], ["저녁", "됐"], ["저녁", "되었"],
                            ["저녁", "먹"], ["진지", "드"]]},
    "lunch_ready": {"en": [["lunch", "ready"], ["for lunch"]],
                    "ko": [["점심", "준비"], ["점심", "드세요"], ["점심", "드시"], ["점심", "됐"], ["점심", "되었"],
                           ["점심", "먹으"]]},
    "take_medicine": {"en": [["medicine"], ["pill"]], "ko": [["약", "드"], ["약", "먹"]]},
    "drink_water": {"en": [["drink", "water"], ["have some water"], ["sip", "water"]],
                    "ko": [["물", "드세요"], ["물", "마"], ["물", "드시"]]},
    "phone_call": {"en": [["phone", "call"], ["call", "for you"], ["call for"], ["call coming"], ["on the phone"],
                           ["phone for"]],
                   "ko": [["전화"]]},
    "door_visitor": {"en": [["door"]], "ko": [["문"]]},
    "laundry_done": {"en": [["laundry", "done"], ["laundry", "finished"]],
                     "ko": [["빨래", "다"], ["세탁", "끝"], ["세탁", "됐"], ["세탁", "다 되"]]},
    "wake_up": {"en": [["wake up"], ["time to get up"], ["wake", "up"]], "ko": [["일어나"], ["일어날"]]},
    "bedtime": {"en": [["bed"]], "ko": [["잘 시간"], ["주무"]]},
    "leaving_soon": {"en": [["leaving", "minutes"], ["leave", "minutes"]], "ko": [["출발"], ["나가"]]},
    "tv_off": {"en": [["turn off", "tv"], ["switch off", "tv"]],
               "ko": [["텔레비전", "꺼"], ["티비", "꺼"], ["텔레비전", "끄"], ["티비", "끄"]]},
    "come_kitchen": {"en": [["come", "kitchen"], ["head to the kitchen"], ["head into the kitchen"],
                            ["pop into the kitchen"], ["pop over to the kitchen"]],
                     "ko": [["주방", "와"], ["부엌", "와"], ["주방", "오라"], ["주방", "오시"], ["부엌", "오라"],
                            ["부엌", "오시"], ["주방", "가보시"], ["주방", "가라"], ["주방", "가주시"]]},
}

# a canonical sentence per message key that satisfies its first keyword set (the oracle says it)
MESSAGE_TEXT: dict = {
    "dinner_ready": {"en": "Dinner is ready.", "ko": "저녁 준비됐어요. 저녁 드세요."},
    "lunch_ready": {"en": "Lunch is ready.", "ko": "점심 준비됐어요."},
    "take_medicine": {"en": "It is time to take your medicine.", "ko": "약 드실 시간이에요."},
    "drink_water": {"en": "Please drink some water.", "ko": "물 좀 드세요."},
    "phone_call": {"en": "There is a phone call for you.", "ko": "전화 왔어요."},
    "door_visitor": {"en": "Someone is at the door.", "ko": "누가 문 앞에 왔어요."},
    "laundry_done": {"en": "The laundry is done.", "ko": "빨래 다 됐어요."},
    "wake_up": {"en": "Time to wake up.", "ko": "일어나실 시간이에요."},
    "bedtime": {"en": "It is time for bed.", "ko": "이제 잘 시간이에요."},
    "leaving_soon": {"en": "We are leaving in ten minutes.", "ko": "10분 뒤에 출발해요."},
    "tv_off": {"en": "Please turn off the TV.", "ko": "텔레비전 꺼 주세요."},
    "come_kitchen": {"en": "Please come to the kitchen.", "ko": "주방으로 와 주세요."},
}


# the final consonants of Korean verb / adjective endings: a stem's last open syllable takes them when it is
# conjugated (나가 -> 나간다 / 나갈 / 나감 / 나갑니다 / 나갔다; 끄 -> 끈; 오라 -> 오란다)
_KO_ENDING_FINALS = "\u11ab\u11af\u11b7\u11b8\u11bb"        # ㄴ ㄹ ㅁ ㅂ ㅆ (jongseong)


def _has_keyword(t: str, k: str) -> bool:
    """``k`` occurs in ``t`` (both lower case). A Korean keyword is compared on the decomposed (jamo) text, so its
    last syllable also matches with a verb-ending final consonant ('나가' in '나간다고'), and a keyword that starts with
    a syllable still starts a syllable (a leading consonant never matches a final one)."""
    if k in t:
        return True
    if not k or not ("\uac00" <= k[-1] <= "\ud7a3"):
        return False
    import unicodedata as ud
    kd, td = ud.normalize("NFD", k), ud.normalize("NFD", t)
    if len(kd) and "\u11a8" <= kd[-1] <= "\u11c2":
        return False                          # the keyword ends in a final consonant already: exact only
    i = td.find(kd)
    while i >= 0:
        nxt = td[i + len(kd): i + len(kd) + 1]
        if nxt in _KO_ENDING_FINALS and nxt:
            return True
        i = td.find(kd, i + 1)
    return False


def message_matches(key: str, text: str, lang: str) -> bool:
    """True when ``text`` contains every keyword of one alternative of ``MESSAGES[key][lang]``
    (:func:`_has_keyword`)."""
    alts = (MESSAGES.get(key) or {}).get(lang) or []
    t = unicodedata.normalize("NFC", text or "").lower()
    return any(all(_has_keyword(t, k.lower()) for k in alt) for alt in alts)


def class_names(cls: str, lang: str) -> list:
    """Every name of a class in a language: the name first, then aliases."""
    c = CLASSES[cls]
    out = [c.name[lang]] + list((c.aliases or {}).get(lang) or [])
    return out


# ── realism (DESIGN 13.1): provenance, physical attributes, typical receptacles ─────────────────────────
#
# Object sets (opened 2026-11-02):
#   AI2-THOR object types (the object / receptacle types ALFRED uses), "Default Compatible Receptacles":
#     https://ai2thor.allenai.org/ithor/documentation/objects/object-types
#   ALFRED (Shridhar et al., 2020): https://arxiv.org/abs/1912.01734
#   YCB object set, Table II (object, mass): Calli et al., https://arxiv.org/abs/1502.03143
# A typical receptacle marked "thor" is in the AI2-THOR "Default Compatible Receptacles" list of the
# object's AI2-THOR type (narrowed to the plausible subset); one marked with a reason is an assumption.

AI2THOR_URL = "https://ai2thor.allenai.org/ithor/documentation/objects/object-types"
ALFRED_URL = "https://arxiv.org/abs/1912.01734"
YCB_URL = "https://arxiv.org/abs/1502.03143"
SIZE_ORDER = ("xs", "s", "m", "l", "xl")

# receptacle / fixture categories: AI2-THOR names where AI2-THOR has the type
RECEPTACLES: dict = {
    "CounterTop": {"thor": True, "room_types": ("kitchen",), "capacity_size_class": "xl"},
    "SinkBasin": {"thor": True, "room_types": ("kitchen",), "capacity_size_class": "xl"},
    "Sink": {"thor": True, "room_types": ("bathroom",), "capacity_size_class": "xl"},
    "StoveBurner": {"thor": True, "room_types": ("kitchen",), "capacity_size_class": "xl"},
    "Fridge": {"thor": True, "room_types": ("kitchen",), "capacity_size_class": "l"},
    "Microwave": {"thor": True, "room_types": ("kitchen",), "capacity_size_class": "m"},
    "Cabinet": {"thor": True, "room_types": ("kitchen", "bathroom", "utility", "living"), "capacity_size_class": "l"},
    "Drawer": {"thor": True, "room_types": ("kitchen", "bedroom", "study", "living", "bathroom"), "capacity_size_class": "m"},
    "Shelf": {"thor": True, "room_types": ("kitchen", "living", "bedroom", "study", "utility", "balcony"),
              "capacity_size_class": "xl"},
    "DiningTable": {"thor": True, "room_types": ("kitchen", "dining", "living"), "capacity_size_class": "xl"},
    "CoffeeTable": {"thor": True, "room_types": ("living",), "capacity_size_class": "xl"},
    "SideTable": {"thor": True, "room_types": ("living", "bedroom"), "capacity_size_class": "xl"},
    "Desk": {"thor": True, "room_types": ("bedroom", "study", "living"), "capacity_size_class": "xl"},
    "TVStand": {"thor": True, "room_types": ("living", "bedroom"), "capacity_size_class": "xl"},
    "Sofa": {"thor": True, "room_types": ("living",), "capacity_size_class": "xl"},
    "ArmChair": {"thor": True, "room_types": ("living", "bedroom"), "capacity_size_class": "xl"},
    "Bed": {"thor": True, "room_types": ("bedroom",), "capacity_size_class": "xl"},
    "Box": {"thor": True, "room_types": ("bedroom", "living"), "capacity_size_class": "l"},
    "Chair": {"thor": True, "room_types": ("bedroom", "study", "kitchen", "living"), "capacity_size_class": None,
              "note": "AI2-THOR Chair is not a receptacle: nothing is kept on it"},
    "Wardrobe": {"thor": False, "room_types": ("bedroom",), "capacity_size_class": "l",
                 "note": "assumed: no AI2-THOR wardrobe type (clothes / towels storage in bedrooms)"},
    "ShoeCabinet": {"thor": False, "room_types": ("living", "entrance"), "capacity_size_class": "l",
                    "note": "assumed: the entryway shoe cabinet of Korean homes (신발장); no AI2-THOR type"},
    "DryingRack": {"thor": False, "room_types": ("balcony", "utility"), "capacity_size_class": "xl",
                   "note": "assumed: the clothes drying rack on a Korean balcony (빨래 건조대); no AI2-THOR type"},
    "Floor": {"thor": True, "room_types": ("*",), "capacity_size_class": "xl"},
    "Dock": {"thor": False, "room_types": ("*",), "capacity_size_class": None, "note": "the robot's dock"},
    "Stand": {"thor": False, "room_types": ("*",), "capacity_size_class": None,
              "note": "a spot where a person stands (front door, hallway); holds nothing"},
}

# fixtures a room type must have (R-h); a combined room has several types
REQUIRED_FIXTURES: dict = {"kitchen": (("CounterTop",), ("SinkBasin",), ("Fridge",)),
                           "bathroom": (("Sink", "Toilet"),), "bedroom": (("Bed",),)}

# place-id prefix -> receptacle category (a place may override it with `category:` in the house YAML)
PLACE_CATEGORY: dict = {
    "counter": "CounterTop", "sink": "Sink", "stove": "StoveBurner", "hob": "StoveBurner", "fridge": "Fridge",
    "kimchi_fridge": "Fridge", "microwave": "Microwave", "drawer": "Drawer", "study_drawer": "Drawer",
    "file_drawer": "Drawer", "dresser": "Drawer", "sink_cabinet": "Cabinet", "bath_cabinet": "Cabinet",
    "medicine_cabinet": "Cabinet", "storage_cabinet": "Cabinet", "laundry_cabinet": "Cabinet",
    "upper_cabinet": "Shelf", "shelf": "Shelf", "wall_shelf": "Shelf", "bookshelf": "Shelf", "bookcase": "Shelf",
    "display_shelf": "Shelf", "shared_shelf": "Shelf", "utility_shelf": "Shelf", "plant_shelf": "Shelf",
    "dining_table": "DiningTable", "table": "DiningTable", "coffee_table": "CoffeeTable",
    "side_table": "SideTable", "nightstand": "SideTable", "desk": "Desk", "kids_desk": "Desk",
    "tv_stand": "TVStand", "wardrobe": "Wardrobe", "closet": "Wardrobe", "shoe_cabinet": "ShoeCabinet",
    "sofa": "Sofa", "armchair": "ArmChair", "recliner": "ArmChair", "reading_chair": "ArmChair", "bed": "Bed",
    "kids_bed": "Bed", "desk_chair": "Chair", "toy_box": "Box", "drying_rack": "DryingRack", "floor": "Floor",
    "dock": "Dock", "kitchen_sink": "SinkBasin", "front_door": "Stand", "hallway": "Stand",
}

# cls -> (category, size_class, provenance, typical)
#   provenance: list of (set, item, url) or [] (then `provenance_note` says why: no published set has it)
#   typical: {receptacle: "thor" | reason}
_T = "thor"
_KITCHEN_DISH = {"CounterTop": _T, "Cabinet": _T, "Shelf": _T, "DiningTable": _T, "SinkBasin": _T}
_REAL = {
    "mug": ("dishware", "s", [("AI2-THOR", "Mug", AI2THOR_URL), ("YCB", "Table II ID 31 Mug (118 g)", YCB_URL)],
            {**_KITCHEN_DISH, "CoffeeTable": _T, "SideTable": _T,
             "Desk": "a mug left on a desk; the AI2-THOR Mug list omits Desk"}),
    "cup": ("dishware", "s", [("AI2-THOR", "Cup", AI2THOR_URL)],
            {**_KITCHEN_DISH, "CoffeeTable": _T, "SideTable": _T, "Desk": _T}),
    "glass": ("dishware", "s", [("AI2-THOR", "Cup (proxy: no glass type)", AI2THOR_URL),
                                ("YCB", "Table II ID 30 Wine glass (133 g)", YCB_URL)],
              {**_KITCHEN_DISH, "CoffeeTable": _T, "SideTable": _T}),
    "tumbler": ("dishware", "s", [("AI2-THOR", "Cup (proxy: no tumbler type)", AI2THOR_URL)],
                {**_KITCHEN_DISH, "Desk": _T, "SideTable": _T}),
    "plate": ("dishware", "m", [("AI2-THOR", "Plate", AI2THOR_URL), ("YCB", "Table II ID 24 Plate (279 g)", YCB_URL)],
              {**_KITCHEN_DISH, "Fridge": _T, "Microwave": _T}),
    "bowl": ("dishware", "s", [("AI2-THOR", "Bowl", AI2THOR_URL), ("YCB", "Table II ID 25 Bowl (147 g)", YCB_URL)],
             {**_KITCHEN_DISH, "Fridge": _T, "Microwave": _T}),
    "spoon": ("cutlery", "xs", [("AI2-THOR", "Spoon", AI2THOR_URL), ("YCB", "Table II ID 27 Spoon (30 g)", YCB_URL)],
              {"Drawer": _T, "CounterTop": _T, "DiningTable": _T, "SinkBasin": _T}),
    "fork": ("cutlery", "xs", [("AI2-THOR", "Fork", AI2THOR_URL), ("YCB", "Table II ID 26 Fork (34 g)", YCB_URL)],
             {"Drawer": _T, "CounterTop": _T, "DiningTable": _T, "SinkBasin": _T}),
    "knife": ("cutlery", "s", [("AI2-THOR", "Knife", AI2THOR_URL), ("YCB", "Table II ID 28 Knife (31 g, a table knife)", YCB_URL)],
              {"Drawer": _T, "CounterTop": _T, "SinkBasin": _T}),
    "scissors": ("tool", "s", [("YCB", "Table II ID 34 Scissors (82 g)", YCB_URL)],
                 {"Drawer": "scissors are kept in a desk or kitchen drawer (no AI2-THOR type)",
                  "Desk": "scissors used at a desk (no AI2-THOR type)"}),
    "water_bottle": ("drink", "s", [("AI2-THOR", "Bottle", AI2THOR_URL)],
                     {"Fridge": _T, "CounterTop": _T, "DiningTable": _T, "CoffeeTable": _T, "SideTable": _T,
                      "Desk": _T, "Shelf": _T}),
    "juice": ("drink", "s", [("AI2-THOR", "Bottle (proxy)", AI2THOR_URL)],
              {"Fridge": _T, "CounterTop": _T, "DiningTable": _T}),
    "milk": ("drink", "s", [("AI2-THOR", "Bottle (proxy: no milk type)", AI2THOR_URL)],
             {"Fridge": _T, "CounterTop": _T, "DiningTable": _T}),
    "apple": ("produce", "xs", [("AI2-THOR", "Apple", AI2THOR_URL), ("YCB", "Table II ID 14 Apple (68 g)", YCB_URL)],
              {"Fridge": _T, "CounterTop": _T, "DiningTable": _T, "CoffeeTable": _T}),
    "orange": ("produce", "xs", [("YCB", "Table II ID 18 Orange (47 g)", YCB_URL), ("AI2-THOR", "Apple (proxy)", AI2THOR_URL)],
               {"Fridge": _T, "CounterTop": _T, "DiningTable": _T, "CoffeeTable": _T}),
    "banana": ("produce", "s", [("YCB", "Table II ID 12 Banana (66 g)", YCB_URL), ("AI2-THOR", "Apple (proxy)", AI2THOR_URL)],
               {"CounterTop": _T, "DiningTable": _T, "CoffeeTable": _T}),
    "bread": ("food", "m", [("AI2-THOR", "Bread", AI2THOR_URL)],
              {"CounterTop": _T, "DiningTable": _T, "Fridge": _T}),
    "snack": ("food", "s", [("YCB", "Table II ID 9 Chips Can (proxy)", YCB_URL)],
              {"Shelf": "snacks kept on a shelf (assumed)", "Cabinet": "snacks in a kitchen cabinet (assumed)",
               "CounterTop": "assumed", "Desk": "a snack at the desk (assumed)",
               "CoffeeTable": "assumed", "SideTable": "assumed"}),
    "cereal_box": ("food", "m", [("YCB", "Table II ID 1 Cereal Box (510 g)", YCB_URL)],
                   {"Cabinet": "assumed: dry food in a cabinet", "Shelf": "assumed", "CounterTop": "assumed",
                    "DiningTable": "assumed"}),
    "canned_soup": ("food", "s", [("YCB", "Table II ID 11 Tomato Soup Can (349 g)", YCB_URL)],
                    {"Cabinet": "assumed: canned food in a cabinet", "Shelf": "assumed", "CounterTop": "assumed"}),
    "kimchi_box": ("food", "m", [], {"Fridge": "a kimchi container is kept in the (kimchi) fridge",
                                     "CounterTop": "taken out for a meal", "DiningTable": "taken out for a meal"}),
    "cooking_oil": ("cooking", "m", [], {"CounterTop": "next to the stove (assumed)",
                                         "Cabinet": "assumed", "Shelf": "assumed"}),
    "bleach": ("cleaning", "m", [("AI2-THOR", "SprayBottle (proxy)", AI2THOR_URL),
                                 ("YCB", "Table II ID 20 Windex Bottle (proxy, 1022 g)", YCB_URL)],
               {"Cabinet": _T, "Shelf": _T}),
    "detergent": ("cleaning", "s", [("AI2-THOR", "SoapBottle (proxy)", AI2THOR_URL)],
                  {"Cabinet": _T, "CounterTop": _T, "Shelf": _T, "Sink": _T}),
    "cleaning_spray": ("cleaning", "s", [("AI2-THOR", "SprayBottle", AI2THOR_URL)],
                       {"Cabinet": _T, "Shelf": _T, "CounterTop": _T}),
    "medicine_bottle": ("medicine", "xs", [], {c: "medicine kept where it is taken (no AI2-THOR type)" for c in
                                               ("SideTable", "DiningTable", "CounterTop", "Drawer", "Cabinet",
                                                "Shelf", "CoffeeTable")}),
    "pill_box": ("medicine", "xs", [], {c: "a weekly pill organizer (no AI2-THOR type)" for c in
                                        ("SideTable", "DiningTable", "CounterTop", "Drawer", "Shelf",
                                         "CoffeeTable", "TVStand")}),
    "vitamins": ("medicine", "xs", [], {c: "supplements (no AI2-THOR type)" for c in
                                        ("DiningTable", "CounterTop", "Desk", "Shelf", "SideTable", "Cabinet")}),
    "remote": ("electronics", "s", [("AI2-THOR", "RemoteControl", AI2THOR_URL)],
               {"Sofa": _T, "ArmChair": _T, "TVStand": _T, "CoffeeTable": _T, "SideTable": _T}),
    "phone": ("electronics", "xs", [("AI2-THOR", "CellPhone", AI2THOR_URL)],
              {"Sofa": _T, "ArmChair": _T, "Desk": _T, "Bed": _T, "DiningTable": _T, "CoffeeTable": _T,
               "SideTable": _T, "Drawer": _T, "TVStand": _T}),
    "charger": ("electronics", "xs", [], {"Desk": "a phone charger at the desk (assumed)",
                                          "SideTable": "a charger on the bedside table (assumed)",
                                          "Drawer": "assumed"}),
    "hair_dryer": ("electronics", "m", [], {"Sink": "kept by the bathroom sink (assumed)", "Cabinet": "assumed",
                                            "Drawer": "assumed"}),
    "book": ("personal", "s", [("AI2-THOR", "Book", AI2THOR_URL)],
             {"Shelf": _T, "Desk": _T, "SideTable": _T, "CoffeeTable": _T, "Bed": _T, "Sofa": _T,
              "ArmChair": _T, "TVStand": _T}),
    "notebook": ("personal", "s", [("AI2-THOR", "Book (proxy)", AI2THOR_URL)],
                 {"Desk": _T, "Shelf": _T, "SideTable": _T, "Drawer": _T}),
    "pen": ("personal", "xs", [("AI2-THOR", "Pen", AI2THOR_URL), ("YCB", "Table II ID 35 Permanent Marker (proxy)", YCB_URL)],
            {"Desk": _T, "Drawer": _T, "SideTable": _T}),
    "glasses": ("personal", "xs", [], {c: "eyeglasses (no AI2-THOR type)" for c in
                                       ("SideTable", "CoffeeTable", "Desk", "TVStand", "Bed", "ArmChair",
                                        "Drawer", "Shelf")}),
    "keys": ("personal", "xs", [("AI2-THOR", "KeyChain", AI2THOR_URL), ("YCB", "Table II ID 38 Keys (6 g)", YCB_URL)],
             {"CoffeeTable": _T, "SideTable": _T, "Desk": _T, "Drawer": _T, "Shelf": _T,
              "ShoeCabinet": "keys kept in the entryway shoe cabinet (assumed)"}),
    "wallet": ("personal", "xs", [("AI2-THOR", "CreditCard (proxy)", AI2THOR_URL)],
               {"SideTable": _T, "Desk": _T, "Drawer": _T, "CoffeeTable": _T,
                "ShoeCabinet": "left in the entryway (assumed)"}),
    "towel": ("textile", "m", [("AI2-THOR", "Cloth (proxy)", AI2THOR_URL)],
              {"Cabinet": _T, "Drawer": _T, "Shelf": _T, "Sink": _T,
               "Wardrobe": "folded towels in a wardrobe (assumed)", "DryingRack": "drying (assumed)"}),
    "shirt": ("textile", "m", [("AI2-THOR", "Cloth (proxy)", AI2THOR_URL)],
              {"Drawer": _T, "Sofa": _T, "ArmChair": _T, "Wardrobe": "hung in a wardrobe (assumed)",
               "Bed": "clothes left on the bed (assumed)", "DryingRack": "drying (assumed)"}),
    "socks": ("textile", "xs", [("AI2-THOR", "Cloth (proxy)", AI2THOR_URL)],
              {"Drawer": _T, "Sofa": _T, "Bed": "left on the bed (assumed)", "DryingRack": "drying (assumed)",
               "Wardrobe": "socks kept in the closet's drawers (assumed)"}),
    "tissue_box": ("household", "m", [("AI2-THOR", "TissueBox", AI2THOR_URL)],
                   {"SideTable": _T, "CoffeeTable": _T, "Desk": _T, "TVStand": _T, "Shelf": _T, "DiningTable": _T}),
    "plastic_bag": ("household", "s", [], {"Drawer": "assumed", "Cabinet": "assumed", "CounterTop": "assumed"}),
    "toy_car": ("toy", "s", [], {c: "a small toy (no AI2-THOR type)" for c in
                                 ("Box", "Desk", "Bed", "CoffeeTable", "Shelf")}),
    "teddy_bear": ("toy", "m", [("AI2-THOR", "TeddyBear", AI2THOR_URL)],
                   {"Bed": _T, "Sofa": _T, "ArmChair": _T, "Desk": _T, "Box": "soft toys in a toy box (assumed)"}),
    "ball": ("toy", "s", [("AI2-THOR", "BasketBall (proxy)", AI2THOR_URL)],
             {"Sofa": _T, "ArmChair": _T, "Bed": _T, "Desk": _T, "Box": "toys in a toy box (assumed)"}),
    "blocks": ("toy", "s", [("YCB", "Table II ID 71 Colored Wood Blocks (proxy)", YCB_URL)],
               {c: "toy blocks (no AI2-THOR type)" for c in ("Box", "Desk", "CoffeeTable", "Shelf")}),
    "lighter": ("fire", "xs", [], {c: "a lighter kept away from children (no AI2-THOR type)" for c in
                                   ("Drawer", "Shelf", "Cabinet", "SideTable")}),
    "matches": ("fire", "xs", [], {c: "matches (no AI2-THOR type)" for c in ("Drawer", "Cabinet", "Shelf")}),
    "candle": ("decor", "s", [("AI2-THOR", "Candle", AI2THOR_URL)],
               {"Shelf": _T, "TVStand": _T, "SideTable": _T, "DiningTable": _T, "CoffeeTable": _T, "Drawer": _T,
                "Cabinet": _T}),
    "foil": ("cooking", "s", [("AI2-THOR", "AluminumFoil", AI2THOR_URL)],
             {"Drawer": "kitchen drawer (AI2-THOR lists no receptacle for AluminumFoil)", "Cabinet": "assumed",
              "CounterTop": "assumed"}),
    "vase": ("decor", "m", [("AI2-THOR", "Vase", AI2THOR_URL)],
             {"Shelf": _T, "TVStand": _T, "SideTable": _T, "DiningTable": _T, "CoffeeTable": _T}),
    "houseplant": ("decor", "l", [("AI2-THOR", "HousePlant", AI2THOR_URL)],
                   {c: "a potted plant (AI2-THOR HousePlant is not pickupable; assumed places)" for c in
                    ("Shelf", "TVStand", "SideTable", "CounterTop")}),
    "water_jug": ("drink", "l", [], {"CounterTop": "a large water container (assumed)",
                                     "Shelf": "stored in the utility room (assumed)"}),
    "laundry_basket": ("household", "l", [("AI2-THOR", "LaundryHamper", AI2THOR_URL)],
                       {"Bed": "brought to the bed to fold laundry (assumed)",
                        "Shelf": "on the utility-room shelf (assumed)"}),
    "tv": ("electronics", "xl", [("AI2-THOR", "Television", AI2THOR_URL)],
           {"TVStand": "a television stands on a TV stand (AI2-THOR Television is not pickupable)"}),
}

# masses from YCB Table II where the class is a YCB object (others: the nominal weights above, assumed)
_YCB_MASS = {"mug": 0.118, "plate": 0.279, "bowl": 0.147, "spoon": 0.030, "fork": 0.034, "apple": 0.068,
             "orange": 0.047, "banana": 0.066, "scissors": 0.082, "keys": 0.006, "canned_soup": 0.349,
             "cereal_box": 0.510, "glass": 0.133}


def _attach_realism():
    out = {}
    for cls, c in CLASSES.items():
        cat, size, prov, typical = _REAL[cls]
        mass = _YCB_MASS.get(cls, c.weight_kg)
        out[cls] = {
            "category": cat, "size_class": size,
            "provenance": [{"set": s, "item": i, "url": u} for s, i, u in prov],
            "provenance_note": "" if prov else "no published object set has this item; a common household item (assumed)",
            "mass_kg": mass, "mass_source": "YCB Table II" if cls in _YCB_MASS else "nominal (assumed)",
            "graspable": c.grasp_class not in ("heavy", "fixed") and mass <= PAYLOAD_KG,
            "liquid": "liquid" in c.tags, "fragile": "fragile" in c.tags, "sharp": "sharp" in c.tags,
            "food": "food" in c.tags, "hot": "hot" in c.tags,
            "packaged_liquid": "liquid" in c.tags,   # every liquid in the catalog is in a bottle / carton / jug
            "typical_receptacles": {r: ({"source": "AI2-THOR Default Compatible Receptacles", "url": AI2THOR_URL}
                                        if why == _T else {"assumed": True, "reason": why})
                                    for r, why in sorted(typical.items())},
        }
    return out


REALISM: dict = _attach_realism()


def place_category(place) -> str:
    """The receptacle category of a Place (explicit `category` or by its id prefix)."""
    explicit = getattr(place, "category", None)
    if explicit:
        return explicit
    return PLACE_CATEGORY.get(place.id.split("@", 1)[0], "")


def size_fits(cls: str, category: str) -> bool:
    cap = (RECEPTACLES.get(category) or {}).get("capacity_size_class")
    if cap is None:
        return False
    return SIZE_ORDER.index(REALISM[cls]["size_class"]) <= SIZE_ORDER.index(cap)


def is_typical(cls: str, category: str) -> bool:
    return category in REALISM[cls]["typical_receptacles"]
