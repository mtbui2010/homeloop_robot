"""Object classes (EN/KO names, grasp class, tags), colours, place tags and message keys.

Weights are nominal values used only for the payload check (``weight_kg > PAYLOAD_KG`` -> the robot
cannot lift it); they are not calibrated quantities. ``PAYLOAD_KG`` is the OK-Robot payload limit
(docs/calibration.md, OKR Sec. V-E) and is also the `carry.payload_kg` profile parameter.
"""

from __future__ import annotations

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
    _c("dumbbell", "dumbbell", "아령", "heavy", 3.0, ("metal",), ()),
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
# utterance (case-insensitive substring) for `said_to(person, key)` to hold.
MESSAGES: dict = {
    "dinner_ready": {"en": [["dinner", "ready"], ["supper", "ready"]], "ko": [["저녁", "준비"], ["저녁", "드세요"]]},
    "lunch_ready": {"en": [["lunch", "ready"]], "ko": [["점심", "준비"], ["점심", "드세요"]]},
    "take_medicine": {"en": [["medicine"], ["pill"]], "ko": [["약", "드"], ["약", "먹"]]},
    "drink_water": {"en": [["drink", "water"]], "ko": [["물", "드세요"], ["물", "마"]]},
    "phone_call": {"en": [["phone", "call"], ["call", "for you"]], "ko": [["전화"]]},
    "door_visitor": {"en": [["door"]], "ko": [["문"]]},
    "laundry_done": {"en": [["laundry", "done"], ["laundry", "finished"]], "ko": [["빨래", "다"], ["세탁", "끝"]]},
    "wake_up": {"en": [["wake up"], ["time to get up"]], "ko": [["일어나"], ["일어날"]]},
    "bedtime": {"en": [["bed"]], "ko": [["잘 시간"], ["주무"]]},
    "leaving_soon": {"en": [["leaving", "minutes"], ["leave", "minutes"]], "ko": [["출발"], ["나가"]]},
    "tv_off": {"en": [["turn off", "tv"], ["switch off", "tv"]], "ko": [["텔레비전", "꺼"], ["티비", "꺼"]]},
    "come_kitchen": {"en": [["come", "kitchen"]], "ko": [["주방", "와"], ["부엌", "와"]]},
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


def message_matches(key: str, text: str, lang: str) -> bool:
    """True when ``text`` contains every keyword of one alternative of ``MESSAGES[key][lang]``."""
    alts = (MESSAGES.get(key) or {}).get(lang) or []
    t = (text or "").lower()
    return any(all(k.lower() in t for k in alt) for alt in alts)


def class_names(cls: str, lang: str) -> list:
    """Every name of a class in a language: the name first, then aliases."""
    c = CLASSES[cls]
    out = [c.name[lang]] + list((c.aliases or {}).get(lang) or [])
    return out
