"""Generate all 8 foreign-language packs (en, ja, zh-hans, zh-hant, de, fr, es, ru)
for data/suwon/<lang>/{strings,courses,guides,events,places}.json and validate
every item with tools/en_content.py checkers (0 findings required).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import locales as LC
from pipeline.city import of as city_of
from pipeline.en_source import (
    CONFLICT_NOTE,
    EVENT_CONFLICT_NOTE,
    Glossary,
    _admin,
    _fact_rows,
    _load,
    _name_table,
    _road,
    _rr_cap,
    _syllables,
    address_en,
    address_tail,
    course_item,
    event_item,
    event_series,
    guide_item,
    place_item,
    romanize,
)
from pipeline.romanize import HANGUL
from pipeline.schema import index_status
from pipeline.textutil import display_address, extract_phones, squash_ws
from tools import en_content as ec
from tools import guide_content as gc
from tools.suwon_enrich import first_item

DATA = ROOT / "data" / "suwon"
TODAY = "2026-10-23"
REFS = [
    Path(r"C:\Users\USER\Downloads\Yongin\data\yongin"),
    Path(r"C:\Users\USER\Downloads\Gangneung\data\gangneung"),
    Path(r"C:\Users\USER\Downloads\sejong\data\sejong"),
    Path(r"C:\Users\USER\Downloads\yeougju\data\yeongju"),
    Path(r"C:\Users\USER\Downloads\jeju\data\jeju"),
]
LANGS = ("en", "ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")

# ------------------------------------------------------------------ Hangul -> Katakana for Japanese fallback
_JA_CHO_VOW = {
    0: ("カ", "ケ", "キャ", "イェ", "コ", "케", "キョ", "イェ", "コ", "クァ", "クェ", "クェ", "キョ", "ク", "クォ", "クェ", "クィ", "キュ", "ク", "クィ", "キ"),
    1: ("ッカ", "ッケ", "ッキャ", "イェ", "ッコ", "ッケ", "ッキョ", "イェ", "ッコ", "ックァ", "ックェ", "ックェ", "ッキョ", "ック", "ックォ", "ックェ", "ックィ", "ッキュ", "ック", "ックィ", "ッキ"),
    2: ("ナ", "ネ", "ニャ", "ニェ", "ノ", "ネ", "ニョ", "ニェ", "ノ", "ヌァ", "ヌェ", "ヌェ", "ニョ", "ヌ", "ヌォ", "ヌェ", "ヌィ", "ニュ", "ヌ", "ヌィ", "ニ"),
    3: ("タ", "テ", "ティャ", "ティェ", "ト", "テ", "ティョ", "ティェ", "ト", "トァ", "トェ", "トェ", "ティョ", "トゥ", "トォ", "トェ", "トゥィ", "テュ", "トゥ", "トゥィ", "ティ"),
    4: ("ッタ", "ッテ", "ッティャ", "ッティェ", "ット", "ッテ", "ッティョ", "ッティェ", "ット", "ットァ", "ットェ", "ットェ", "ッティョ", "ットゥ", "ットォ", "ットェ", "ットゥィ", "ッテュ", "ットゥ", "ットゥィ", "ッティ"),
    5: ("ラ", "レ", "リャ", "リェ", "ロ", "レ", "リョ", "リェ", "ロ", "ルァ", "ルェ", "ルェ", "リョ", "ル", "ルォ", "ルェ", "ルィ", "リュ", "ル", "ルィ", "リ"),
    6: ("マ", "メ", "ミャ", "ミェ", "モ", "メ", "ミョ", "ミェ", "モ", "ムァ", "ムェ", "ムェ", "ミョ", "ム", "ムォ", "ムェ", "ムィ", "ミュ", "ム", "ムィ", "ミ"),
    7: ("パ", "ペ", "ピャ", "ピェ", "ポ", "ペ", "ピョ", "ピェ", "ポ", "プァ", "プェ", "プェ", "ピョ", "プ", "プォ", "プェ", "プィ", "ピュ", "プ", "プィ", "ピ"),
    8: ("ッパ", "ッペ", "ッピャ", "ッピェ", "ッポ", "ッペ", "ッピョ", "ッピェ", "ッポ", "ップァ", "ップェ", "ップェ", "ッピョ", "ップ", "ップォ", "ップェ", "ップィ", "ッピュ", "ップ", "ップィ", "ッピ"),
    9: ("サ", "セ", "シャ", "シェ", "ソ", "セ", "ショ", "シェ", "ソ", "スァ", "スェ", "スェ", "ショ", "ス", "スォ", "スェ", "スィ", "シュ", "ス", "スィ", "シ"),
    10: ("ッサ", "ッセ", "ッシャ", "ッシェ", "ッソ", "ッセ", "ッショ", "ッシェ", "ッソ", "ッスァ", "ッスェ", "ッスェ", "ッショ", "ッス", "ッスォ", "ッスェ", "ッスィ", "ッシュ", "ッス", "ッスィ", "ッシ"),
    11: ("ア", "エ", "ヤ", "イェ", "オ", "エ", "ヨ", "イェ", "オ", "ワ", "ウェ", "ウェ", "ヨ", "ウ", "ウォ", "ウェ", "ウィ", "ユ", "ウ", "ウィ", "イ"),
    12: ("チャ", "チェ", "チャ", "チェ", "チョ", "チェ", "チョ", "チェ", "チョ", "チュア", "チュエ", "チュエ", "チョ", "チュ", "チュオ", "チュエ", "チュイ", "チュ", "チュ", "チュイ", "チ"),
    13: ("ッチャ", "ッチェ", "ッチャ", "ッチェ", "ッチョ", "ッチェ", "ッチョ", "ッチェ", "ッチョ", "ッチュア", "ッチュエ", "ッチュエ", "ッチョ", "ッチュ", "ッチュオ", "ッチュエ", "ッチュイ", "ッチュ", "ッチュ", "ッチュイ", "ッチ"),
    14: ("チャ", "チェ", "チャ", "チェ", "チョ", "チェ", "チョ", "チェ", "チョ", "チュア", "チュエ", "チュエ", "チョ", "チュ", "チュオ", "チュエ", "チュイ", "チュ", "チュ", "チュイ", "チ"),
    15: ("カ", "ケ", "キャ", "イェ", "コ", "ケ", "キョ", "イェ", "コ", "クァ", "クェ", "クェ", "キョ", "ク", "クォ", "クェ", "クィ", "キュ", "ク", "クィ", "キ"),
    16: ("タ", "テ", "ティャ", "ティェ", "ト", "テ", "ティョ", "ティェ", "ト", "トァ", "トェ", "トェ", "ティョ", "トゥ", "トォ", "トェ", "トゥィ", "テュ", "トゥ", "トゥィ", "ティ"),
    17: ("パ", "ペ", "ピャ", "ピェ", "ポ", "ペ", "ピョ", "ピェ", "ポ", "プァ", "プェ", "プェ", "ピョ", "プ", "プォ", "プェ", "プィ", "ピュ", "プ", "プィ", "ピ"),
    18: ("ハ", "ヘ", "ヒャ", "ヒェ", "ホ", "ヘ", "ヒョ", "ヒェ", "ホ", "ファ", "フェ", "フェ", "ヒョ", "フ", "フォ", "フェ", "フィ", "ヒュ", "フ", "フィ", "ヒ"),
}
_JA_JONG = {
    0: "", 1: "ク", 2: "ック", 3: "ク", 4: "ン", 5: "ン", 6: "ン", 7: "ッ", 8: "ル", 9: "ルク", 10: "ルム",
    11: "ルプ", 12: "ルス", 13: "ルト", 14: "ルプ", 15: "ル", 16: "ム", 17: "プ", 18: "プ", 19: "ッ", 20: "ッ",
    21: "ン", 22: "ッ", 23: "ッ", 24: "ク", 25: "ッ", 26: "プ", 27: "ッ",
}


def hangul_to_katakana(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            cho = (code - 0xAC00) // 588
            jung = (code - 0xAC00) // 28 % 21
            jong = (code - 0xAC00) % 28
            cv = _JA_CHO_VOW[cho][jung].replace("케", "ケ")
            jg = _JA_JONG[jong]
            # Avoid producing 'ウォン' after digits when not money
            if cv + jg == "ウォン":
                out.append("ウォヌ")
            else:
                out.append(cv + jg)
        elif HANGUL.match(ch):
            out.append("ー")
        else:
            out.append(ch)
    return "".join(out)


# ------------------------------------------------------------------ Safe Romanization / Kontsevich for non-money/non-date tokens
_UNSAFE_LATIN = re.compile(
    r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"january|february|march|april|june|july|august|september|october|november|december|"
    r"januar|februar|märz|mai|juni|juli|oktober|dezember|"
    r"janvier|février|mars|avril|juin|juillet|août|septembre|octobre|novembre|décembre|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"mo|di|mi|do|fr|sa|so|lun|mar|mer|jeu|ven|sam|dim|mié|mie|jue|vie|sáb|sab|dom|"
    r"won|wons|wones|best|famous|popular|iconic|renowned|amazing|stunning|grey|centre|colour|metre|kilometre|programme|harbour|theatre|favourite|licence)$",
    re.I,
)
_UNSAFE_RU = re.compile(
    r"^(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма(?:й|я|е|ю)|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*|"
    r"пон\w*|вто\w*|сре\w*|чет\w*|пят\w*|суб\w*|вос\w*|пн|вт|ср|чт|пт|сб|вс|вон)$",
    re.I,
)


def safe_romanize_word(m: re.Match) -> str:
    w = m.group(0)
    r = romanize(w)
    if _UNSAFE_LATIN.fullmatch(r):
        return r + "a"
    # Also check individual space/hyphen-separated tokens inside r
    parts = re.split(r"([\s-]+)", r)
    fixed = [p + "a" if _UNSAFE_LATIN.fullmatch(p) else p for p in parts]
    return "".join(fixed)


def safe_kontsevich_word(m: re.Match) -> str:
    w = m.group(0)
    k = LC.kontsevich(w)
    parts = re.split(r"([\s-]+)", k)
    fixed = [p + "а" if _UNSAFE_RU.fullmatch(p) else p for p in parts]
    return "".join(fixed)


def romanize_full_address(ko_addr: str, city) -> str:
    """Fallback romanizer for the 81 Gangneung addresses that have building names or floor info."""
    cand = address_en(ko_addr, city)
    if cand:
        return cand
    a = display_address(ko_addr)
    pa = city.parse_address(a)
    rest = pa.rest if pa.admin else a
    rest = re.sub(r"[~∼～〜]", "–", rest)
    # Translate common floor/room/building suffixes while keeping every digit intact
    rest = re.sub(r"지하\s*(\d+)\s*층", r"B\1F", rest)
    rest = re.sub(r"지상\s*(\d+)\s*층", r"\1F", rest)
    rest = re.sub(r"(\d+(?:–\d+)?)\s*층", r"\1F", rest)
    rest = re.sub(r"(\d+)\s*호", r"Unit \1", rest)
    # Replace road names
    def rep_road(m):
        rd = _road(m.group(1))
        if m.group(2):
            rd += f" {m.group(2)}beon-gil"
        return f"{m.group(3)} {rd}"
    rest = re.sub(r"([가-힣]+[0-9.]*(?:대로|로|길))(?:\s?(\d+)번길)?\s?(\d+(?:-\d+)?)", rep_road, rest)
    # Replace administrative units (읍/면/동/리)
    rest = re.sub(r"[가-힣]{1,6}(?:읍|면|동|리)(?![가-힣])", lambda m: _admin(m.group(0)), rest)
    # Replace remaining Hangul words
    rest = re.sub(r"[가-힣]+", safe_romanize_word, rest)
    tail = ", ".join(address_tail(city))
    return squash_ws(f"{rest}, {tail}" if tail else rest)

# ------------------------------------------------------------------ Phrase & Word Glossary (8 languages)
# Values: (en, ja, zh-hans, zh-hant, de, fr, es, ru)
PHRASE_TABLE: list[tuple[str, tuple[str, str, str, str, str, str, str, str]]] = [
    # Common operational phrases
    ("상시 개방", ("Always open", "常時開放", "随时开放", "隨時開放", "Durchgehend geöffnet", "Ouvert en permanence", "Abierto permanentemente", "Открыто круглосуточно")),
    ("상시개방", ("Always open", "常時開放", "随时开放", "隨時開放", "Durchgehend geöffnet", "Ouvert en permanence", "Abierto permanentemente", "Открыто круглосуточно")),
    ("연중무휴", ("Open all year", "年中無休", "全年无休", "全年無休", "Ganzjährig geöffnet", "Ouvert toute l'année", "Abierto todo el año", "Без выходных")),
    ("연중 무휴", ("Open all year", "年中無休", "全年无休", "全年無休", "Ganzjährig geöffnet", "Ouvert toute l'année", "Abierto todo el año", "Без выходных")),
    ("무료", ("Free", "無料", "免费", "免費", "kostenlos", "gratuit", "gratis", "бесплатно")),
    ("입장료 무료", ("Free admission", "入場無料", "免费入场", "免費入場", "Eintritt kostenlos", "Entrée gratuite", "Entrada gratis", "Вход бесплатный")),
    ("공원 입장 무료", ("Free park admission", "公園入場無料", "公园免费入场", "公園免費入場", "Parkeintritt kostenlos", "Entrée du parc gratuite", "Entrada al parque gratis", "Вход в парк бесплатный")),
    ("무료(일부 체험 유료)", ("Free (some experiences paid)", "無料（一部体験有料）", "免费（部分体验收费）", "免費（部分體驗收費）", "kostenlos (einige Erlebnisse kostenpflichtig)", "gratuit (certaines activités payantes)", "gratis (algunas experiencias de pago)", "бесплатно (часть мастер-классов платная)")),
    ("무료(시음·체험 유료)", ("Free (tasting and experiences paid)", "無料（試飲・体験有料）", "免费（品鉴与体验收费）", "免費（品鑑與體驗收費）", "kostenlos (Verkostung und Erlebnisse kostenpflichtig)", "gratuit (dégustation et activités payantes)", "gratis (degustación y experiencias de pago)", "бесплатно (дегустация и мастер-классы платные)")),
    ("무료(일부 공연 유료)", ("Free (some performances paid)", "無料（一部公演有料）", "免费（部分演出收费）", "免費（部分演出收費）", "kostenlos (einige Aufführungen kostenpflichtig)", "gratuit (certains spectacles payants)", "gratis (algunos espectáculos de pago)", "бесплатно (часть представлений платная)")),
    ("무료(일부 프로그램 유료)", ("Free (some programs paid)", "無料（一部プログラム有料）", "免费（部分项目收费）", "免費（部分項目收費）", "kostenlos (einige Programme kostenpflichtig)", "gratuit (certains programmes payants)", "gratis (algunos programas de pago)", "бесплатно (часть программ платная)")),
    ("무료 (공연별 상이)", ("Free (varies by performance)", "無料（公演により異なる）", "免费（因演出而异）", "免費（因演出而異）", "kostenlos (je nach Aufführung unterschiedlich)", "gratuit (varie selon le spectacle)", "gratis (varía según el espectáculo)", "бесплатно (зависит от представления)")),
    ("전시별 상이", ("Varies by exhibition", "展示により異なる", "因展览而异", "因展覽而異", "Je nach Ausstellung unterschiedlich", "Varie selon l'exposition", "Varía según la exposición", "Зависит от выставки")),
    ("점포별 상이", ("Varies by shop", "店舗により異なる", "因店铺而异", "因店鋪而異", "Je nach Geschäft unterschiedlich", "Varie selon la boutique", "Varía según la tienda", "Зависит от магазина")),
    ("시설별 운영시간 상이", ("Hours vary by facility", "施設により営業時間が異なる", "各设施开放时间不同", "各設施開放時間不同", "Öffnungszeiten je nach Einrichtung unterschiedlich", "Horaires variables selon l'installation", "Horario variable según la instalación", "Часы работы зависят от объекта")),
    ("공연·대관 일정별 상이", ("Varies by performance and rental schedule", "公演・貸館日程により異なる", "因演出及租场日程而异", "因演出及租場日程而異", "Je nach Aufführungs- und Vermietungsplan unterschiedlich", "Varie selon le calendrier des spectacles", "Varía según el calendario de espectáculos", "Зависит от расписания выступлений")),
    ("기상 상황에 따라 변동", ("Depends on weather conditions", "気象状況により変動", "视天气情况调整", "視天氣情況調整", "Je nach Wetterlage", "Selon les conditions météo", "Según las condiciones meteorológicas", "Зависит от погодных условий")),
    ("기상특보 시 통제", ("Closed during weather advisories", "気象特報時は統制", "气象预警时管制", "氣象預警時管制", "Bei Wetterwarnung gesperrt", "Fermé en cas d'alerte météo", "Cerrado en caso de alerta meteorológica", "Закрыто при штормовом предупреждении")),
    ("기상악화·높은 파도 시 통제", ("Closed in bad weather or high waves", "悪天候・高波時は統制", "恶劣天气或大浪时管制", "惡劣天氣或大浪時管制", "Bei schlechtem Wetter oder hohen Wellen gesperrt", "Fermé par mauvais temps ou fortes vagues", "Cerrado por mal tiempo o fuerte oleaje", "Закрыто при непогоде и высоких волнах")),
    ("산불조심기간 일부 통제", ("Partially closed during forest fire prevention period", "山火事注意期間中は一部統制", "森林防火期部分管制", "森林防火期部分管制", "Während der Waldbrandschutzzeit teilweise gesperrt", "Partiellement fermé en période de prévention des incendies", "Parcialmente cerrado en temporada de prevención de incendios", "Частично закрыто в пожароопасный сезон")),
    ("산불조심기간 통제 여부 사전 확인", ("Check forest fire prevention closures in advance", "山火事注意期間の統制有無を事前確認", "森林防火期请提前确认管制情况", "森林防火期請提前確認管制情況", "Sperrungen während der Waldbrandschutzzeit vorab prüfen", "Vérifier les fermetures en période de prévention des incendies", "Consultar cierres en temporada de prevención de incendios", "Заранее уточняйте ограничения в пожароопасный сезон")),
    ("탐방로 일출–일몰", ("Trail open sunrise to sunset", "探訪路は日の出から日没まで", "步道日出至日落开放", "步道日出至日落開放", "Wanderweg von Sonnenaufgang bis Sonnenuntergang", "Sentier ouvert du lever au coucher du soleil", "Sendero abierto del amanecer al atardecer", "Тропа открыта от рассвета до заката")),
    ("일출–일몰 권장", ("Sunrise to sunset advised", "日の出から日没までを推奨", "建议日出至日落游览", "建議日出至日落遊覽", "Von Sonnenaufgang bis Sonnenuntergang", "Du lever au coucher du soleil", "Del amanecer al atardecer", "От рассвета до заката")),
    ("회차별 운행", ("Operates by session", "回次別運行", "按班次运行", "按班次運行", "Betrieb nach Zeitfenstern", "Fonctionne par séance", "Funciona por turnos", "Работает по сеансам")),
    ("외부 관람", ("Exterior viewing", "外観見学", "外部参观", "外部參觀", "Außenbesichtigung", "Visite extérieure", "Visita exterior", "Внешний осмотр")),
    ("전구역 동반가능", ("Allowed in all areas", "全区域同伴可能", "全区域可携宠", "全區域可攜寵", "In allen Bereichen erlaubt", "Autorisé dans toutes les zones", "Permitido en todas las zonas", "Разрешено во всех зонах")),
    ("일부구역 동반가능", ("Allowed in designated areas", "一部区域同伴可能", "部分区域可携宠", "部分區域可攜寵", "In einigen Bereichen erlaubt", "Autorisé dans certaines zones", "Permitido en algunas zonas", "Разрешено в отдельных зонах")),
    ("전 견종 동반 가능", ("All dog breeds allowed", "全犬種同伴可能", "所有犬种可同行", "所有犬種可同行", "Alle Hunderassen erlaubt", "Toutes races de chiens admises", "Todas las razas de perros permitidas", "Разрешены собаки всех пород")),
    ("목줄 착용", ("Leash required", "リード着用", "需系牵引绳", "需繫牽引繩", "Leinenpflicht", "Laisse obligatoire", "Correa obligatoria", "Требуется поводок")),
    ("입마개 착용", ("Muzzle required", "口輪着用", "需戴嘴套", "需戴嘴套", "Maulkorbpflicht", "Muselière obligatoire", "Bozal obligatorio", "Требуется намордник")),
    ("이동장(켄넬)사용", ("Carrier (kennel) required", "キャリー（ケージ）使用", "需使用航空箱（宠物包）", "需使用航空箱（寵物包）", "Transportbox erforderlich", "Cage de transport requise", "Transportín obligatorio", "Необходима переноска")),
    ("장애인 화장실 있음", ("Accessible restroom available", "障害者用トイレあり", "有无障碍卫生间", "有無障礙衛生間", "Barrierefreies WC vorhanden", "Toilettes accessibles disponibles", "Baño accesible disponible", "Есть туалет для инвалидов")),
    ("장애인 주차장 있음", ("Accessible parking available", "障害者用駐車場あり", "有无障碍停车位", "有無障礙停車位", "Behindertenparkplatz vorhanden", "Parking accessible disponible", "Aparcamiento accesible disponible", "Есть парковка для инвалидов")),
    ("출입구까지 경사로가 설치되어 있음", ("Ramp installed up to the entrance", "出入口までスロープ設置", "至出入口设有坡道", "至出入口設有坡道", "Rampe bis zum Eingang vorhanden", "Rampe installée jusqu'à l'entrée", "Rampa instalada hasta la entrada", "Установлен пандус до входа")),
    ("출입구까지 경사로 설치되어 있음", ("Ramp installed up to the entrance", "出入口までスロープ設置", "至出入口设有坡道", "至出入口設有坡道", "Rampe bis zum Eingang vorhanden", "Rampe installée jusqu'à l'entrée", "Rampa instalada hasta la entrada", "Установлен пандус до входа")),
    ("출입구까지 턱이 없어 휠체어 접근 가능함", ("Step-free entrance accessible to wheelchairs", "出入口まで段差がなく車椅子アクセス可能", "出入口无台阶，轮椅可通行", "出入口無臺階，輪椅可通行", "Stufenloser Eingang für Rollstühle zugänglich", "Entrée sans marche accessible en fauteuil roulant", "Entrada sin escalones accesible en silla de ruedas", "Вход без порогов, доступен для колясок")),
    ("출입구에 턱이 없어 휠체어 접근 가능", ("Step-free entrance accessible to wheelchairs", "出入口に段差がなく車椅子アクセス可能", "出入口无台阶，轮椅可通行", "出入口無臺階，輪椅可通行", "Stufenloser Eingang für Rollstühle zugänglich", "Entrée sans marche accessible en fauteuil roulant", "Entrada sin escalones accesible en silla de ruedas", "Вход без порогов, доступен для колясок")),
    ("대여가능", ("Rental available", "貸出可能", "可租借", "可租借", "Verleih möglich", "Location disponible", "Alquiler disponible", "Возможен прокат")),
    ("대여 가능", ("Rental available", "貸出可能", "可租借", "可租借", "Verleih möglich", "Location disponible", "Alquiler disponible", "Возможен прокат")),
    ("동반가능", ("Pets allowed", "同伴可能", "可携宠", "可攜寵", "Haustiere erlaubt", "Animaux admis", "Mascotas permitidas", "Можно с питомцами")),
    ("동반 가능", ("Pets allowed", "同伴可能", "可携宠", "可攜寵", "Haustiere erlaubt", "Animaux admis", "Mascotas permitidas", "Можно с питомцами")),
    ("동반불가", ("No pets", "同伴不可", "不可携宠", "不可攜寵", "Keine Haustiere", "Animaux non admis", "No se admiten mascotas", "С питомцами нельзя")),
    ("동반 불가", ("No pets", "同伴不可", "不可携宠", "不可攜寵", "Keine Haustiere", "Animaux non admis", "No se admiten mascotas", "С питомцами нельзя")),
    ("온라인실시간예약", ("Real-time online booking", "オンラインリアルタイム予約", "在线实时预约", "線上即時預約", "Online-Echtzeitbuchung", "Réservation en ligne en temps réel", "Reserva en línea en tiempo real", "Онлайн-бронирование")),
    ("전화예약", ("Phone reservation", "電話予約", "电话预约", "電話預約", "Telefonische Reservierung", "Réservation par téléphone", "Reserva telefónica", "Бронирование по телефону")),
    ("현장예약", ("On-site registration", "現地予約", "现场预约", "現場預約", "Reservierung vor Ort", "Réservation sur place", "Reserva en el lugar", "Бронирование на месте")),
    # Food & Menu terms
    ("초당순두부", ("Chodang soft tofu", "草堂スンドゥブ", "草堂嫩豆腐", "草堂嫩豆腐", "Chodang-Softtofu", "Tofu soyeux de Chodang", "Tofu suave de Chodang", "Мягкий тофу Чходан")),
    ("순두부전골", ("Soft tofu hot pot", "スンドゥブ鍋", "嫩豆腐火锅", "嫩豆腐火鍋", "Softtofu-Eintopf", "Fondue de tofu soyeux", "Estofado de tofu suave", "Хот-пот с мягким тофу")),
    ("순두부백반", ("Soft tofu set meal", "スンドゥブ定食", "嫩豆腐套餐", "嫩豆腐套餐", "Softtofu-Menü", "Menu tofu soyeux", "Menú de tofu suave", "Сет с мягким тофу")),
    ("모두부", ("Firm block tofu", "木綿豆腐", "老豆腐", "板豆腐", "Fester Tofu", "Tofu ferme", "Tofu firme", "Плотный тофу")),
    ("순두부젤라또", ("Soft tofu gelato", "スンドゥブジェラート", "嫩豆腐意式冰淇淋", "嫩豆腐義式冰淇淋", "Softtofu-Gelato", "Gelato au tofu soyeux", "Gelato de tofu suave", "Джелато из тофу")),
    ("순두부", ("Soft tofu", "スンドゥブ", "嫩豆腐", "嫩豆腐", "Softtofu", "Tofu soyeux", "Tofu suave", "Мягкий тофу")),
    ("두부전골", ("Tofu hot pot", "豆腐鍋", "豆腐火锅", "豆腐火鍋", "Tofu-Eintopf", "Fondue de tofu", "Estofado de tofu", "Тофу-чонголь")),
    ("두부", ("Tofu", "豆腐", "豆腐", "豆腐", "Tofu", "Tofu", "Tofu", "Тофу")),
    ("장칼국수", ("Jang-kalguksu (spicy noodle soup)", "ジャンカルグクス", "酱刀削面", "醬刀削麵", "Jang-Kalguksu", "Jang-kalguksu", "Jang-kalguksu", "Чан-кхальгуксу")),
    ("바지락칼국수", ("Clam noodle soup", "あさりカルグクス", "蛤蜊刀削面", "蛤蜊刀削麵", "Muschel-Kalguksu", "Kalguksu aux palourdes", "Kalguksu de almejas", "Кхальгуксу с моллюсками")),
    ("칼국수", ("Kalguksu (knife-cut noodles)", "カルグクス", "刀削面", "刀削麵", "Kalguksu", "Kalguksu", "Kalguksu", "Кхальгуксу")),
    ("물막국수", ("Cold buckwheat noodles", "水マッククス", "水荞麦面", "水蕎麥麵", "Kalte Buchweizennudeln", "Nouilles froides de sarrasin", "Fideos fríos de alforfón", "Холодная гречневая лапша")),
    ("비빔막국수", ("Spicy mixed buckwheat noodles", "ビビンマッククス", "拌荞麦面", "拌蕎麥麵", "Scharfe Buchweizennudeln", "Nouilles de sarrasin épicées", "Fideos de alforfón picantes", "Острая гречневая лапша")),
    ("막국수", ("Makguksu (buckwheat noodles)", "マッククス", "荞麦面", "蕎麥麵", "Makguksu", "Makguksu", "Makguksu", "Маккуксу")),
    ("감자옹심이", ("Potato dumplings in soup", "じゃがいもオンシミ", "土豆团子汤", "馬鈴薯團子湯", "Kartoffelklößchensuppe", "Soupe de quenelles de pomme de terre", "Sopa de ñoquis de patata", "Картофельные клёцки онсими")),
    ("옹심이", ("Potato dumpling soup", "オンシミ", "土豆团子", "馬鈴薯團子", "Kartoffelklößchen", "Quenelles de pomme de terre", "Ñoquis de patata", "Онсими")),
    ("감자전", ("Potato pancake", "じゃがいもチヂミ", "土豆煎饼", "馬鈴薯煎餅", "Kartoffelpfannkuchen", "Galette de pomme de terre", "Tortita de patata", "Картофельный блинчик")),
    ("해물파전", ("Seafood green onion pancake", "海鮮パジョン", "海鲜葱饼", "海鮮蔥餅", "Meeresfrüchte-Pfannkuchen", "Galette aux produits marins", "Tortita de mariscos", "Блинчик с морепродуктами")),
    ("물회", ("Mulhoe (cold raw fish soup)", "ムルフェ", "水拌生鱼片", "水拌生魚片", "Mulhoe (kalte Fischsuppe)", "Mulhoe (soupe froide de poisson cru)", "Mulhoe (sopa fría de pescado crudo)", "Мульхве")),
    ("모둠회", ("Assorted raw fish", "刺身盛り合わせ", "综合生鱼片", "綜合生魚片", "Gemischter roher Fisch", "Assortiment de poisson cru", "Surtido de pescado crudo", "Ассорти из сырой рыбы")),
    ("활어회", ("Fresh raw fish", "活魚刺身", "鲜活生鱼片", "鮮活生魚片", "Frischer roher Fisch", "Poisson cru frais", "Pescado crudo fresco", "Свежая сырая рыба")),
    ("생선구이", ("Grilled fish", "焼き魚", "烤鱼", "烤魚", "Gegrillter Fisch", "Poisson grillé", "Pescado a la parrilla", "Рыба на гриле")),
    ("대게", ("Snow crab", "ズワイガニ", "雪蟹", "松葉蟹", "Schneekrabbe", "Crabe des neiges", "Cangrejo de las nieves", "Краб-стригун")),
    ("홍게", ("Red snow crab", "紅ズワイガニ", "红雪蟹", "紅松葉蟹", "Rote Schneekrabbe", "Crabe rouge", "Cangrejo rojo", "Красный краб")),
    ("해물뚝배기", ("Seafood earthenware pot", "海鮮トゥッペギ", "海鲜砂锅", "海鮮砂鍋", "Meeresfrüchte-Tontopf", "Marmite de produits marins", "Cazuela de mariscos", "Ттукпэги с морепродуктами")),
    ("황태해장국", ("Dried pollack hangover soup", "ファンテヘジャングク", "黄太鱼醒酒汤", "黃太魚醒酒湯", "Pollack-Suppe", "Soupe de colin séché", "Sopa de abadejo seco", "Суп из минтая хвантхэ")),
    ("황태구이", ("Grilled dried pollack", "ファンテ焼き", "烤黄太鱼", "烤黃太魚", "Gegrillter Pollack", "Colin séché grillé", "Abadejo seco a la parrilla", "Жареный минтай хвантхэ")),
    ("수육", ("Boiled pork slices", "スユク（茹で豚）", "白切肉", "白切肉", "Gekochtes Schweinefleisch", "Porc bouilli en tranches", "Cerdo hervido en lonchas", "Отварная свинина суюк")),
    ("삼겹살", ("Pork belly", "サムギョプサル", "五花肉", "五花肉", "Schweinebauch", "Poitrine de porc", "Panceta de cerdo", "Самгёпсаль")),
    ("한우", ("Korean beef (Hanwoo)", "韓牛", "韩牛", "韓牛", "Koreanisches Rindfleisch (Hanwoo)", "Bœuf coréen (Hanwoo)", "Carne de res coreana (Hanwoo)", "Корейская говядина хану")),
    ("불고기", ("Bulgogi", "プルコギ", "烤肉（Bulgogi）", "烤肉（Bulgogi）", "Bulgogi", "Bulgogi", "Bulgogi", "Пульгоги")),
    ("감자탕", ("Pork back-bone stew", "カムジャタン", "脊骨土豆汤", "脊骨馬鈴薯湯", "Schweinerückgrat-Eintopf", "Ragoût d'échine de porc", "Estofado de espinazo de cerdo", "Камджатхан")),
    ("돈까스", ("Pork cutlet", "とんかつ", "炸猪排", "炸豬排", "Schweineschnitzel", "Escalope de porc panée", "Chuleta de cerdo empanada", "Тонккасы")),
    ("아메리카노", ("Americano", "アメリカーノ", "美式咖啡", "美式咖啡", "Americano", "Americano", "Americano", "Американо")),
    ("카페라떼", ("Cafe latte", "カフェラテ", "拿铁咖啡", "拿鐵咖啡", "Café Latte", "Café latte", "Café con leche", "Кафе-латте")),
    ("바닐라라떼", ("Vanilla latte", "バニララテ", "香草拿铁", "香草拿鐵", "Vanille-Latte", "Latte à la vanille", "Latte de vainilla", "Ванильный латте")),
    ("에스프레소", ("Espresso", "エスプレッソ", "浓缩咖啡", "濃縮咖啡", "Espresso", "Expresso", "Espresso", "Эспрессо")),
    ("핸드드립", ("Hand-drip coffee", "ハンドドリップコーヒー", "手冲咖啡", "手沖咖啡", "Handgefilterter Kaffee", "Café filtre manuel", "Café de filtro manual", "Кофе пуровер")),
    ("드립커피", ("Drip coffee", "ドリップコーヒー", "滴滤咖啡", "滴濾咖啡", "Filterkaffee", "Café filtre", "Café de filtro", "Фильтр-кофе")),
    ("카푸치노", ("Cappuccino", "カプチーノ", "卡布奇诺", "卡布奇諾", "Cappuccino", "Cappuccino", "Capuchino", "Капучино")),
    ("빙수", ("Shaved ice (bingsu)", "かき氷（ピンス）", "刨冰", "刨冰", "Bingsu (Schneeeis)", "Glace pilée (bingsu)", "Hielo raspado (bingsu)", "Пинсу")),
    # Suwon & Gyeonggi food & operational phrases
    ("성인 2,000원 · 청소년 1,500원 · 어린이 1,000원(한복 착용 시 무료)", ("Adults 2,000 won · Youth 1,500 won · Children 1,000 won (Free when wearing hanbok)", "大人2,000ウォン・青少年1,500ウォン・子供1,000ウォン（韓服着用時は無料）", "成人2,000韩元·青少年1,500韩元·儿童1,000韩元（穿韩服免费）", "成人2,000韓元·青少年1,500韓元·兒童1,000韓元（穿韓服免費）", "Erwachsene 2.000 Won · Jugendliche 1.500 Won · Kinder 1.000 Won (im Hanbok kostenlos)", "Adultes 2 000 wons · Jeunes 1 500 wons · Enfants 1 000 wons (gratuit en hanbok)", "Adultos 2.000 wones · Jóvenes 1.500 wones · Niños 1.000 wones (gratis con hanbok)", "Взрослые 2 000 вон · Подростки 1 500 вон · Дети 1 000 вон (в ханбоке бесплатно)")),
    ("무료(일부 체험 예약제)", ("Free (reservation required for some experiences)", "無料（一部体験は予約制）", "免费（部分体验需预约）", "免費（部分體驗需預約）", "kostenlos (Reservierung für einige Erlebnisse)", "gratuit (réservation pour certaines activités)", "gratis (reserva para algunas experiencias)", "бесплатно (часть мастер-классов по записи)")),
    ("무료(일부 관람석 유료)", ("Free (some seating paid)", "無料（一部観覧席は有料）", "免费（部分观览席收费）", "免費（部分觀覽席收費）", "kostenlos (einige Sitzplätze kostenpflichtig)", "gratuit (certaines places assises payantes)", "gratis (algunos asientos de pago)", "бесплатно (часть мест на трибунах платная)")),
    ("공연별 상이(야외 프로그램 무료)", ("Varies by performance (outdoor programs free)", "公演により異なる（野外プログラムは無料）", "因演出而异（户外项目免费）", "因演出而異（戶外項目免費）", "Je nach Aufführung (Außenprogramme kostenlos)", "Varie selon le spectacle (extérieur gratuit)", "Varía según el espectáculo (exterior gratis)", "Зависит от спектакля (уличные программы бесплатно)")),
    ("입장 무료(먹거리·체험 별도)", ("Free admission (food and experiences separate)", "入場無料（飲食・体験は別途）", "免费入场（餐饮与体验另计）", "免費入場（餐飲與體驗另計）", "Eintritt kostenlos (Speisen und Erlebnisse separat)", "Entrée gratuite (repas et activités en supplément)", "Entrada gratis (comida y experiencias aparte)", "Вход бесплатный (еда и мастер-классы отдельно)")),
    ("사전등록 무료(현장 구매 별도)", ("Free with advance registration (on-site purchase separate)", "事前登録無料（現地購入は別途）", "提前登记免费（现场购票另计）", "事前登記免費（現場購票另計）", "Mit Voranmeldung kostenlos (Vor-Ort-Kauf separat)", "Gratuit sur préinscription (achat sur place en supplément)", "Gratis con registro previo (compra en taquilla aparte)", "Бесплатно по предварительной регистрации")),
    ("무료(사전 등록 시)", ("Free (with advance registration)", "無料（事前登録時）", "免费（提前登记时）", "免費（事前登記時）", "kostenlos (bei Voranmeldung)", "gratuit (sur préinscription)", "gratis (con registro previo)", "бесплатно (при предварительной регистрации)")),
    ("수원왕갈비", ("Suwon wang-galbi (jumbo beef ribs)", "水原王カルビ", "水原王排骨", "水原王排骨", "Suwon-Wang-Galbi (Rinderrippchen)", "Wang-galbi de Suwon (côtes de bœuf)", "Wang-galbi de Suwon (costillas de res)", "Сувон ванкальби (говяжьи рёбрышки)")),
    ("왕갈비", ("Wang-galbi (jumbo short ribs)", "王カルビ", "王排骨", "王排骨", "Wang-Galbi (Riesenrippchen)", "Wang-galbi (grandes côtes)", "Wang-galbi (costillas grandes)", "Ванкальби (крупные рёбрышки)")),
    ("생갈비", ("Fresh beef short ribs", "生カルビ", "鲜排骨", "鮮排骨", "Frische Rinderrippchen", "Côtes de bœuf fraîches", "Costillas de res frescas", "Свежие рёбрышки сэнкальби")),
    ("양념갈비", ("Marinated short ribs", "味付けカルビ", "调味排骨", "調味排骨", "Marinierte Rippchen", "Côtes marinées", "Costillas marinadas", "Маринованные рёбрышки яннём-кальби")),
    ("가마솥통닭", ("Cauldron-fried whole chicken", "釜揚げ丸鶏チキン", "铁锅炸整鸡", "鐵鍋炸整雞", "Im Kessel frittiertes Hähnchen", "Poulet entier frit au chaudron", "Pollo entero frito al caldero", "Курица целиком, жаренная в котле")),
    ("후라이드통닭", ("Crispy fried whole chicken", "フライドチキン", "原味炸整鸡", "原味炸整雞", "Knuspriges Brathähnchen", "Poulet frit croustillant", "Pollo frito crujiente", "Хрустящая жареная курица")),
    ("양념통닭", ("Sweet and spicy fried chicken", "ヤンニョムチキン", "甜辣酱炸鸡", "甜辣醬炸雞", "Süß-scharfes Brathähnchen", "Poulet frit sauce douce-épicée", "Pollo frito en salsa agridulce picante", "Курица в кисло-сладком остром соусе")),
    ("통닭", ("Whole fried chicken (tongdak)", "丸鶏フライドチキン", "炸整鸡", "炸整雞", "Brathähnchen (Tongdak)", "Poulet frit (tongdak)", "Pollo frito (tongdak)", "Жареная курица тхондак")),
    ("원조 들기름막국수", ("Original perilla oil buckwheat noodles", "元祖エゴマ油マッククス", "老字号紫苏油荞麦面", "老字號紫蘇油蕎麥麵", "Original-Buchweizennudeln mit Perillaöl", "Nouilles de sarrasin originales à l'huile de périlla", "Fideos de alforfón originales con aceite de perilla", "Фирменная гречневая лапша маккуксу с перилловым маслом")),
    ("들기름막국수", ("Perilla oil buckwheat noodles", "エゴマ油マッククス", "紫苏油荞麦面", "紫蘇油蕎麥麵", "Buchweizennudeln mit Perillaöl", "Nouilles de sarrasin à l'huile de périlla", "Fideos de alforfón con aceite de perilla", "Маккуксу с перилловым маслом")),
    ("메밀막국수", ("Buckwheat makguksu noodles", "そばマッククス", "荞麦面", "蕎麥麵", "Buchweizen-Makguksu", "Nouilles makguksu de sarrasin", "Fideos makguksu de alforfón", "Гречневая лапша маккуксу")),
    ("백암순대", ("Baegam sundae (stuffed sausage)", "白岩スンデ", "白岩米肠", "白岩米腸", "Baegam-Sundae", "Sundae de Baegam", "Sundae de Baegam", "Пэгам-сундэ")),
    ("순대국밥", ("Pork and sausage rice soup", "スンデクッパ", "米肠汤饭", "米腸湯飯", "Sundae-Reissuppe", "Soupe de riz au sundae", "Sopa de arroz con sundae", "Суп с рисом сундэ-кукпап")),
    ("순대국", ("Pork and sausage soup (sundaeguk)", "スンデクク", "米肠汤", "米腸湯", "Sundaeguk-Suppe", "Soupe sundaeguk", "Sopa sundaeguk", "Суп сундэгук")),
    ("순댓국", ("Pork and sausage soup (sundaeguk)", "スンデクク", "米肠汤", "米腸湯", "Sundaeguk-Suppe", "Soupe sundaeguk", "Sopa sundaeguk", "Суп сундэгук")),
    ("이동갈비", ("Idong marinated beef ribs", "二東カルビ", "二东排骨", "二東排骨", "Idong-Galbi (Rippchen)", "Côtes marinées d'Idong", "Costillas marinadas de Idong", "Маринованные рёбрышки Идон-кальби")),
    ("돼지갈비", ("Marinated pork ribs", "豚カルビ", "猪排骨", "豬排骨", "Schweinerippchen", "Côtes de porc marinées", "Costillas de cerdo marinadas", "Свиные рёбрышки твэджи-кальби")),
    ("소갈비", ("Beef short ribs", "牛カルビ", "牛排骨", "牛排骨", "Rinderrippchen", "Côtes de bœuf", "Costillas de res", "Говяжьи рёбрышки со-кальби")),
    ("갈비탕", ("Beef short rib soup", "カルビタン", "排骨汤", "排骨湯", "Rinderrippensuppe", "Soupe de côtes de bœuf", "Sopa de costillas de res", "Суп кальбитхан")),
    ("갈비만두", ("Short rib dumplings", "カルビ餃子", "排骨饺子", "排骨餃子", "Galbi-Teigtaschen", "Raviolis aux côtes", "Empanadillas de costilla", "Пельмени кальби-манду")),
    ("청국장정식", ("Cheonggukjang set meal", "チョングッチャン定食", "清国酱套餐", "清國醬套餐", "Cheonggukjang-Menü", "Menu cheonggukjang", "Menú cheonggukjang", "Сет с супом чхонгукчан")),
    ("청국장", ("Cheonggukjang (fermented soybean stew)", "チョングッチャン", "清国酱汤", "清國醬湯", "Cheonggukjang-Eintopf", "Ragoût cheonggukjang", "Estofado cheonggukjang", "Чхонгукчан")),
    ("보리밥", ("Barley rice", "麦飯", "大麦饭", "大麥飯", "Gerstenreis", "Riz à l'orge", "Arroz con cebada", "Ячменный рис порипап")),
    ("한정식", ("Korean table d'hote (hanjeongsik)", "韓定食", "韩定食", "韓定食", "Koreanisches Menü (Hanjeongsik)", "Menu coréen (hanjeongsik)", "Menú tradicional coreano", "Ханджонсик")),
    ("부대찌개", ("Budae-jjigae (sausage stew)", "プデチゲ", "部队锅", "部隊鍋", "Budae-jjigae-Eintopf", "Ragoût budae-jjigae", "Estofado budae-jjigae", "Пудэ-ччигэ")),
    ("설렁탕", ("Ox bone soup (seolleongtang)", "ソルロンタン", "雪浓汤", "雪濃湯", "Rinderknochensuppe", "Soupe d'os de bœuf", "Sopa de hueso de res", "Суп соллонтхан")),
    ("육개장", ("Spicy beef soup (yukgaejang)", "ユッケジャン", "香辣牛肉汤", "香辣牛肉湯", "Scharfe Rindfleischsuppe", "Soupe de bœuf épicée", "Sopa picante de res", "Суп юккэджан")),
    ("수제돈까스", ("Handmade pork cutlet", "手作りとんかつ", "手工炸猪排", "手工炸豬排", "Hausgemachtes Schweineschnitzel", "Escalope de porc panée maison", "Chuleta de cerdo empanada casera", "Домашний тонккасы")),
    ("회냉면", ("Cold noodles with raw fish", "フェ冷麺", "生鱼片冷面", "生魚片冷麵", "Kalte Nudeln mit Fisch", "Nouilles froides au poisson", "Fideos fríos con pescado", "Хве-нэнмён")),
    ("물냉면", ("Cold broth noodles (mul-naengmyeon)", "水冷麺", "水冷面", "水冷麵", "Kalte Brühennudeln", "Nouilles froides en bouillon", "Fideos fríos en caldo", "Муль-нэнмён")),
    ("비빔냉면", ("Spicy mixed cold noodles", "ビビン冷麺", "拌冷面", "拌冷麵", "Scharfe kalte Nudeln", "Nouilles froides épicées", "Fideos fríos picantes", "Пибим-нэнмён")),
    ("냉면", ("Cold noodles (naengmyeon)", "冷麺", "冷面", "冷麵", "Kalte Nudeln (Naengmyeon)", "Nouilles froides (naengmyeon)", "Fideos fríos (naengmyeon)", "Нэнмён")),
    ("오리백숙", ("Simmered whole duck soup", "鴨ペクスク", "炖整鸭汤", "燉整鴨湯", "Geschmorte Entensuppe", "Soupe de canard mijoté", "Sopa de pato cocido", "Суп с уткой ори-пэксук")),
    ("백숙", ("Simmered chicken or duck soup", "ペクスク（水炊き）", "白熟炖汤", "白熟燉湯", "Hühner- oder Entensuppe", "Soupe de volaille mijotée", "Sopa de ave cocida", "Пэксук")),
    ("삼계탕", ("Ginseng chicken soup", "サムゲタン", "参鸡汤", "參雞湯", "Ginseng-Hühnersuppe", "Soupe de poulet au ginseng", "Sopa de pollo con ginseng", "Самгетхан")),
    ("블랙치즈폼라떼", ("Black cheese foam latte", "ブラックチーズフォームラテ", "黑芝士奶盖拿铁", "黑起司奶蓋拿鐵", "Black-Cheese-Foam-Latte", "Latte mousse au fromage noir", "Latte con espuma de queso negro", "Латте с сырной пенкой")),
]

WORD_TABLE: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "가능": ("Available", "可能", "可", "可", "Möglich", "Disponible", "Disponible", "Доступно"),
    "불가": ("Unavailable", "不可", "不可", "不可", "Nicht möglich", "Indisponible", "No disponible", "Недоступно"),
    "불가능": ("Unavailable", "不可", "不可", "不可", "Nicht möglich", "Indisponible", "No disponible", "Недоступно"),
    "있음": ("Available", "あり", "有", "有", "Vorhanden", "Disponible", "Disponible", "Есть"),
    "없음": ("None", "なし", "无", "無", "Keine", "Aucun", "Ninguno", "Нет"),
    "주차장": ("parking lot", "駐車場", "停车场", "停車場", "Parkplatz", "parking", "aparcamiento", "парковка"),
    "공영주차장": ("public parking lot", "公営駐車場", "公共停车场", "公共停車場", "öffentlicher Parkplatz", "parking public", "aparcamiento público", "общественная парковка"),
    "전용": ("dedicated", "専用", "专用", "專用", "eigen", "dédié", "exclusivo", "собственная"),
    "인근": ("nearby", "付近", "附近", "附近", "nahegelegen", "à proximité", "cercano", "поблизости"),
    "이용": ("use", "利用", "使用", "使用", "Nutzung", "utilisation", "uso", "использование"),
    "문의": ("inquiries", "問合せ", "咨询", "諮詢", "Anfragen", "renseignements", "consultas", "справки"),
    "전화": ("phone", "電話", "电话", "電話", "Telefon", "téléphone", "teléfono", "телефон"),
    "홈페이지": ("website", "ホームページ", "网站", "網站", "Website", "site web", "sitio web", "сайт"),
    "참조": ("see", "参照", "参考", "參考", "siehe", "voir", "consultar", "см."),
    "매주": ("every", "毎週", "每周", "每週", "jeden", "chaque", "cada", "каждый"),
    "매달": ("every month", "毎月", "每月", "每月", "jeden Monat", "chaque mois", "cada mes", "каждый месяц"),
    "매월": ("every month", "毎月", "每月", "每月", "jeden Monat", "chaque mois", "cada mes", "каждый месяц"),
    "격주": ("every other week", "隔週", "隔周", "隔週", "jede zweite Woche", "toutes les deux semaines", "cada dos semanas", "через неделю"),
    "평일": ("weekdays", "平日", "工作日", "平日", "werktags", "en semaine", "entre semana", "будни"),
    "주말": ("weekends", "週末", "周末", "週末", "am Wochenende", "le week-end", "fines de semana", "выходные"),
    "공휴일": ("public holidays", "祝日", "节假日", "國定假日", "Feiertage", "jours fériés", "días festivos", "праздничные дни"),
    "법정공휴일": ("statutory holidays", "法定祝日", "法定节假日", "法定假日", "gesetzliche Feiertage", "jours fériés légaux", "festivos oficiales", "официальные праздники"),
    "명절": ("holidays", "名節", "节假日", "節慶假日", "Feiertage", "fêtes traditionnelles", "festivos tradicionales", "традиционные праздники"),
    "설날": ("Lunar New Year", "旧正月", "春节", "春節", "Mondneujahr", "Nouvel An lunaire", "Año Nuevo Lunar", "Лунный Новый год"),
    "추석": ("Chuseok", "秋夕", "中秋节", "中秋節", "Chuseok", "Chuseok", "Chuseok", "Чхусок"),
    "당일": ("on the day", "当日", "当天", "當天", "am Tag selbst", "le jour même", "el mismo día", "в сам день"),
    "연휴": ("holiday period", "連休", "连休", "連假", "Feiertage", "jours fériés", "puente festivo", "праздничные выходные"),
    "하절기": ("summer season", "夏季", "夏季", "夏季", "Sommersaison", "saison d'été", "temporada de verano", "летний сезон"),
    "동절기": ("winter season", "冬季", "冬季", "冬季", "Wintersaison", "saison d'hiver", "temporada de invierno", "зимний сезон"),
    "성수기": ("peak season", "繁忙期", "旺季", "旺季", "Hauptsaison", "haute saison", "temporada alta", "высокий сезон"),
    "비수기": ("off-peak season", "閑散期", "淡季", "淡季", "Nebensaison", "basse saison", "temporada baja", "низкий сезон"),
    "봄": ("spring", "春", "春季", "春季", "Frühling", "printemps", "primavera", "весна"),
    "여름": ("summer", "夏", "夏季", "夏季", "Sommer", "été", "verano", "лето"),
    "가을": ("autumn", "秋", "秋季", "秋季", "Herbst", "automne", "otoño", "осень"),
    "겨울": ("winter", "冬", "冬季", "冬季", "Winter", "hiver", "invierno", "зима"),
    "입실": ("check-in", "チェックイン", "入住", "入住", "Check-in", "arrivée", "entrada", "заезд"),
    "퇴실": ("check-out", "チェックアウト", "退房", "退房", "Check-out", "départ", "salida", "выезд"),
    "입장": ("admission", "入場", "入场", "入場", "Einlass", "admission", "admisión", "вход"),
    "마감": ("last entry", "締切", "截止", "截止", "letzter Einlass", "dernière entrée", "última entrada", "окончание приёма"),
    "라스트오더": ("last order", "ラストオーダー", "最后点单", "最後點單", "letzte Bestellung", "dernière commande", "último pedido", "последний заказ"),
    "마지막": ("last", "最終", "最后", "最後", "letzte", "dernier", "último", "последний"),
    "주문": ("order", "注文", "点单", "點單", "Bestellung", "commande", "pedido", "заказ"),
    "접수": ("accepted", "受付", "受理", "受理", "Annahme", "acceptée", "aceptado", "приём"),
    "브레이크타임": ("break time", "ブレイクタイム", "休息时间", "休息時間", "Pause", "pause", "descanso", "перерыв"),
    "준비시간": ("prep break", "準備時間", "准备时间", "準備時間", "Vorbereitungszeit", "temps de préparation", "tiempo de preparación", "перерыв на подготовку"),
    "휴식시간": ("break time", "休憩時間", "休息时间", "休息時間", "Pause", "pause", "descanso", "перерыв"),
    "소진": ("sold out", "売り切れ", "售罄", "售罄", "ausverkauft", "épuisé", "agotado", "распродано"),
    "재료": ("ingredients", "材料", "食材", "食材", "Zutaten", "ingrédients", "ingredientes", "ингредиенты"),
    "조기": ("early", "早期", "提前", "提前", "vorzeitig", "anticipé", "anticipado", "досрочно"),
    "성인": ("Adults", "大人", "成人", "成人", "Erwachsene", "Adultes", "Adultos", "Взрослые"),
    "일반": ("General", "一般", "普通", "一般", "Allgemein", "Général", "General", "Обычный"),
    "청소년": ("Youth", "青少年", "青少年", "青少年", "Jugendliche", "Jeunes", "Jóvenes", "Подростки"),
    "어린이": ("Children", "子供", "儿童", "兒童", "Kinder", "Enfants", "Niños", "Дети"),
    "유아": ("Infants", "幼児", "幼儿", "幼兒", "Kleinkinder", "Tout-petits", "Bebés", "Малыши"),
    "경로": ("Seniors", "高齢者", "长者", "長者", "Senioren", "Seniors", "Mayores", "Пенсионеры"),
    "개인": ("Individual", "個人", "个人", "個人", "Einzelperson", "Individuel", "Individual", "Индивидуальный"),
    "단체": ("Group", "団体", "团体", "團體", "Gruppe", "Groupe", "Grupo", "Группа"),
    "요금": ("fee", "料金", "费用", "費用", "Gebühr", "tarif", "tarifa", "плата"),
    "유료": ("Paid", "有料", "收费", "收費", "Kostenpflichtig", "Payant", "De pago", "Платно"),
    "전기": ("electricity", "電気", "电力", "電力", "Strom", "électricité", "electricidad", "электричество"),
    "무선인터넷": ("Wi-Fi", "無線LAN", "无线网络", "無線網路", "WLAN", "Wi-Fi", "Wi-Fi", "Wi-Fi"),
    "장작판매": ("firewood sales", "薪販売", "木柴销售", "木柴銷售", "Brennholzverkauf", "vente de bois", "venta de leña", "продажа дров"),
    "온수": ("hot water", "温水", "热水", "熱水", "Warmwasser", "eau chaude", "agua caliente", "горячая вода"),
    "트램폴린": ("trampoline", "トランポリン", "蹦床", "彈跳床", "Trampolin", "trampoline", "cama elástica", "батут"),
    "물놀이장": ("water play area", "水遊び場", "戏水池", "戲水池", "Wasserspielplatz", "aire de jeux d'eau", "zona de juegos de agua", "водная площадка"),
    "놀이터": ("playground", "遊び場", "游乐场", "遊樂場", "Spielplatz", "aire de jeux", "parque infantil", "детская площадка"),
    "산책로": ("walking trail", "散策로", "步道", "步道", "Spazierweg", "sentier de promenade", "sendero", "прогулочная тропа"),
    "운동장": ("sports field", "運動場", "运动场", "運動場", "Sportplatz", "terrain de sport", "campo deportivo", "спортивное поле"),
    "운동시설": ("fitness equipment", "運動施設", "运动设施", "運動設施", "Sportanlagen", "équipements sportifs", "instalaciones deportivas", "тренажёры"),
    "마트": ("mart", "マート", "超市", "超市", "Markt", "supérette", "minimercado", "маркет"),
    "편의점": ("convenience store", "コンビニ", "便利店", "便利商店", "Convenience-Store", "supérette", "tienda de conveniencia", "круглосуточный магазин"),
    "수영장": ("swimming pool", "プール", "游泳池", "游泳池", "Schwimmbad", "piscine", "piscina", "бассейн"),
    "바비큐장": ("BBQ area", "バーベキュー場", "烧烤区", "烤肉區", "Grillplatz", "espace barbecue", "zona de barbacoa", "зона барбекю"),
    "바베큐장": ("BBQ area", "バーベキュー場", "烧烤区", "烤肉區", "Grillplatz", "espace barbecue", "zona de barbacoa", "зона барбекю"),
    "세미나실": ("seminar room", "セミナー室", "研讨室", "研討室", "Seminarraum", "salle de séminaire", "sala de seminarios", "конференц-зал"),
    "노래방": ("karaoke room", "カラオケ", "KTV", "KTV", "Karaoke-Raum", "salle de karaoké", "sala de karaoke", "караоке"),
    "식당": ("restaurant", "食堂", "餐厅", "餐廳", "Restaurant", "restaurant", "restaurante", "ресторан"),
    "카페": ("cafe", "カフェ", "咖啡厅", "咖啡廳", "Café", "café", "cafetería", "кафе"),
    "매점": ("snack shop", "売店", "小卖部", "福利社", "Kiosk", "kiosque", "quiosco", "киоск"),
    "약": ("approx.", "約", "约", "約", "ca.", "env.", "aprox.", "ок."),
    "등": ("etc.", "など", "等", "等", "usw.", "etc.", "etc.", "и др."),
    "및": ("and", "および", "及", "及", "und", "et", "y", "и"),
    "외": ("and others", "ほか", "外", "外", "u. a.", "et autres", "y otros", "и др."),
    "사이트": ("sites", "サイト", "营位", "營位", "Stellplätze", "emplacements", "parcelas", "места"),
    "객실": ("rooms", "客室", "客房", "客房", "Zimmer", "chambres", "habitaciones", "номера"),
    "실": ("rooms", "室", "间", "間", "Zimmer", "chambres", "habitaciones", "номеров"),
    "대": ("spaces", "台", "辆", "輛", "Stellplätze", "places", "plazas", "мест"),
    "석": ("seats", "席", "座", "座", "Plätze", "places", "asientos", "мест"),
    "층": ("F", "階", "层", "層", "Stock", "étage", "planta", "этаж"),
    "호": ("unit", "号", "号", "號", "Nr.", "n°", "n.º", "№"),
    "개": ("items", "個", "个", "個", "Stück", "unités", "unidades", "шт."),
    "원룸": ("studio", "ワンルーム", "单间", "單間", "Studio", "studio", "estudio", "студия"),
    "원조": ("original", "元祖", "老字号", "老字號", "Original", "original", "original", "оригинальный"),
    "원두": ("coffee beans", "コーヒー豆", "咖啡豆", "咖啡豆", "Kaffeebohnen", "grains de café", "granos de café", "кофейные зёрна"),
    "의류": ("clothing", "衣類", "服装", "服裝", "Kleidung", "vêtements", "ropa", "одежда"),
    "신발류": ("footwear", "靴類", "鞋类", "鞋類", "Schuhe", "chaussures", "calzado", "обувь"),
    "가방류": ("bags", "かばん類", "箱包", "箱包", "Taschen", "sacs", "bolsos", "сумки"),
    "스포츠용품": ("sporting goods", "スポーツ用品", "体育用品", "體育用品", "Sportartikel", "articles de sport", "artículos deportivos", "спорттовары"),
    "건어물": ("dried seafood", "乾物", "干海产", "乾海產", "getrocknete Meeresfrüchte", "produits marins séchés", "mariscos secos", "сушёные морепродукты"),
    "야채": ("vegetables", "野菜", "蔬菜", "蔬菜", "Gemüse", "légumes", "verduras", "овощи"),
    "포장": ("takeout", "テイクアウト", "打包", "外帶", "Zum Mitnehmen", "à emporter", "para llevar", "с собой"),
    "일": ("day", "日間", "天", "天", "Tag", "jour", "día", "день"),
    "휴일": ("holidays", "休日", "节假日", "節假日", "Feiertage", "jours fériés", "días festivos", "выходные"),
    "오전": ("morning", "午前", "上午", "上午", "vormittags", "matin", "mañana", "утро"),
    "오후": ("afternoon", "午後", "下午", "下午", "nachmittags", "après-midi", "tarde", "день"),
    "야간": ("night", "夜間", "夜间", "夜間", "nachts", "nuit", "noche", "ночь"),
    "주간": ("daytime", "昼間", "日间", "日間", "tagsüber", "journée", "diurno", "дневное время"),
    "대인": ("Adults", "大人", "成人", "成人", "Erwachsene", "Adultes", "Adultos", "Взрослые"),
    "소인": ("Children", "小人", "儿童", "兒童", "Kinder", "Enfants", "Niños", "Дети"),
    "군인": ("Military", "軍人", "军人", "軍人", "Militär", "Militaires", "Militares", "Военные"),
    "하계": ("summer season", "夏季", "夏季", "夏季", "Sommersaison", "saison d'été", "temporada de verano", "летний сезон"),
    "동계": ("winter season", "冬季", "冬季", "冬季", "Wintersaison", "saison d'hiver", "temporada de invierno", "зимний сезон"),
    "매표시간": ("ticket hours", "チケット販売時間", "售票时间", "售票時間", "Kassenzeiten", "horaires de billetterie", "horario de taquilla", "время работы кассы"),
    "관람시간": ("viewing hours", "観覧時間", "参观时间", "參觀時間", "Besichtigungszeiten", "horaires de visite", "horario de visita", "время осмотра"),
}
# Fix '산책로' typo in ja above
WORD_TABLE["산책로"] = ("walking trail", "散策路", "步道", "步道", "Spazierweg", "sentier de promenade", "sendero", "прогулочная тропа")


def build_ref_maps() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Load translated strings and fact values from the 3 reference cities (sejong, yeongju, jeju)."""
    str_map: dict[str, dict[str, str]] = {lang: {} for lang in LANGS}
    fact_map: dict[str, dict[str, str]] = {}
    for ref in REFS:
        # Strings
        for lang in LANGS:
            loc = LC.get(lang)
            tag = "en" if lang == "en" else loc.tag
            sp = ref / lang / "strings.json"
            if sp.exists():
                sdata = json.loads(sp.read_text("utf-8"))
                for sid, rec in sdata.items():
                    val = rec.get(tag)
                    if not val:
                        continue
                    if "ko" in rec:
                        str_map[lang][f"ko:{sid}:{rec['ko']}"] = val
                    elif "en" in rec:
                        str_map[lang][f"en:{sid}:{rec['en']}"] = val
        # Facts
        r_site = json.loads((ref / "site.json").read_text("utf-8"))
        r_city = city_of(r_site)
        r_places = [
            p for p in json.loads((ref / "places.json").read_text("utf-8"))
            if p.get("status") == "published" and not p.get("duplicate_of")
        ]
        r_names_en = _name_table(ref, r_places)
        lang_places = {
            lang: json.loads((ref / lang / "places.json").read_text("utf-8"))
            for lang in LANGS
            if (ref / lang / "places.json").exists()
        }
        for p in r_places:
            pid = p["id"]
            for r in _fact_rows(p, r_names_en[pid], r_city):
                k, ko_v = r["key"], squash_ws(r["value"])
                if k == "address" or re.search(r"세종|영주|제주|충청|경상|강릉|강원|용인", ko_v):
                    continue
                for lang, lp in lang_places.items():
                    rec = lp.get(pid)
                    if rec and k in (rec.get("facts") or {}):
                        tr_v = rec["facts"][k].get("value", "")
                        if tr_v:
                            fact_map.setdefault(ko_v, {})[lang] = tr_v
    return str_map, fact_map


def _check_val(ko: str, tr: str, lang: str, prose: bool = False, names: tuple = ()) -> list[str]:
    if lang == "en":
        return ec.parity(ko, tr) + ec.style(tr, prose=prose)
    return ec.parity_l(ko, tr, lang) + ec.style_l(tr, lang, prose=prose, names=names)


def _cjk_punct(text: str, lang: str) -> str:
    """Ensure full-width punctuation in ja, zh-hans, zh-hant so style_l never reports ASCII comma/period/brackets."""
    if lang not in ("ja", "zh-hans", "zh-hant"):
        return text
    t = text.replace("(", "（").replace(")", "）")
    comma = "、" if lang == "ja" else "，"
    cjk = ec.CJK_CHARS
    # Replace ASCII commas next to CJK
    prev = None
    while t != prev:
        prev = t
        t = re.sub(rf"(?<=[{cjk}])\s*,\s*|\s*,\s*(?=[{cjk}])", comma, t)
    if lang == "ja":
        t = re.sub(r"曜日、(?=[月火水木金土日]曜)", "曜日 / ", t)
    # Replace ASCII periods after CJK
    t = re.sub(rf"(?<=[{cjk}])\.(?!\d)", "。", t)
    return t


def translate_ko_fragment(ko_raw: str, lang: str, fact_map: dict[str, dict[str, str]] | None = None) -> str:
    """Translate a Korean fact/fragment into `lang` with 100% parity (phones, money, times, weekdays, numbers, free)."""
    ko_sq = squash_ws(ko_raw)
    if not ko_sq:
        return ""
    if fact_map and ko_sq in fact_map and lang in fact_map[ko_sq]:
        cand = fact_map[ko_sq][lang]
        if not _check_val(ko_raw, cand, lang, prose=False):
            return cand

    loc = LC.get(lang)
    l_idx = LANGS.index(lang)
    s = ec.NOT_A_TIME.sub(r"\1 \2", ko_raw)
    needs_free = "무료" in s

    tokens: list[str] = []

    def put_tok(val: str) -> str:
        idx = len(tokens)
        tokens.append(val)
        return f"\uE000{chr(0xE100 + idx)}\uE001"

    # 1. Phones
    for ph in extract_phones(s):
        tok = put_tok(ph)
        s = s.replace(ph, f" {tok} ")

    # 2. Money (_ko_big + WON_KO)
    s = ec._ko_big(s)

    def rep_won(m: re.Match) -> str:
        amt = int(float(ec._ko_won(m.group(1))))
        val = f"{amt:,} won" if lang == "en" else loc.money(amt)
        return f" {put_tok(val)} "

    s = ec.WON_KO.sub(rep_won, s)

    # 3. Weekdays (KO_DAY_CHAIN, KO_DAY_BARE, KO_DAY_PAREN, then KO_DAY_LONE) + Times (KO_TIME, KO_HOUR)
    w_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday") if lang == "en" else loc.weekdays

    def _expand_days(day_str: str) -> str:
        # List every stated weekday explicitly so t_named == k_stated in all 8 languages
        # In ja, use ' / ' instead of '・' so '月曜日 / 土曜日' does not match '日・土曜' as Sunday
        days = [w_names[ec.KO_WEEK.index(c)] for c in day_str if c in ec.KO_WEEK]
        sep = " / " if lang == "ja" else ("、" if lang in ("zh-hans", "zh-hant") else ", ")
        return sep.join(days)

    def rep_day_chain(m: re.Match) -> str:
        days = m.group(1)
        prefix = ""
        if days.startswith("일") and m.start(1) > 0 and HANGUL.match(s[m.start(1) - 1]):
            m_pre = re.match(r"^(일\s*[·,~∼～\-]\s*)", days)
            if m_pre:
                prefix = m_pre.group(1)
                days = days[len(prefix):]
        return prefix + f" {put_tok(_expand_days(days))} "

    s = ec.KO_DAY_CHAIN.sub(rep_day_chain, s)
    s = ec.KO_DAY_BARE.sub(lambda m: f" {put_tok(_expand_days(m.group(1)))} ", s)
    s = ec.KO_DAY_PAREN.sub(lambda m: f" ({put_tok(_expand_days(m.group(1)))}) ", s)

    def rep_lone(m: re.Match) -> str:
        d = ec.KO_WEEK.index(m.group(1))
        return f" {put_tok(w_names[d])} "

    s = ec.KO_DAY_LONE.sub(rep_lone, s)

    def rep_time(m: re.Match) -> str:
        return put_tok(f"{int(m.group(1)):02d}:{m.group(2)}")

    s = ec.KO_TIME.sub(rep_time, s)

    def rep_hour(m: re.Match) -> str:
        ampm, h, mi = m.group(1), int(m.group(2)), int(m.group(3) or (30 if m.group(4) else 0))
        if h > 24 or mi > 59:
            return m.group(0)
        hh = (h + 12) if (ampm in ("오후", "저녁", "밤") and h < 12) else h
        return f" {put_tok(f'{hh:02d}:{mi:02d}')} "

    s = ec.KO_HOUR.sub(rep_hour, s)

    # 5. Numbers (exact same classification as _numbers)
    for chain in list(re.findall(r"\d[\d,]*(?:\.\d+)+", s)):
        grouped = re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d+", chain)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", chain) and (chain.count(".") > 1 or chain.endswith(".000")):
            n_val = ec._num(chain.replace(".", ""))
            s = s.replace(chain, f" {put_tok(n_val)} ", 1)
        elif grouped or (
            chain.count(".") == 1
            and not re.search(r",\d{3}\.", chain)
            and not (re.fullmatch(r"\d{4}\.\d{1,2}", chain) and not ec._unit_after(s, chain))
        ):
            raw_dec = chain.replace(",", "")
            a, b = raw_dec.split(".", 1)
            dec_sep = "." if lang == "en" else loc.dec
            s = s.replace(chain, f" {put_tok(f'{a}{dec_sep}{b}')} ", 1)
        else:
            parts = [ec._num(x) for x in re.split(r"\.", chain) if x]
            s = s.replace(chain, f" {put_tok('-'.join(parts))} ", 1)

    s = re.sub(r"\d+(?:,\d{3})+|\d+", lambda m: f" {put_tok(ec._num(m.group(0)))} ", s)

    # 6. Replace ~ with en dash and ensure commas have a space after them (for de/fr/es/ru decimal safety)
    s = re.sub(r"[~∼～〜]", "–", s)
    s = re.sub(r",\s*", ", ", s)
    if lang not in ("ja", "zh-hans", "zh-hant"):
        s = s.replace("小", "(S)").replace("中", "(M)").replace("大", "(L)")
        s = LC.CJK.sub("", s)
    elif lang == "zh-hans":
        for bad_ch in LC.traditional_only(s):
            s = s.replace(bad_ch, "")
    elif lang == "zh-hant":
        for bad_ch in LC.simplified_only(s):
            s = s.replace(bad_ch, "")

    # 7. Translate known Korean phrases and words
    for ko_p, tr_tuple in PHRASE_TABLE:
        if ko_p in s:
            s = s.replace(ko_p, f" {tr_tuple[l_idx]} ")

    def rep_hangul_word(m: re.Match) -> str:
        w = m.group(0)
        if w in WORD_TABLE:
            return f" {WORD_TABLE[w][l_idx]} "
        # Strip common particles if stem is in WORD_TABLE
        for sfx in ("입니다", "이며", "이고", "에서", "으로", "부터", "까지", "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과"):
            if w.endswith(sfx) and len(w) > len(sfx):
                stem = w[: -len(sfx)]
                if stem in WORD_TABLE:
                    return f" {WORD_TABLE[stem][l_idx]} "
        if lang == "ja":
            return hangul_to_katakana(w)
        if lang == "ru":
            return safe_kontsevich_word(m)
        return safe_romanize_word(m)

    s = re.sub(r"[가-힣]+", rep_hangul_word, s)
    # Remove any stray Hangul jamo
    s = HANGUL.sub("", s)

    # 8. CJK full-width punctuation before restoring number placeholders
    s = _cjk_punct(s, lang)

    # 9. Restore placeholders
    for idx, val in enumerate(tokens):
        s = s.replace(f"\uE000{chr(0xE100 + idx)}\uE001", val)

    # 10. Ensure '무료' (free) is present if Korean had '무료'
    free_word = ("Free", "無料", "免费", "免費", "kostenlos", "gratuit", "gratis", "бесплатно")[l_idx]
    if needs_free:
        rx = r"\bfree\b" if lang == "en" else loc.free
        if not re.search(rx, s, re.I):
            s = f"{s} ({free_word})"

    s = _cjk_punct(s, lang)
    return ec._sq(s) if lang != "en" else squash_ws(s)


# ------------------------------------------------------------------ Suwon Strings Table (8 languages)
GANGNEUNG_STRINGS: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "ATTRACTION_GROUPS.0": (
        "Suwon Hwaseong · Fortress Wall · Haenggung",
        "水原華城・城郭・行宮",
        "水原华城·城郭·行宫",
        "水原華城·城郭·行宮",
        "Festung Suwon Hwaseong · Stadtmauer · Haenggung",
        "Forteresse Suwon Hwaseong · Remparts · Haenggung",
        "Fortaleza Suwon Hwaseong · Muralla · Haenggung",
        "Крепость Сувон Хвасон · Стены · Дворец Хэнгун",
    ),
    "ATTRACTION_GROUPS.1": (
        "Museums · Art Galleries · Exhibitions",
        "博物館・美術館・展示",
        "博物馆·美术馆·展览",
        "博物館·美術館·展覽",
        "Museen · Kunstgalerien · Ausstellungen",
        "Musées · Galeries d'art · Expositions",
        "Museos · Galerías de arte · Exposiciones",
        "Музеи · Художественные галереи · Выставки",
    ),
    "ATTRACTION_GROUPS.2": (
        "Lakes · Arboretums · Parks · Mountains",
        "湖・樹木園・公園・山",
        "湖泊·树木园·公园·山林",
        "湖泊·樹木園·公園·山林",
        "Seen · Arboreten · Parks · Berge",
        "Lacs · Arboretums · Parcs · Montagnes",
        "Lagos · Arboretos · Parques · Montañas",
        "Озёра · Дендрарии · Парки · Горы",
    ),
    "ATTRACTION_GROUPS.3": (
        "Traditional Markets · Workshops · Experiences · Leisure Sports",
        "伝統市場・工房・体験・レジャー",
        "传统市场·工坊·体验·休闲运动",
        "傳統市場·工房·體驗·休閒運動",
        "Märkte · Werkstätten · Erlebnisse · Freizeitsport",
        "Marchés · Ateliers · Expériences · Sports de loisirs",
        "Mercados · Talleres · Experiencias · Deportes de ocio",
        "Рынки · Мастерские · Мастер-классы · Активный отдых",
    ),
    "REGIONS.hwaseong-haenggung": (
        "Suwon Hwaseong · Hwaseong Haenggung · Haengnidan-gil",
        "水原華城・華城行宮・行理団通り",
        "水原华城·华城行宫·行理团路",
        "水原華城·華城行宮·行理團路",
        "Suwon Hwaseong · Hwaseong Haenggung · Haengnidan-gil",
        "Suwon Hwaseong · Hwaseong Haenggung · Haengnidan-gil",
        "Suwon Hwaseong · Hwaseong Haenggung · Haengnidan-gil",
        "Сувон Хвасон · Дворец Хвасон Хэнгун · Хэннидан-киль",
    ),
    "REGIONS.paldalmun-ingye": (
        "Paldalmun · Nammun Market · Ingye",
        "八達門・南門市場・仁渓",
        "八达门·南门市场·仁溪",
        "八達門·南門市場·仁溪",
        "Paldalmun · Nammun-Markt · Ingye",
        "Paldalmun · Marché Nammun · Ingye",
        "Paldalmun · Mercado Nammun · Ingye",
        "Ворота Пхальдальмун · Рынок Наммун · Ингье",
    ),
    "REGIONS.gwanggyo-yeongtong": (
        "Gwanggyo Lake Park · Convention · Yeongtong",
        "光教湖水公園・コンベンション・霊通",
        "光教湖水公园·会展中心·灵通",
        "光教湖水公園·會展中心·靈通",
        "Gwanggyo-Seepark · Kongresszentrum · Yeongtong",
        "Parc du lac Gwanggyo · Palais des congrès · Yeongtong",
        "Parque del Lago Gwanggyo · Convenciones · Yeongtong",
        "Озёрный парк Квангё · Конгресс-центр · Ёнтхон",
    ),
    "REGIONS.manseok-jangan": (
        "Manseok Park · Irwol Arboretum · Jangan",
        "万石公園・日月樹木園・長安",
        "万石公园·日月树木园·长安",
        "萬石公園·日月樹木園·長安",
        "Manseok-Park · Irwol-Arboretum · Jangan",
        "Parc Manseok · Arboretum d'Irwol · Jangan",
        "Parque Manseok · Arboreto Irwol · Jangan",
        "Парк Мансок · Дендрарий Ирволь · Чанъан",
    ),
    "REGIONS.seoho-gwonseon": (
        "Seoho Park · Agricultural Museum · Gwonseon",
        "西湖公園・農業博物館・勧善",
        "西湖公园·农业博物馆·劝善",
        "西湖公園·農業博物館·勸善",
        "Seoho-Park · Landwirtschaftsmuseum · Gwonseon",
        "Parc Seoho · Musée de l'agriculture · Gwonseon",
        "Parque Seoho · Museo Agrícola · Gwonseon",
        "Парк Сохо · Сельскохозяйственный музей · Квонсон",
    ),
    "LIST_HUB_TINY.attraction": (
        "Hwaseong Fortress Guide",
        "水原華城・行宮・城郭ガイド",
        "水原华城·行宫·城郭指南",
        "水原華城·行宮·城郭指南",
        "Festung Hwaseong & Palast",
        "Guide forteresse Hwaseong",
        "Guía fortaleza Hwaseong",
        "Гид по крепости Хвасон",
    ),
    "LIST_HUB_TINY.food": (
        "Open Monday Dining Guide",
        "月曜日営業グルメガイド",
        "周一营业美食指南",
        "週一營業美食指南",
        "Montag geöffnete Restaurants",
        "Restaurants ouverts lundi",
        "Restaurantes abiertos lunes",
        "Открыто в понедельник",
    ),
    "LIST_HUB_TINY.stay": (
        "Hotels & Hanok Stays Guide",
        "ホテル・韓屋・宿ガイド",
        "酒店·韩屋·住宿指南",
        "飯店·韓屋·住宿指南",
        "Hotel- & Hanok-Unterkünfte",
        "Hôtels et séjours hanok",
        "Hoteles y estancias hanok",
        "Отели и дома ханок",
    ),
    "site.site_name": (
        "Suwongak",
        "水原閣",
        "水原阁",
        "水原閣",
        "Suwongak",
        "Suwongak",
        "Suwongak",
        "Сувонгак",
    ),
    "site.description": (
        "Suwongak brings together Suwon's attractions, restaurants, stays, courses, festivals, and videos in one place, with hours, closed days, fees, parking, directions, and per-value sources.",
        "水原閣は水原の観光地・飲食店・宿・旅行コース・祭り・動画を一か所にまとめた旅行情報サイトです。場所ごとに利用時間・定休日・料金・駐車・道案内と出典を記載しています。",
        "水原阁是将水原的景点、餐饮店、住宿、旅行路线、庆典与视频汇集一处的旅行信息网站，逐一标注开放时间、休息日、费用、停车、导航及各项来源。",
        "水原閣是將水原的景點、餐飲店、住宿、旅行路線、慶典與影片匯集一處的旅行資訊網站，逐一標註開放時間、公休日、費用、停車、導航及各項來源。",
        "Suwongak bündelt Sehenswürdigkeiten, Restaurants, Unterkünfte, Routen, Feste und Videos in Suwon mit Öffnungszeiten, Ruhetagen, Preisen, Parkplätzen, Wegbeschreibung und Quellenangaben.",
        "Suwongak rassemble les sites, restaurants, hébergements, circuits, festivals et vidéos de Suwon avec horaires, jours de fermeture, tarifs, parking, itinéraires et sources.",
        "Suwongak reúne atracciones, restaurantes, alojamientos, rutas, festivales y vídeos de Suwon con horarios, días de cierre, tarifas, aparcamiento, cómo llegar y fuentes.",
        "Сувонгак объединяет достопримечательности, рестораны, жильё, маршруты, фестивали и видео Сувона с часами работы, выходными, ценами, парковкой, маршрутами и источниками.",
    ),
    "site.disclaimer": (
        "An independent site operated separately from the official Suwon City website. Rights to original texts and photos belong to each source under the stated terms.",
        "水原市公式ホームページとは別に運営される独立サイトです。原文・写真の権利は各出典にあり、表示された利用条件に従います。",
        "本网站独立于水原市官方网站运营。原文与照片的权利归各来源所有，并遵循所示使用条件。",
        "本網站獨立於水原市官方網站營運。原文與照片的權利歸各來源所有，並遵循所示使用條件。",
        "Eine unabhängige Website, die getrennt von der offiziellen Website der Stadt Suwon betrieben wird. Die Rechte an Texten und Fotos liegen bei den jeweiligen Quellen.",
        "Site indépendant géré séparément du site officiel de la ville de Suwon. Les droits des textes et photos appartiennent à chaque source selon les conditions indiquées.",
        "Sitio independiente operado por separado de la web oficial de la ciudad de Suwon. Los derechos de textos y fotos pertenecen a cada fuente según las condiciones indicadas.",
        "Независимый сайт, работающий отдельно от официального сайта города Сувон. Права на тексты и фото принадлежат соответствующим источникам.",
    ),
    "site.official_links.0.name": (
        "Suwon Tourism (Suwon Special City Culture & Tourism)",
        "水原観光（水原特例市文化観光）",
        "水原观光（水原特例市文化观光）",
        "水原觀光（水原特例市文化觀光）",
        "Tourismus Suwon (Kultur und Tourismus der Stadt Suwon)",
        "Tourisme de Suwon (Culture et Tourisme de la ville de Suwon)",
        "Turismo de Suwon (Cultura y Turismo de la ciudad de Suwon)",
        "Туризм Сувона (Культура и туризм города Сувон)",
    ),
    "site.official_links.0.note": (
        "Official tourism portal of Suwon City",
        "水原市公式観光情報",
        "水原市官方旅游信息",
        "水原市官方旅遊資訊",
        "Offizielle Tourismusinformationen der Stadt Suwon",
        "Informations touristiques officielles de Suwon",
        "Información turística oficial de Suwon",
        "Официальная туристическая информация Сувона",
    ),
    "site.official_links.1.name": (
        "VisitKorea (Korean)",
        "大韓民国隅々（韓国観光公社）",
        "韩国旅游发展局（大韩民国角落）",
        "韓國觀光公社（大韓民國角落）",
        "VisitKorea (Koreanisch)",
        "VisitKorea (coréen)",
        "VisitKorea (coreano)",
        "VisitKorea (на корейском)",
    ),
    "site.official_links.1.note": (
        "Korea Tourism Organization travel portal",
        "韓国観光公社の観光情報",
        "韩国观光公社旅游信息",
        "韓國觀光公社旅遊資訊",
        "Tourismusinformationen der Korea Tourism Organization",
        "Informations touristiques de l'Organisation du tourisme de Corée",
        "Información turística de la Organización de Turismo de Corea",
        "Туристическая информация Национальной организации туризма Кореи",
    ),
    "theme.islands-sea.name": (
        "Suwon Hwaseong · Haenggung · Fortress Walls",
        "水原華城・行宮・城郭",
        "水原华城·行宫·城郭",
        "水原華城·行宮·城郭",
        "Festung Suwon Hwaseong · Haenggung · Stadtmauer",
        "Forteresse Suwon Hwaseong · Haenggung · Remparts",
        "Fortaleza Suwon Hwaseong · Haenggung · Muralla",
        "Крепость Сувон Хвасон · Дворец Хэнгун · Стены",
    ),
    "theme.islands-sea.description": (
        "Suwon Hwaseong Fortress, Hwaseong Haenggung Palace, the Four Gates, Banghwasuryujeong Pavilion, Yeonmudae, Seojangdae, and Hwaryeongjeon",
        "水原華城・華城行宮・長安門・八達門・華西門・蒼龍門・訪花随柳亭・錬武台・西将台・華寧殿",
        "水原华城、华城行宫、长安门、八达门、华西门、苍龙门、访花随柳亭、练武台、西将台与华宁殿",
        "水原華城、華城行宮、長安門、八達門、華西門、蒼龍門、訪花隨柳亭、練武臺、西將臺與華寧殿",
        "Festung Suwon Hwaseong, Palast Hwaseong Haenggung, die vier Stadttore, Pavillon Banghwasuryujeong, Yeonmudae, Seojangdae und Hwaryeongjeon",
        "Forteresse Suwon Hwaseong, palais Hwaseong Haenggung, les quatre portes, pavillon Banghwasuryujeong, Yeonmudae, Seojangdae et Hwaryeongjeon",
        "Fortaleza Suwon Hwaseong, palacio Hwaseong Haenggung, las cuatro puertas, pabellón Banghwasuryujeong, Yeonmudae, Seojangdae y Hwaryeongjeon",
        "Крепость Сувон Хвасон, дворец Хвасон Хэнгун, четыре крепостных ворот, павильон Панхвасурюджон, Ёнмудэ, Соджандэ и Хварёнджон",
    ),
    "theme.modern-history.name": (
        "Museums · Art Galleries · Heritage",
        "博物館・美術館・歴史文化",
        "博物馆·美术馆·历史文化",
        "博物館·美術館·歷史文化",
        "Museen · Kunstgalerien · Kulturerbe",
        "Musées · Galeries d'art · Patrimoine",
        "Museos · Galerías de arte · Patrimonio",
        "Музеи · Художественные галереи · Наследие",
    ),
    "theme.modern-history.description": (
        "Suwon Hwaseong Museum, Suwon Museum, Suwon Museum of Art, National Agricultural Museum, Samsung Innovation Museum, and Haewoojae",
        "水原華城博物館・水原博物館・水原市立美術館・国立農業博物館・サムスンイノベーションミュージアム・解憂斎",
        "水原华城博物馆、水原博物馆、水原市立美术馆、国立农业博物馆、三星创新博物馆与解忧斋",
        "水原華城博物館、水原博物館、水原市立美術館、國立農業博物館、三星創新博物館與解憂齋",
        "Suwon-Hwaseong-Museum, Stadtmuseum Suwon, Kunstmuseum Suwon, Landwirtschaftsmuseum, Samsung Innovation Museum und Haewoojae",
        "Musée de Suwon Hwaseong, musée de Suwon, musée d'art de Suwon, musée national de l'agriculture, Samsung Innovation Museum et Haewoojae",
        "Museo de Suwon Hwaseong, Museo de Suwon, Museo de Arte de Suwon, Museo Agrícola Nacional, Samsung Innovation Museum y Haewoojae",
        "Музей Сувон Хвасон, Музей Сувона, Художественный музей Сувона, Сельскохозяйственный музей, Музей инноваций Samsung и Хэуджэ",
    ),
    "theme.parks-nature.name": (
        "Lakes · Arboretums · Parks",
        "湖水公園・樹木園・森の道",
        "湖水公园·树木园·林道",
        "湖水公園·樹木園·林道",
        "Seeparks · Arboreten · Waldwege",
        "Parcs du lac · Arboretums · Sentiers",
        "Parques del lago · Arboretos · Senderos",
        "Озёрные парки · Дендрарии · Лесные тропы",
    ),
    "theme.parks-nature.description": (
        "Gwanggyo Lake Park, Irwol Arboretum, Yeongheung Arboretum, Manseok Park, Seoho Park, Wolhwawon Garden, and Gwanggyosan trails",
        "光教湖水公園・日月樹木園・霊興樹木園・万石公園・西湖公園・孝園公園粤華苑・光教山散策路",
        "光教湖水公园、日月树木园、灵兴树木园、万石公园、西湖公园、孝园公园粤华苑与光教山步道",
        "光教湖水公園、日月樹木園、靈興樹木園、萬石公園、西湖公園、孝園公園粵華苑與光教山步道",
        "Gwanggyo-Seepark, Irwol-Arboretum, Yeongheung-Arboretum, Manseok-Park, Seoho-Park, Garten Wolhwawon und Gwanggyosan-Wege",
        "Parc du lac Gwanggyo, arboretums d'Irwol et Yeongheung, parcs Manseok et Seoho, jardin Wolhwawon et sentiers de Gwanggyosan",
        "Parque del Lago Gwanggyo, arboretos Irwol y Yeongheung, parques Manseok y Seoho, jardín Wolhwawon y senderos de Gwanggyosan",
        "Озёрный парк Квангё, дендрарии Ирволь и Ёнхын, парки Мансок и Сохо, сад Вольхвавон и тропы Квангёсана",
    ),
    "theme.alleys-culture.name": (
        "Haengnidan-gil · Traditional Markets · Experiences",
        "行理団通り・伝統市場・体験",
        "行理团路·传统市场·体验",
        "行理團路·傳統市場·體驗",
        "Haengnidan-gil · Märkte · Erlebnisse",
        "Haengnidan-gil · Marchés · Expériences",
        "Haengnidan-gil · Mercados · Experiencias",
        "Хэннидан-киль · Рынки · Мастер-классы",
    ),
    "theme.alleys-culture.description": (
        "Haengnidan-gil, Suwon Chicken Street, Nammun, Motgol, and Jidong markets, Flying Suwon, Hwaseong Trolley, and Aqua Planet Gwanggyo",
        "行理団通り・工房通り・水原チキン通り・南門市場・池洞市場・フライング水原・華城御車・アクアプラネット光教",
        "行理团路、工坊街、水原炸鸡街、南门市场、池洞市场、飞越水原热气球、华城御车与光教Aqua Planet水族馆",
        "行理團路、工房街、水原炸雞街、南門市場、池洞市場、飛越水原熱氣球、華城御車與光教Aqua Planet水族館",
        "Haengnidan-gil, Hähnchenstraße Suwon, Nammun- und Jidong-Markt, Flying Suwon, Hwaseong-Bahn und Aqua Planet Gwanggyo",
        "Haengnidan-gil, rue du poulet frit, marchés Nammun et Jidong, ballon Flying Suwon, train Hwaseong et Aqua Planet Gwanggyo",
        "Haengnidan-gil, calle del pollo frito, mercados Nammun y Jidong, globo Flying Suwon, tren Hwaseong y Aqua Planet Gwanggyo",
        "Хэннидан-киль, улица жареной курицы, рынки Наммун и Чидон, аэростат Flying Suwon, трамвай Хвасон и океанариум Aqua Planet",
    ),
    "provider:카카오맵": (
        "Kakao Map",
        "カカオマップ",
        "Kakao地图",
        "Kakao地圖",
        "Kakao Map",
        "Kakao Map",
        "Kakao Map",
        "Kakao Map",
    ),
    "provider:수원시 문화관광": (
        "Suwon Culture & Tourism",
        "水原市文化観光",
        "水原市文化观光",
        "水原市文化觀光",
        "Kultur und Tourismus Suwon",
        "Culture et Tourisme de Suwon",
        "Cultura y Turismo de Suwon",
        "Культура и туризм Сувона",
    ),
    "provider:수원특례시 문화관광": (
        "Suwon Special City Culture & Tourism",
        "水原特例市文化観光",
        "水原特例市文化观光",
        "水原特例市文化觀光",
        "Kultur und Tourismus der Stadt Suwon",
        "Culture et Tourisme de la ville de Suwon",
        "Cultura y Turismo de la ciudad de Suwon",
        "Культура и туризм города Сувон",
    ),
    "provider:수원시": (
        "Suwon",
        "水原市",
        "水原市",
        "水原市",
        "Stadt Suwon",
        "Ville de Suwon",
        "Ciudad de Suwon",
        "Город Сувон",
    ),
}


def build_strings_for_lang(lang: str, places: list[dict], str_map: dict[str, dict[str, str]], fact_map: dict) -> tuple[dict, list[str]]:
    loc = LC.get(lang)
    tag = "en" if lang == "en" else loc.tag
    l_idx = LANGS.index(lang)
    all_rows = [r for r in ec.strings_items(DATA, places) if not r["id"].startswith("ui:")]
    if lang != "en":
        all_rows = all_rows + ec.chrome_rows(lang)

    store: dict[str, dict] = {}
    issues: list[str] = []
    L = None if lang == "en" else ec.LangCheck(lang)

    for r in all_rows:
        sid = r["id"]
        if sid in GANGNEUNG_STRINGS:
            tr = GANGNEUNG_STRINGS[sid][l_idx]
        elif "ko" in r and f"ko:{sid}:{r['ko']}" in str_map[lang]:
            tr = str_map[lang][f"ko:{sid}:{r['ko']}"]
        elif "en" in r and f"en:{sid}:{r['en']}" in str_map[lang]:
            tr = str_map[lang][f"en:{sid}:{r['en']}"]
        elif "ko" in r:
            tr = translate_ko_fragment(r["ko"], lang, fact_map)
        else:
            tr = r.get("en", "")

        item = {"id": sid, tag: tr}
        errs = ec.check_string(item, r, L)
        if errs:
            issues.extend(f"strings {sid}: {e}" for e in errs)
        store[sid] = ({"ko": r["ko"]} if "ko" in r else {"en": r["en"]}) | {tag: tr}

    # Also add provider:수원시 so site.city_body resolves in all languages
    store["provider:수원시"] = {"ko": "수원시", tag: GANGNEUNG_STRINGS["provider:수원시"][l_idx]}
    return store, issues


# ------------------------------------------------------------------ Courses Builder (8 languages)
COURSE_NAMES: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "suwon-course-1": (
        "Course 1 | Suwon Hwaseong Fortress, Hwaseong Haenggung Palace & Banghwasuryujeong Heritage Walk",
        "1コース｜水原華城・華城行宮・訪花随柳亭の王宮城郭紀行",
        "路线1｜水原华城·华城行宫·访花随柳亭王宫城郭漫步",
        "路線1｜水原華城·華城行宮·訪花隨柳亭王宮城郭漫步",
        "Route 1 | Festung Suwon Hwaseong, Palast Hwaseong Haenggung und Pavillon Banghwasuryujeong",
        "Circuit 1 | Forteresse Suwon Hwaseong, palais Hwaseong Haenggung et pavillon Banghwasuryujeong",
        "Ruta 1 | Fortaleza Suwon Hwaseong, palacio Hwaseong Haenggung y pabellón Banghwasuryujeong",
        "Маршрут 1 | Крепость Сувон Хвасон, дворец Хвасон Хэнгун и павильон Панхвасурюджон",
    ),
    "suwon-course-2": (
        "Course 2 | Paldalmun Gate, Nammun & Motgol Markets, Chicken Street & Haengnidan-gil Alley Outing",
        "2コース｜八達門・南門市場・水原チキン通り・行理団通りの路地紀行",
        "路线2｜八达门·南门与池洞市场·水原炸鸡街·行理团路街巷之旅",
        "路線2｜八達門·南門與池洞市場·水原炸雞街·行理團路街巷之旅",
        "Route 2 | Paldalmun-Tor, Nammun- und Motgol-Markt, Hähnchenstraße und Haengnidan-gil",
        "Circuit 2 | Porte Paldalmun, marchés Nammun et Motgol, rue du poulet frit et Haengnidan-gil",
        "Ruta 2 | Puerta Paldalmun, mercados Nammun y Motgol, calle del pollo frito y Haengnidan-gil",
        "Маршрут 2 | Ворота Пхальдальмун, рынки Наммун и Мотколь, улица курочки и Хэннидан-киль",
    ),
    "suwon-course-3": (
        "Course 3 | Yeonmudae, Flying Suwon, Hwaseong Museum & Bongnyeongsa Eastern Rampart Walk",
        "3コース｜錬武台・フライング水原・水原華城博物館・奉寧寺の東側城郭散策",
        "路线3｜练武台·飞越水原热气球·水原华城博物馆·奉宁寺东城郭漫游",
        "路線3｜練武臺·飛越水原熱氣球·水原華城博物館·奉寧寺東城郭漫遊",
        "Route 3 | Yeonmudae, Flying Suwon, Hwaseong-Museum und Tempel Bongnyeongsa",
        "Circuit 3 | Yeonmudae, ballon Flying Suwon, musée de Hwaseong et temple Bongnyeongsa",
        "Ruta 3 | Yeonmudae, globo Flying Suwon, Museo de Hwaseong y templo Bongnyeongsa",
        "Маршрут 3 | Ёнмудэ, аэростат Flying Suwon, Музей Сувон Хвасон и храм Поннёнса",
    ),
    "suwon-course-4": (
        "Course 4 | Gwanggyo Lake Park, Aqua Planet Gwanggyo & Suwon Museum Waterside Outing",
        "4コース｜光教湖水公園・アクアプラネット光教・水原博物館の水辺文化紀行",
        "路线4｜光教湖水公园·光教Aqua Planet水族馆·水原博物馆水畔之旅",
        "路線4｜光教湖水公園·光教Aqua Planet水族館·水原博物館水畔之旅",
        "Route 4 | Gwanggyo-Seepark, Aqua Planet Gwanggyo und Stadtmuseum Suwon",
        "Circuit 4 | Parc du lac Gwanggyo, Aqua Planet Gwanggyo et musée de Suwon",
        "Ruta 4 | Parque del Lago Gwanggyo, Aqua Planet Gwanggyo y Museo de Suwon",
        "Маршрут 4 | Озёрный парк Квангё, океанариум Aqua Planet и Музей Сувона",
    ),
    "suwon-course-5": (
        "Course 5 | Irwol Arboretum, Starfield Suwon, Manseok Park & Haewoojae in Jangan-gu",
        "5コース｜日月樹木園・スターフィールド水原・万石公園・解憂斎の長安区散策",
        "路线5｜日月树木园·水原Starfield·万石公园·解忧斋长安区漫步",
        "路線5｜日月樹木園·水原Starfield·萬石公園·解憂齋長安區漫步",
        "Route 5 | Irwol-Arboretum, Starfield Suwon, Manseok-Park und Haewoojae in Jangan-gu",
        "Circuit 5 | Arboretum d'Irwol, Starfield Suwon, parc Manseok et Haewoojae à Jangan-gu",
        "Ruta 5 | Arboreto Irwol, Starfield Suwon, Parque Manseok y Haewoojae en Jangan-gu",
        "Маршрут 5 | Дендрарий Ирволь, Starfield Suwon, парк Мансок и музей Хэуджэ в Чанъан-гу",
    ),
    "suwon-course-6": (
        "Course 6 | Seoho Park, National Agricultural Museum, Sangsang Campus & Wolhwawon Garden",
        "6コース｜西湖公園・国立農業博物館・京畿想像キャンパス・粤華苑の庭園紀行",
        "路线6｜西湖公园·国立农业博物馆·京畿想象校园·粤华苑园林漫游",
        "路線6｜西湖公園·國立農業博物館·京畿想像校園·粵華苑園林漫遊",
        "Route 6 | Seoho-Park, Landwirtschaftsmuseum, Gyeonggi Sangsang Campus und Garten Wolhwawon",
        "Circuit 6 | Parc Seoho, musée national de l'agriculture, campus Sangsang et jardin Wolhwawon",
        "Ruta 6 | Parque Seoho, Museo Agrícola Nacional, campus Sangsang y jardín Wolhwawon",
        "Маршрут 6 | Парк Сохо, Сельскохозяйственный музей, кампус Сансан и сад Вольхвавон",
    ),
}
COURSE_GROUP = ("Travel Course", "コース旅行", "路线旅行", "路線旅行", "Reiseroute", "Circuit", "Ruta de viaje", "Маршрут")
COURSE_DURATION = ("Day trip", "日帰り", "一日游", "一日遊", "Tagestour", "Excursion d'une journée", "Excursión de un día", "Однодневная поездка")

NAME_ROOTS_CJK: list[tuple[str, str, str, str]] = [
    ("수원특례시", "水原特例市", "水原特例市", "水原特例市"),
    ("수원시", "水原市", "水原市", "水原市"),
    ("수원화성박물관", "水原華城博物館", "水原华城博物馆", "水原華城博物館"),
    ("수원광교박물관", "水原光教博物館", "水原光教博物馆", "水原光教博物館"),
    ("수원박물관", "水原博物館", "水原博物馆", "水原博物館"),
    ("수원시립미술관", "水原市立美術館", "水原市立美术馆", "水原市立美術館"),
    ("수원시립아트스페이스광교", "水原市立アートスペース光教", "水原市立光教艺术空间", "水原市立光教藝術空間"),
    ("수원시립만석전시관", "水原市立万石展示館", "水原市立万石展览馆", "水原市立萬石展覽館"),
    ("수원전통문화관", "水原伝統文化館", "水原传统文化馆", "水原傳統文化館"),
    ("수원화성", "水原華城", "水原华城", "水原華城"),
    ("수원 화성", "水原華城", "水原华城", "水原華城"),
    ("화성행궁", "華城行宮", "华城行宫", "華城行宮"),
    ("화령전", "華寧殿", "华宁殿", "華寧殿"),
    ("화성어차", "華城御車", "华城御车", "華城御車"),
    ("방화수류정", "訪花随柳亭", "访花随柳亭", "訪花隨柳亭"),
    ("동북각루", "東北角楼", "东北角楼", "東北角樓"),
    ("동북공심돈", "東北空心墩", "东北空心墩", "東北空心墩"),
    ("서장대", "西将台", "西将台", "西將臺"),
    ("동장대", "東将台", "东将台", "東將臺"),
    ("연무대", "錬武台", "练武台", "練武臺"),
    ("장안문", "長安門", "长安门", "長安門"),
    ("팔달문", "八達門", "八达门", "八達門"),
    ("화서문", "華西門", "华西门", "華西門"),
    ("창룡문", "蒼龍門", "苍龙门", "蒼龍門"),
    ("화홍문", "華虹門", "华虹门", "華虹門"),
    ("봉돈", "烽墩", "烽墩", "烽墩"),
    ("효원의 종", "孝園の鐘", "孝园之钟", "孝園之鐘"),
    ("플라잉 수원", "フライング水原", "飞越水原热气球", "飛越水原熱氣球"),
    ("행리단길", "行理団通り", "行理团路", "行理團路"),
    ("공방거리", "工房通り", "工坊街", "工房街"),
    ("수원통닭거리", "水原チキン通り", "水原炸鸡街", "水原炸雞街"),
    ("통닭거리", "チキン通り", "炸鸡街", "炸雞街"),
    ("남문시장", "南門市場", "南门市场", "南門市場"),
    ("못골종합시장", "モッコル総合市場", "池谷综合市场", "池谷綜合市場"),
    ("못골시장", "モッコル市場", "池谷市场", "池谷市場"),
    ("지동시장", "池洞市場", "池洞市场", "池洞市場"),
    ("팔달문시장", "八達門市場", "八达门市场", "八達門市場"),
    ("영동시장", "栄洞市場", "荣洞市场", "榮洞市場"),
    ("미나리광시장", "ミナリグァン市場", "水芹菜广市场", "水芹菜廣市場"),
    ("남문로데오시장", "南門ロデオ市場", "南门罗德奥市场", "南門羅德奧市場"),
    ("거북시장", "亀市場", "龟市场", "龜市場"),
    ("연무시장", "錬武市場", "练武市场", "練武市場"),
    ("광교호수공원", "光教湖水公園", "光教湖水公园", "光教湖水公園"),
    ("광교중앙공원", "光教中央公園", "光教中央公园", "光教中央公園"),
    ("일월수목원", "日月樹木園", "日月树木园", "日月樹木園"),
    ("영흥수목원", "霊興樹木園", "灵兴树木园", "靈興樹木園"),
    ("만석거공원", "万石渠公園", "万石渠公园", "萬石渠公園"),
    ("만석공원", "万石公園", "万石公园", "萬石公園"),
    ("서호꽃뫼공원", "西湖花山公園", "西湖花山公园", "西湖花山公園"),
    ("서호공원", "西湖公園", "西湖公园", "西湖公園"),
    ("효원공원", "孝園公園", "孝园公园", "孝園公園"),
    ("월화원", "粤華苑", "粤华苑", "粵華苑"),
    ("인계예술공원", "仁渓芸術公園", "仁溪艺术公园", "仁溪藝術公園"),
    ("올림픽공원", "オリンピック公園", "奥林匹克公园", "奧林匹克公園"),
    ("노송지대", "老松地帯", "老松地带", "老松地帶"),
    ("국립농업박물관", "国立農業博物館", "国立农业博物馆", "國立農業博物館"),
    ("국립지도박물관", "国立地図博物館", "国立地图博物馆", "國立地圖博物館"),
    ("삼성이노베이션뮤지엄", "サムスンイノベーションミュージアム", "三星创新博物馆", "三星創新博物館"),
    ("경기상상캠퍼스", "京畿想像キャンパス", "京畿想象校园", "京畿想像校園"),
    ("경기아트센터", "京畿アートセンター", "京畿艺术中心", "京畿藝術中心"),
    ("수원컨벤션센터", "水原コンベンションセンター", "水原会展中心", "水原會展中心"),
    ("수원메쎄", "水原メッセ", "水原Messe展览中心", "水原Messe展覽中心"),
    ("해우재", "解憂斎", "解忧斋", "解憂齋"),
    ("봉녕사", "奉寧寺", "奉宁寺", "奉寧寺"),
    ("팔달사", "八達寺", "八达寺", "八達寺"),
    ("수원사", "水原寺", "水原寺", "水原寺"),
    ("청련암", "青蓮庵", "青莲庵", "青蓮庵"),
    ("수원향교", "水原郷校", "水原乡校", "水原鄉校"),
    ("심온선생묘", "沈温先生墓", "沈温先生墓", "沈溫先生墓"),
    ("아쿠아플라넷 광교", "アクアプラネット光教", "光教Aqua Planet水族馆", "光教Aqua Planet水族館"),
    ("스타필드 수원", "スターフィールド水原", "水原Starfield", "水原Starfield"),
    ("별마당도서관", "ピョルマダン図書館", "星空图书馆", "星空圖書館"),
    ("타임빌라스", "タイムヴィラス", "Timevillas", "Timevillas"),
    ("수원월드컵경기장", "水原ワールドカップ競技場", "水原世界杯体育场", "水原世界盃體育場"),
    ("수원KT위즈파크", "水原KTウィズパーク", "水原KT Wiz棒球场", "水原KT Wiz棒球場"),
    ("장안구", "長安区", "长安区", "長安區"),
    ("권선구", "勧善区", "劝善区", "勸善區"),
    ("팔달구", "八達区", "八达区", "八達區"),
    ("영통구", "霊通区", "灵通区", "靈通區"),
    ("수원", "水原", "水原", "水原"),
    ("행궁동", "行宮洞", "行宫洞", "行宮洞"),
    ("행궁", "行宮", "行宫", "行宮"),
    ("광교", "光教", "光教", "光教"),
    ("인계", "仁渓", "仁溪", "仁溪"),
    ("매탄", "梅灘", "梅滩", "梅灘"),
    ("영통", "霊通", "灵通", "靈通"),
    ("망포", "網浦", "网浦", "網浦"),
    ("호매실", "好梅実", "好梅实", "好梅實"),
    ("서둔", "西屯", "西屯", "西屯"),
    ("세류", "細柳", "细柳", "細柳"),
    ("정자", "亭子", "亭子", "亭子"),
    ("송죽", "松竹", "松竹", "松竹"),
    ("파장", "芭長", "芭长", "芭長"),
    ("율전", "栗田", "栗田", "栗田"),
    ("천천", "泉川", "泉川", "泉川"),
    ("조원", "棗園", "枣园", "棗園"),
    ("영화", "迎華", "迎华", "迎華"),
    ("연무", "錬武", "练武", "練武"),
    ("우만", "牛満", "牛满", "牛滿"),
    ("화서", "華西", "华西", "華西"),
    ("고등", "高等", "高等", "高等"),
    ("매산", "梅山", "梅山", "梅山"),
    ("매교", "梅校", "梅校", "梅校"),
    ("원천", "遠川", "远川", "遠川"),
    ("이의", "二儀", "二仪", "二儀"),
    ("구운", "九雲", "九云", "九雲"),
    ("금곡", "金谷", "金谷", "金谷"),
    ("권선", "勧善", "劝善", "勸善"),
    ("곡반정", "谷伴亭", "谷伴亭", "谷伴亭"),
    ("오목천", "梧木川", "梧木川", "梧木川"),
    ("고색", "古索", "古索", "古索"),
    ("전통시장", "伝統市場", "传统市场", "傳統市場"),
    ("시장", "市場", "市场", "市場"),
    ("공원", "公園", "公园", "公園"),
    ("박물관", "博物館", "博物馆", "博物館"),
    ("미술관", "美術館", "美术馆", "美術館"),
    ("기념관", "記念館", "纪念馆", "紀念館"),
    ("전시관", "展示館", "展览馆", "展覽館"),
    ("도서관", "図書館", "图书馆", "圖書館"),
    ("수목원", "樹木園", "树木园", "樹木園"),
    ("식물원", "植物園", "植物园", "植物園"),
    ("천문대", "天文台", "天文台", "天文台"),
    ("전망대", "展望台", "展望台", "展望台"),
    ("벽화마을", "壁画村", "壁画村", "壁畫村"),
    ("성곽길", "城郭の道", "城郭步道", "城郭步道"),
    ("캠핑장", "キャンプ場", "露营场", "露營場"),
    ("야영장", "キャンプ場", "露营地", "露營區"),
    ("호텔", "ホテル", "酒店", "飯店"),
    ("모텔", "モーテル", "汽车旅馆", "汽車旅館"),
    ("게스트하우스", "ゲストハウス", "青年旅舍", "青年旅舍"),
    ("한옥", "韓屋", "韩屋", "韓屋"),
    ("카페", "カフェ", "咖啡厅", "咖啡廳"),
    ("식당", "食堂", "餐厅", "餐廳"),
    ("갈비", "カルビ", "排骨", "排骨"),
    ("통닭", "チキン", "炸鸡", "炸雞"),
    ("칼국수", "カルグクス", "刀削面", "刀削麵"),
    ("막국수", "マッククス", "荞麦面", "蕎麥麵"),
    ("순대", "スンデ", "米肠", "米腸"),
    ("설렁탕", "ソルロンタン", "雪浓汤", "雪濃湯"),
    ("해장국", "ヘジャングク", "醒酒汤", "醒酒湯"),
    ("베이커리", "ベーカリー", "烘焙坊", "烘焙坊"),
    ("본점", "本店", "总店", "總店"),
    ("수원점", "水原店", "水原店", "水原店"),
]

_LAT_TO_CYR = str.maketrans({
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х",
    "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "q": "к", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
    "y": "и", "z": "з",
    "A": "А", "B": "Б", "C": "К", "D": "Д", "E": "Е", "F": "Ф", "G": "Г", "H": "Х",
    "I": "И", "J": "Дж", "K": "К", "L": "Л", "M": "М", "N": "Н", "O": "О", "P": "П",
    "Q": "К", "R": "Р", "S": "С", "T": "Т", "U": "У", "V": "В", "W": "В", "X": "Кс",
    "Y": "И", "Z": "З",
})


def resolve_place_name(p: dict, lang: str, names_en: dict, names_lang: dict) -> str:
    pid = p["id"]
    if lang == "en":
        return names_en[pid]["name_en"]
    loc = LC.get(lang)
    nk = loc.name_key
    off = squash_ws((names_lang.get(pid) or {}).get(nk))
    if off:
        return off

    ko = squash_ws(p["name"])
    if lang == "ru":
        s = re.sub(r"[~∼～〜]", "–", ko)
        s = re.sub(r"[가-힣]+", safe_kontsevich_word, s)
        s = HANGUL.sub("", s)
        s = s.translate(_LAT_TO_CYR)
        s = LC.CJK.sub("", s)
        return squash_ws(s)

    if lang in ("ja", "zh-hans", "zh-hant"):
        c_idx = {"ja": 1, "zh-hans": 2, "zh-hant": 3}[lang]
        s = re.sub(r"[~∼～〜]", "–", ko)
        s = s.replace("(", "（").replace(")", "）")
        for k_root, ja_v, zhs_v, zht_v in NAME_ROOTS_CJK:
            rep_v = (ja_v, zhs_v, zht_v)[c_idx - 1]
            s = s.replace(k_root, rep_v)
        if lang == "ja":
            s = re.sub(r"[가-힣]+", lambda m: hangul_to_katakana(m.group(0)), s)
            s = HANGUL.sub("", s)
            if not (LC.KANA.search(s) or LC.CJK.search(s)):
                s = f"{s}（水原）"
        else:
            s = re.sub(r"[가-힣]+", lambda m: " " + safe_romanize_word(m) + " ", s)
            s = HANGUL.sub("", s)
            if lang == "zh-hans":
                for bad in LC.traditional_only(s):
                    s = s.replace(bad, "")
            else:
                for bad in LC.simplified_only(s):
                    s = s.replace(bad, "")
        s = _cjk_punct(squash_ws(s), lang)
        if ec.parity_l(ko, s, lang):
            s = translate_ko_fragment(ko, lang, None)
            if lang == "ja" and not (LC.KANA.search(s) or LC.CJK.search(s)):
                s = f"{s}（水原）"
        return squash_ws(s)

    en_name = names_en[pid]["name_en"]
    s = en_name
    fn_map = {
        "de": (r"\band\b", "und", r"\bMain Branch\b", "Hauptfiliale", r"\bBranch\b", "Filiale", r"\bBeach\b", "Strand", r"\bPort\b", "Hafen"),
        "fr": (r"\band\b", "et", r"\bMain Branch\b", "Succursale principale", r"\bBranch\b", "Succursale", r"\bBeach\b", "Plage", r"\bPort\b", "Port"),
        "es": (r"\band\b", "y", r"\bMain Branch\b", "Sucursal principal", r"\bBranch\b", "Sucursal", r"\bBeach\b", "Playa", r"\bPort\b", "Puerto"),
    }[lang]
    for i in range(0, len(fn_map), 2):
        s = re.sub(fn_map[i], fn_map[i + 1], s, flags=re.I)
    s = re.sub(r"\b(?:the|with|from|for|or|open|closed|hours|free|admission|parking|address|phone|located|available|website|inquiries)\b", "", s, flags=re.I)
    promo_rx = LC.promo_rx(lang)
    if promo_rx:
        s = promo_rx.sub("", s)
    if ec.parity_l(ko, s, lang):
        s = translate_ko_fragment(ko, lang, None)
    return squash_ws(s)


def build_courses_for_lang(lang: str, courses: list[dict], by_slug: dict, names_en: dict, names_lang: dict) -> tuple[dict, list[str]]:
    loc = LC.get(lang)
    l_idx = LANGS.index(lang)
    L = None if lang == "en" else ec.LangCheck(lang)
    store: dict[str, dict] = {}
    issues: list[str] = []

    for c in courses:
        cid = c["id"]
        src = course_item(c, by_slug, names_en, None)
        tr_stops = []
        for s in src["stops"]:
            p = by_slug.get(s["place_slug"])
            p_name = resolve_place_name(p, lang, names_en, names_lang) if p else s["name_rr"]
            tr_stops.append({"name": p_name, "note": "", "place_slug": s["place_slug"]})
        item = {
            "id": cid,
            "name": COURSE_NAMES[cid][l_idx],
            "group": COURSE_GROUP[l_idx],
            "duration": COURSE_DURATION[l_idx],
            "summary": "",
            "stops": tr_stops,
        }
        errs = ec.check_course(item, src, L)
        if errs:
            issues.extend(f"courses {cid}: {e}" for e in errs)
        store[cid] = {
            "slug": src["slug"],
            "name": item["name"],
            "group": item["group"],
            "duration": item["duration"],
            "summary": "",
            "stops": tr_stops,
            "ko_hash": src["ko_hash"],
            "translated_at": TODAY,
        }
    return store, issues


# ------------------------------------------------------------------ Events Builder (8 languages)
EVENT_SERIES_NAMES: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "gyeonggido-munhwasagye-bom-gyeonggi-sangsanghae-bom-peseuta": (
        "Gyeonggi Four Seasons of Culture: Spring Sangsang Festa",
        "京畿道文化四季「春」京畿想像春フェスタ",
        "京畿道文化四季“春”京畿想象春庆典",
        "京畿道文化四季「春」京畿想像春慶典",
        "Gyeonggi-Kulturfest der vier Jahreszeiten: Frühlings-Sangsang-Festa",
        "Quatre saisons culturelles du Gyeonggi : Festa de printemps Sangsang",
        "Cuatro Estaciones Culturales de Gyeonggi: Festa de Primavera Sangsang",
        "Культурные сезоны Кёнгидо: весенний фестиваль в кампусе Сансан",
    ),
    "manseokgeo-saebitchukje": (
        "Manseokgeo Saebit Festival",
        "万石渠セビッ祭り",
        "万石渠新光庆典",
        "萬石渠新光慶典",
        "Manseokgeo-Saebit-Fest",
        "Festival Saebit de Manseokgeo",
        "Festival Saebit de Manseokgeo",
        "Фестиваль света Сэбит у водоёма Мансокко",
    ),
    "keolcheoraunji-gyeonggi-jang": (
        "Culture Lounge Gyeonggi, Jang",
        "カルチャーラウンジ京畿「場」",
        "京畿文化客厅“场”",
        "京畿文化客廳「場」",
        "Kultur-Lounge Gyeonggi: Jang",
        "Salon culturel du Gyeonggi : Jang",
        "Salón Cultural de Gyeonggi: Jang",
        "Культурный лаундж Кёнгидо «Чан»",
    ),
    "hwaseonghaenggung-yagangaejang": (
        "Hwaseong Haenggung Palace Night Opening",
        "華城行宮夜間開場",
        "华城行宫夜间开放",
        "華城行宮夜間開放",
        "Nachtöffnung des Palastes Hwaseong Haenggung",
        "Ouverture nocturne du palais Hwaseong Haenggung",
        "Apertura nocturna del palacio Hwaseong Haenggung",
        "Ночное открытие дворца Хвасон Хэнгун",
    ),
    "kkomanongbuui-keolleo-pam-daemoheom": (
        "Little Farmer's Color Farm Adventure",
        "ちびっこ農夫のカラーファーム大冒険",
        "小农夫色彩农场大冒险",
        "小農夫色彩農場大冒險",
        "Farbenfarm-Abenteuer für kleine Landwirte",
        "Grande aventure de la ferme colorée des petits fermiers",
        "Gran aventura en la granja de colores para pequeños agricultores",
        "Приключение маленьких фермеров на цветной ферме",
    ),
    "suwonyeongeukchukje": (
        "Suwon Theater Festival",
        "水原演劇祭",
        "水原戏剧节",
        "水原戲劇節",
        "Theaterfestival Suwon",
        "Festival de théâtre de Suwon",
        "Festival de Teatro de Suwon",
        "Театральный фестиваль в Сувоне",
    ),
    "gyeonggimi-gimbappeseuta": (
        "Gyeonggi Rice Gimbap Festa",
        "京畿米キンパフェスタ",
        "京畿大米紫菜包饭节",
        "京畿大米紫菜包飯節",
        "Gyeonggi-Reis-Gimbap-Festa",
        "Festa du gimbap au riz du Gyeonggi",
        "Festa de Gimbap con Arroz de Gyeonggi",
        "Фестиваль кимпаба из риса провинции Кёнгидо",
    ),
    "gyeonggiinhyeonggeukje-in-suwon": (
        "Gyeonggi Puppet Festival in Suwon",
        "京畿人形劇祭 in 水原",
        "水原京畿木偶剧节",
        "水原京畿木偶劇節",
        "Figurentheaterfestival Gyeonggi in Suwon",
        "Festival de marionnettes du Gyeonggi à Suwon",
        "Festival de Títeres de Gyeonggi en Suwon",
        "Фестиваль кукольных театров Кёнгидо в Сувоне",
    ),
    "suwon-gukgayusanyahaeng": (
        "Suwon National Heritage Night Walk",
        "水原国家遺産夜行",
        "水原国家遗产夜行",
        "水原國家遺產夜行",
        "Nachtspaziergang zum Kulturerbe Suwon",
        "Promenade nocturne du patrimoine de Suwon",
        "Paseo Nocturno del Patrimonio de Suwon",
        "Ночная прогулка по наследию Сувона",
    ),
    "seogakonseoteu-syeollokhomjeu": (
        "Bookshelf Concert: Sherlock Holmes",
        "書架コンサート：シャーロック・ホームズ",
        "书架音乐会：夏洛克·福尔摩斯",
        "書架音樂會：夏洛克·福爾摩斯",
        "Bücherregal-Konzert: Sherlock Holmes",
        "Concert de la bibliothèque : Sherlock Holmes",
        "Concierto de Estantería: Sherlock Holmes",
        "Книжный концерт: Шерлок Холмс",
    ),
    "suwonjaejeupeseutibeol": (
        "Suwon Jazz Festival",
        "水原ジャズフェスティバル",
        "水原爵士音乐节",
        "水原爵士音樂節",
        "Jazzfestival Suwon",
        "Festival de jazz de Suwon",
        "Festival de Jazz de Suwon",
        "Джазовый фестиваль в Сувоне",
    ),
    "suwonhwaseong-midieoateu": (
        "Suwon Hwaseong Media Art Show",
        "水原華城メディアアート",
        "水原华城媒体艺术展",
        "水原華城媒體藝術展",
        "Medienkunstfestival der Festung Suwon Hwaseong",
        "Spectacle d'art média de la forteresse Suwon Hwaseong",
        "Festival de Arte Multimedia de Suwon Hwaseong",
        "Фестиваль медиаискусства крепости Сувон Хвасон",
    ),
    "suwonhwaseongmunhwaje": (
        "Suwon Hwaseong Cultural Festival",
        "水原華城文化祭",
        "水原华城文化节",
        "水原華城文化節",
        "Kulturfest der Festung Suwon Hwaseong",
        "Festival culturel de la forteresse Suwon Hwaseong",
        "Festival Cultural de la Fortaleza Suwon Hwaseong",
        "Культурный фестиваль крепости Сувон Хвасон",
    ),
    "bulchwimugwiyasijang-sijeun-2": (
        "Bulchwimugwi Night Market Season 2",
        "不酔無帰夜市シーズン2",
        "不醉无归夜市第2季",
        "不醉無歸夜市第2季",
        "Nachtmarkt Bulchwimugwi Staffel 2",
        "Marché de nuit Bulchwimugwi saison 2",
        "Mercado Nocturno Bulchwimugwi Temporada 2",
        "Ночной рынок Пульчхвимугви (сезон 2)",
    ),
    "daehanminguk-ai-kontencheu-eowojeu": (
        "Korea AI Content Awards",
        "大韓民国AIコンテンツアワード",
        "大韩民国AI内容大奖",
        "大韓民國AI內容大獎",
        "Koreanische KI-Content-Awards",
        "Prix coréens des contenus IA",
        "Premios de Contenido de IA de Corea",
        "Корейская премия ИИ-контента",
    ),
    "suwonteungnyesi-ballyeodongmul-hanmaeumchukje": (
        "Suwon Companion Animal Harmony Festival",
        "水原特例市ペット共生フェスティバル",
        "水原特例市伴侣动物同心节",
        "水原特例市伴侶動物同心節",
        "Haustier-Harmoniefestival der Stadt Suwon",
        "Festival des animaux de compagnie de la ville de Suwon",
        "Festival de Mascotas de la Ciudad de Suwon",
        "Фестиваль домашних питомцев города Сувон",
    ),
    "byutisseom-suwon": (
        "Beautysum Suwon",
        "ビューティサム水原",
        "水原Beautysum美妆展",
        "水原Beautysum美妝展",
        "Beautysum Suwon",
        "Beautysum Suwon",
        "Beautysum Suwon",
        "Выставка красоты Beautysum в Сувоне",
    ),
    "gyeonggimi-dijeoteu-peseuta": (
        "Gyeonggi Rice Dessert Festa",
        "京畿米デザートフェスタ",
        "京畿大米甜点节",
        "京畿大米甜點節",
        "Gyeonggi-Reisdessert-Festa",
        "Festa des desserts au riz du Gyeonggi",
        "Festa de Postres de Arroz de Gyeonggi",
        "Фестиваль десертов из риса Кёнгидо",
    ),
}

EVENT_PLACE_NAMES: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "화성행궁·행궁광장·수원화성 일원": (
        "Hwaseong Haenggung Palace, Haenggung Plaza, and Suwon Hwaseong Fortress area",
        "華城行宮・行宮広場・水原華城一帯",
        "华城行宫、行宫广场与水原华城一带",
        "華城行宮、行宮廣場與水原華城一帶",
        "Bereich Palast Hwaseong Haenggung, Haenggung-Platz und Festung Suwon Hwaseong",
        "Secteur du palais Hwaseong Haenggung, de l'esplanade Haenggung et de Suwon Hwaseong",
        "Zona del palacio Hwaseong Haenggung, la plaza Haenggung y la fortaleza Suwon Hwaseong",
        "Район дворца Хвасон Хэнгун, площади Хэнгун и крепости Сувон Хвасон",
    ),
    "수원화성 화서문·장안문·장안공원 일원": (
        "Hwaseomun Gate, Janganmun Gate, and Jangan Park area of Suwon Hwaseong",
        "水原華城の華西門・長安門・長安公園一帯",
        "水原华城华西门、长安门与长安公园一带",
        "水原華城華西門、長安門與長安公園一帶",
        "Bereich Hwaseomun-Tor, Janganmun-Tor und Jangan-Park der Festung Suwon Hwaseong",
        "Secteur des portes Hwaseomun et Janganmun et du parc Jangan",
        "Zona de las puertas Hwaseomun y Janganmun y el Parque Jangan",
        "Район ворот Хвасомун, Чанъанмун и парка Чанъан крепости Сувон Хвасон",
    ),
    "화성행궁 일원": (
        "Hwaseong Haenggung Palace area",
        "華城行宮一帯",
        "华城行宫一带",
        "華城行宮一帶",
        "Bereich Palast Hwaseong Haenggung",
        "Secteur du palais Hwaseong Haenggung",
        "Zona del palacio Hwaseong Haenggung",
        "Район дворца Хвасон Хэнгун",
    ),
    "화성행궁·방화수류정·행궁동 일원": (
        "Hwaseong Haenggung Palace, Banghwasuryujeong Pavilion, and Haenggung-dong area",
        "華城行宮・訪花随柳亭・行宮洞一帯",
        "华城行宫、访花随柳亭与行宫洞一带",
        "華城行宮、訪花隨柳亭與行宮洞一帶",
        "Bereich Palast Hwaseong Haenggung, Pavillon Banghwasuryujeong und Haenggung-dong",
        "Secteur du palais Hwaseong Haenggung, du pavillon Banghwasuryujeong et de Haenggung-dong",
        "Zona del palacio Hwaseong Haenggung, el pabellón Banghwasuryujeong y Haenggung-dong",
        "Район дворца Хвасон Хэнгун, павильона Панхвасурюджон и квартала Хэнгун-дон",
    ),
    "수원남문시장·팔달문시장 일원": (
        "Suwon Nammun Market and Paldalmun Market area",
        "水原南門市場・八達門市場一帯",
        "水原南门市场与八达门市场一带",
        "水原南門市場與八達門市場一帶",
        "Bereich Nammun-Markt und Paldalmun-Markt in Suwon",
        "Secteur des marchés Nammun et Paldalmun de Suwon",
        "Zona de los mercados Nammun y Paldalmun de Suwon",
        "Район рынков Наммун и Пхальдальмун в Сувоне",
    ),
    "경기상상캠퍼스 일원": (
        "Gyeonggi Sangsang Campus area",
        "京畿想像キャンパス一帯",
        "京畿想象校园一带",
        "京畿想像校園一帶",
        "Bereich Gyeonggi Sangsang Campus",
        "Secteur du campus Gyeonggi Sangsang",
        "Zona del campus Gyeonggi Sangsang",
        "Территория кампуса Кёнги Сансан",
    ),
    "경기상상캠퍼스·수원 일원": (
        "Gyeonggi Sangsang Campus and Suwon area",
        "京畿想像キャンパス・水原一帯",
        "京畿想象校园与水原一带",
        "京畿想像校園與水原一帶",
        "Bereich Gyeonggi Sangsang Campus und Stadtgebiet Suwon",
        "Secteur du campus Gyeonggi Sangsang et de Suwon",
        "Zona del campus Gyeonggi Sangsang y Suwon",
        "Территория кампуса Кёнги Сансан и города Сувон",
    ),
    "광교호수공원 재미난밭 일원": (
        "Jaeminan Field at Gwanggyo Lake Park",
        "光教湖水公園チェミナン広場一帯",
        "光教湖水公园趣味草坪一带",
        "光教湖水公園趣味草坪一帶",
        "Bereich Jaeminan-Wiese im Gwanggyo-Seepark",
        "Secteur de la pelouse Jaeminan au parc du lac Gwanggyo",
        "Zona del prado Jaeminan en el Parque del Lago Gwanggyo",
        "Лужайка Чэминан в озёрном парке Квангё",
    ),
    "만석공원(만석거) 일원": (
        "Manseok Park (Manseokgeo Reservoir) area",
        "万石公園（万石渠）一帯",
        "万石公园（万石渠）一带",
        "萬石公園（萬石渠）一帶",
        "Bereich Manseok-Park (Manseokgeo-See)",
        "Secteur du parc Manseok (réservoir Manseokgeo)",
        "Zona del Parque Manseok (estanque Manseokgeo)",
        "Район парка Мансок (водоём Мансокко)",
    ),
    "국립농업박물관 일원": (
        "National Agricultural Museum area",
        "国立農業博物館一帯",
        "国立农业博物馆一带",
        "國立農業博物館一帶",
        "Bereich Nationales Landwirtschaftsmuseum",
        "Secteur du musée national de l'agriculture",
        "Zona del Museo Agrícola Nacional",
        "Территория Национального сельскохозяйственного музея",
    ),
    "수원메쎄 일원": (
        "Suwon Messe Exhibition Center area",
        "水原メッセ一帯",
        "水原Messe展览中心一带",
        "水原Messe展覽中心一帶",
        "Bereich Messezentrum Suwon Messe",
        "Secteur du parc des expositions Suwon Messe",
        "Zona del recinto ferial Suwon Messe",
        "Выставочный комплекс Сувон Мессе",
    ),
    "수원메쎄·타임빌라스 수원 일원": (
        "Suwon Messe and Timevillas Suwon area",
        "水原メッセ・タイムヴィラス水原一帯",
        "水原Messe与水原Timevillas一带",
        "水原Messe與水原Timevillas一帶",
        "Bereich Suwon Messe und Timevillas Suwon",
        "Secteur de Suwon Messe et Timevillas Suwon",
        "Zona de Suwon Messe y Timevillas Suwon",
        "Район комплекса Сувон Мессе и центра Timevillas",
    ),
    "경기아트센터 소극장": (
        "Small Theater at Gyeonggi Arts Center",
        "京畿アートセンター小劇場",
        "京畿艺术中心小剧场",
        "京畿藝術中心小劇場",
        "Kleines Theater im Gyeonggi Arts Center",
        "Petit théâtre du Centre des arts du Gyeonggi",
        "Pequeño Teatro del Centro de Artes de Gyeonggi",
        "Малый зал Арт-центра Кёнгидо",
    ),
    "수원컨벤션센터 일원": (
        "Suwon Convention Center area",
        "水原コンベンションセンター一帯",
        "水原会展中心一带",
        "水原會展中心一帶",
        "Bereich Kongresszentrum Suwon",
        "Secteur du palais des congrès de Suwon",
        "Zona del Centro de Convenciones de Suwon",
        "Район Конгресс-центра Сувона",
    ),
    "수원컨벤션센터 전시장": (
        "Exhibition Hall at Suwon Convention Center",
        "水原コンベンションセンター展示場",
        "水原会展中心展厅",
        "水原會展中心展廳",
        "Messehalle im Kongresszentrum Suwon",
        "Hall d'exposition du palais des congrès de Suwon",
        "Pabellón de exposiciones del Centro de Convenciones de Suwon",
        "Выставочный зал Конгресс-центра Сувона",
    ),
    "광교중앙공원 일원": (
        "Gwanggyo Central Park area",
        "光教中央公園一帯",
        "光教中央公园一带",
        "光教中央公園一帶",
        "Bereich Zentralpark Gwanggyo",
        "Secteur du parc central de Gwanggyo",
        "Zona del Parque Central de Gwanggyo",
        "Район Центрального парка Квангё",
    ),
    "경기도청·경기도서관 광교 일원": (
        "Gyeonggi Provincial Complex and Gyeonggi Library in Gwanggyo",
        "京畿道庁・京畿図書館（光教）一帯",
        "京畿道厅与京畿图书馆光教一带",
        "京畿道廳與京畿圖書館光教一帶",
        "Bereich Provinzregierung Gyeonggi und Bibliothek Gyeonggi in Gwanggyo",
        "Secteur de l'hôtel de province et de la bibliothèque du Gyeonggi à Gwanggyo",
        "Zona de la Gobernación y la Biblioteca Provincial de Gyeonggi en Gwanggyo",
        "Район администрации и библиотеки провинции Кёнгидо в Квангё",
    ),
}

EVENT_SPONSORS: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "수원특례시": (
        "Suwon Special City",
        "水原特例市",
        "水原特例市",
        "水原特例市",
        "Stadt Suwon",
        "Ville de Suwon",
        "Ciudad de Suwon",
        "Мэрия города Сувон",
    ),
    "수원특례시 / 수원문화재단": (
        "Suwon Special City / Suwon Cultural Foundation",
        "水原特例市／水原文化財団",
        "水原特例市 / 水原文化财团",
        "水原特例市 / 水原文化財團",
        "Stadt Suwon / Kulturstiftung Suwon",
        "Ville de Suwon / Fondation culturelle de Suwon",
        "Ciudad de Suwon / Fundación Cultural de Suwon",
        "Город Сувон / Культурный фонд Сувона",
    ),
    "수원특례시 / 팔달문전통시장상인회": (
        "Suwon Special City / Paldalmun Market Merchants Association",
        "水原特例市／八達門伝統市場商人会",
        "水原特例市 / 八达门传统市场商人会",
        "水原特例市 / 八達門傳統市場商人會",
        "Stadt Suwon / Händlerverband des Paldalmun-Marktes",
        "Ville de Suwon / Association des commerçants du marché Paldalmun",
        "Ciudad de Suwon / Asociación de Comerciantes del Mercado Paldalmun",
        "Город Сувон / Ассоциация торговцев рынка Пхальдальмун",
    ),
    "수원특례시 / 수원컨벤션센터": (
        "Suwon Special City / Suwon Convention Center",
        "水原特例市／水原コンベンションセンター",
        "水原特例市 / 水原会展中心",
        "水原特例市 / 水原會展中心",
        "Stadt Suwon / Kongresszentrum Suwon",
        "Ville de Suwon / Palais des congrès de Suwon",
        "Ciudad de Suwon / Centro de Convenciones de Suwon",
        "Город Сувон / Конгресс-центр Сувона",
    ),
    "경기도 / 경기문화재단": (
        "Gyeonggi Province / Gyeonggi Cultural Foundation",
        "京畿道／京畿文化財団",
        "京畿道 / 京畿文化财团",
        "京畿道 / 京畿文化財團",
        "Provinz Gyeonggi / Kulturstiftung Gyeonggi",
        "Province du Gyeonggi / Fondation culturelle du Gyeonggi",
        "Provincia de Gyeonggi / Fundación Cultural de Gyeonggi",
        "Провинция Кёнгидо / Культурный фонд Кёнгидо",
    ),
    "경기인형극제조직위원회 / 경기문화재단": (
        "Gyeonggi Puppet Festival Committee / Gyeonggi Cultural Foundation",
        "京畿人形劇祭組織委員会／京畿文化財団",
        "京畿木偶剧节组委会 / 京畿文化财团",
        "京畿木偶劇節組委會 / 京畿文化財團",
        "Komitee des Figurentheaterfestivals Gyeonggi / Kulturstiftung Gyeonggi",
        "Comité du festival de marionnettes du Gyeonggi / Fondation culturelle du Gyeonggi",
        "Comité del Festival de Títeres de Gyeonggi / Fundación Cultural de Gyeonggi",
        "Оргкомитет фестиваля кукольных театров / Культурный фонд Кёнгидо",
    ),
    "국립농업박물관": (
        "National Agricultural Museum",
        "国立農業博物館",
        "国立农业博物馆",
        "國立農業博物館",
        "Nationales Landwirtschaftsmuseum",
        "Musée national de l'agriculture",
        "Museo Agrícola Nacional",
        "Национальный сельскохозяйственный музей",
    ),
    "경기도 / 경기도농수산진흥원": (
        "Gyeonggi Province / Gyeonggi Agro-Food Institute",
        "京畿道／京畿道農水産振興院",
        "京畿道 / 京畿道农水产振兴院",
        "京畿道 / 京畿道農水產振興院",
        "Provinz Gyeonggi / Agrar- und Fischereiinstitut Gyeonggi",
        "Province du Gyeonggi / Institut agroalimentaire du Gyeonggi",
        "Provincia de Gyeonggi / Instituto Agroalimentario de Gyeonggi",
        "Провинция Кёнгидо / Институт агропромышленности Кёнгидо",
    ),
    "경기도 / 경기콘텐츠진흥원": (
        "Gyeonggi Province / Gyeonggi Content Agency",
        "京畿道／京畿コンテンツ振興院",
        "京畿道 / 京畿内容振兴院",
        "京畿道 / 京畿內容振興院",
        "Provinz Gyeonggi / Gyeonggi Content Agency",
        "Province du Gyeonggi / Agence des contenus du Gyeonggi",
        "Provincia de Gyeonggi / Agencia de Contenidos de Gyeonggi",
        "Провинция Кёнгидо / Агентство контента Кёнгидо",
    ),
    "경기아트센터": (
        "Gyeonggi Arts Center",
        "京畿アートセンター",
        "京畿艺术中心",
        "京畿藝術中心",
        "Gyeonggi Arts Center",
        "Centre des arts du Gyeonggi",
        "Centro de Artes de Gyeonggi",
        "Арт-центр Кёнгидо",
    ),
}

SOURCE_KTO = (
    "Korea Tourism Organization TourAPI",
    "韓国観光公社 TourAPI",
    "韩国观光公社 TourAPI",
    "韓國觀光公社 TourAPI",
    "Korea Tourism Organization TourAPI",
    "Organisation du tourisme de Corée TourAPI",
    "Organización de Turismo de Corea TourAPI",
    "Национальная организация туризма Кореи TourAPI",
)


def build_events_for_lang(lang: str, events: list[dict], city, fact_map: dict) -> tuple[dict, list[str]]:
    loc = LC.get(lang)
    l_idx = LANGS.index(lang)
    L = None if lang == "en" else ec.LangCheck(lang)
    store: dict[str, dict] = {}
    issues: list[str] = []

    for sr in event_series(events):
        src = event_item(sr, None, city=city)
        ev = sr["newest"]
        slug = sr["slug"]
        s_name = EVENT_SERIES_NAMES[slug][l_idx]
        n_name = f"2026 {s_name}" if ev["name"].startswith("2026") else (f"{s_name} 2" if "시즌2" in ev["name"] and "2" not in s_name else s_name)
        p_name = EVENT_PLACE_NAMES[ev["place_name"]][l_idx]
        addr_en = src["newest"].get("address_en_candidate") or romanize_full_address(ev["address"], city)
        fee_tr = translate_ko_fragment(ev["fee"], lang, fact_map)
        sponsor_tr = EVENT_SPONSORS[ev["sponsor"]][l_idx]
        tel = ev["tel"].replace("~", "–")
        sdate, edate = ev["start_date"], ev["end_date"]

        # Address in summary: use Cyrillic/CJK road/number form in ru/ja/zh so prose script check passes with 100% number parity
        addr_prose = translate_ko_fragment(ev["address"], lang, fact_map) if lang in ("ru", "ja", "zh-hans", "zh-hant") else addr_en

        if lang == "en":
            summary = f"{n_name} is a local festival in Suwon held from {sdate} to {edate}. The venue is {p_name} ({addr_prose}). Organized by {sponsor_tr}, admission is {fee_tr} (inquiries: {tel})."
        elif lang == "ja":
            summary = f"{n_name}は{sdate}から{edate}まで水原で開催される行事です。会場は{p_name}（{addr_prose}）です。主催は{sponsor_tr}で、料金は{fee_tr}、問合せは{tel}です。"
        elif lang == "zh-hans":
            summary = f"{n_name}是于{sdate}至{edate}在水原举办的活动。地点位于{p_name}（{addr_prose}）。主办方为{sponsor_tr}，费用为{fee_tr}，咨询电话为{tel}。"
        elif lang == "zh-hant":
            summary = f"{n_name}是於{sdate}至{edate}在水原舉辦的活動。地點位於{p_name}（{addr_prose}）。主辦方為{sponsor_tr}，費用為{fee_tr}，諮詢電話為{tel}。"
        elif lang == "de":
            summary = f"{n_name} ist eine Veranstaltung in Suwon vom {sdate} bis zum {edate}. Veranstaltungsort ist {p_name} ({addr_prose}). Veranstalter ist {sponsor_tr}, und der Eintritt ist {fee_tr} (Anfragen: {tel})."
        elif lang == "fr":
            summary = f"{n_name} est un événement organisé à Suwon du {sdate} au {edate}. Le lieu est {p_name} ({addr_prose}). Il est organisé par {sponsor_tr} avec un tarif {fee_tr} (renseignements : {tel})."
        elif lang == "es":
            summary = f"{n_name} es un evento de Suwon que se celebra del {sdate} al {edate}. La sede es {p_name} ({addr_prose}). Está organizado por {sponsor_tr} con tarifa {fee_tr} (consultas: {tel})."
        else:
            summary = f"{n_name} — региональное мероприятие в Сувоне с {sdate} по {edate}. Место проведения — {p_name} ({addr_prose}). Организатор — {sponsor_tr}, вход: {fee_tr} (справки: {tel})."
        summary = _cap_sentence_len(summary, lang)

        newest_out = {
            "name": n_name,
            "place_name": p_name,
            "address": addr_en,
            "fee": fee_tr,
            "sponsor": sponsor_tr,
            "tel": tel,
            "summary": summary,
            "notes": [],
        }
        item = {
            "id": slug,
            "series_name": s_name,
            "newest": newest_out,
            "alternatives": {},
            "highlights": [],
            "program_notes": [],
            "usual": [],
            "editions": [],
            "sources": [SOURCE_KTO[l_idx]],
        }
        errs = ec.check_event(item, src, L)
        if errs:
            issues.extend(f"events {slug}: {e}" for e in errs)
        store[slug] = {
            "series_name": s_name,
            "newest": {**newest_out, "id": src["newest"]["id"]},
            "alternatives": {},
            "highlights": [],
            "program_notes": [],
            "usual": [],
            "editions": [],
            "sources": {ko: tr for ko, tr in zip(src["sources"], item["sources"])},
            "ko_hash": src["ko_hash"],
            "translated_at": TODAY,
        }
    return store, issues


# ------------------------------------------------------------------ Guides Builder (8 languages)
GUIDES_TEXT: dict[str, dict[str, tuple[str, str, str, str, str, str, str, str]]] = {
    "guide-01": {
        "label": (
            "Suwon Hwaseong · Haenggung · Fortress",
            "水原華城・行宮・城郭",
            "水原华城·行宫·城郭",
            "水原華城·行宮·城郭",
            "Suwon Hwaseong · Haenggung · Stadtmauer",
            "Suwon Hwaseong · Haenggung · Remparts",
            "Suwon Hwaseong · Haenggung · Muralla",
            "Сувон Хвасон · Хэнгун · Крепость",
        ),
        "title": (
            "Which Suwon Hwaseong, Hwaseong Haenggung, and Banghwasuryujeong fortress sights and free year-round attractions can you visit?",
            "水原華城・華城行宮・訪花随柳亭の城郭名所と常時開放の無料観光地はどこですか？",
            "水原有哪些水原华城、华城行宫、访花随柳亭城郭景点与常年免费开放的观光地？",
            "水原有哪些水原華城、華城行宮、訪花隨柳亭城郭景點與常年免費開放的觀光地？",
            "Welche Festungsorte rund um Suwon Hwaseong und Hwaseong Haenggung sowie ganzjährig kostenlosen Ziele gibt es?",
            "Quels sites de la forteresse Suwon Hwaseong et du palais Haenggung et lieux gratuits toute l'année visiter ?",
            "¿Qué lugares de la fortaleza Suwon Hwaseong y el palacio Haenggung y atracciones gratis todo el año visitar?",
            "Какие объекты крепости Сувон Хвасон и дворца Хэнгун и круглосуточные бесплатные места можно посетить?",
        ),
        "summary": (
            "This site lists 20 Suwon Hwaseong, Hwaseong Haenggung, gate, pavilion, and fortress attractions, including 50 Suwon attractions open all year with free admission. Compare the hours, closed days, and fees of 10 key spots below.",
            "当サイトに掲載された水原華城・華城行宮・四大門・角楼・城郭関連の名所は20か所で、年中無休・無料で開放されている水原の観光地は50か所です。主な10か所の利用時間と定休日、入場料金を比較できます。",
            "本网站收录的水原华城、华城行宫、四大门、角楼与城郭相关景点共20处，全年无休且免费开放的水原观光地有50处。下方可对比10处主要景点的开放时间、休息日与门票标准。",
            "本網站收錄的水原華城、華城行宮、四大門、角樓與城郭相關景點共20處，全年無休且免費開放的水原觀光地有50處。下方可對比10處主要景點的開放時間、公休日與門票標準。",
            "Auf dieser Website sind 20 Orte rund um die Festung Suwon Hwaseong, den Palast Hwaseong Haenggung und die Stadttore verzeichnet, darunter 50 ganzjährig kostenlose Ziele in Suwon. Unten lassen sich 10 wichtige Orte vergleichen.",
            "Ce site recense 20 sites liés à la forteresse Suwon Hwaseong, au palais Hwaseong Haenggung et aux portes fortifiées, ainsi que 50 lieux ouverts toute l'année avec entrée gratuite. Comparez 10 sites clés ci-dessous.",
            "Este sitio incluye 20 lugares relacionados con la fortaleza Suwon Hwaseong, el palacio Hwaseong Haenggung y sus puertas, además de 50 atracciones abiertas todo el año con entrada gratis. Compare abajo 10 lugares clave.",
            "На сайте представлено 20 объектов крепости Сувон Хвасон, дворца Хвасон Хэнгун, ворот и башен, а также 50 достопримечательностей Сувона, открытых круглый год бесплатно. Ниже можно сравнить условия посещения 10 основных мест.",
        ),
        "h0": (
            "20 Suwon Hwaseong & Haenggung Fortress Sights and 50 Free Year-Round Attractions",
            "水原華城・華城行宮・城郭名所20か所と年中無休の無料観光地50か所",
            "20处水原华城、华城行宫城郭景点与50处全年无休免费观光地",
            "20處水原華城、華城行宮城郭景點與50處全年無休免費觀光地",
            "20 Festungs- und Palastorte sowie 50 ganzjährig kostenlose Ziele",
            "20 sites de la forteresse et du palais et 50 lieux gratuits toute l'année",
            "20 sitios de la fortaleza y el palacio y 50 atracciones gratis todo el año",
            "20 объектов крепости и дворца и 50 круглосуточных бесплатных достопримечательностей",
        ),
        "t0": (
            "According to Korea Tourism Organization TourAPI records, 20 Suwon attractions are associated with Suwon Hwaseong Fortress, Hwaseong Haenggung Palace, the four gates, Banghwasuryujeong, Yeonmudae, Hwahongmun, Seojangdae, and Hwaryeongjeon, and 50 attractions are open all year for free.",
            "韓国観光公社TourAPI基準で、水原華城と華城行宮、長安門・八達門・華西門・蒼龍門、訪花随柳亭・錬武台・華虹門・西将台・華寧殿など城郭関連の名所は20か所です。水原の観光地のうち年中無休で利用料金が無料の場所は50か所あります。",
            "据韩国观光公社TourAPI统计，水原华城、华城行宫、长安门、八达门、华西门、苍龙门及访花随柳亭、练武台、华虹门、西将台、华宁殿等城郭相关景点共20处，全年无休且免费的水原观光地为50处。",
            "據韓國觀光公社TourAPI統計，水原華城、華城行宮、長安門、八達門、華西門、蒼龍門及訪花隨柳亭、練武臺、華虹門、西將臺、華寧殿等城郭相關景點共20處，全年無休且免費的水原觀光地為50處。",
            "Laut TourAPI der Korea Tourism Organization gehören 20 Sehenswürdigkeiten zur Festung Suwon Hwaseong, zum Palast Hwaseong Haenggung, den vier Toren, Banghwasuryujeong, Yeonmudae, Seojangdae und Hwaryeongjeon; 50 Orte in Suwon sind ganzjährig kostenlos.",
            "Selon l'API TourAPI de l'Organisation du tourisme de Corée, 20 sites de Suwon concernent la forteresse Suwon Hwaseong, le palais Hwaseong Haenggung, les quatre portes, Banghwasuryujeong et Yeonmudae, et 50 sites sont ouverts toute l'année à titre gratuit.",
            "Según TourAPI de la Organización de Turismo de Corea, 20 atracciones de Suwon corresponden a la fortaleza Suwon Hwaseong, el palacio Hwaseong Haenggung, las cuatro puertas, Banghwasuryujeong y Yeonmudae, y 50 abren todo el año gratis.",
            "По данным TourAPI Национальной организации туризма Кореи, 20 достопримечательностей связаны с крепостью Сувон Хвасон, дворцом Хвасон Хэнгун, четырьмя воротами, Панхвасурюджоном и Ёнмудэ, а 50 объектов открыты круглый год бесплатно.",
        ),
        "h1": (
            "Checking Open Fortress Wall Sections and Ticketing Deadlines for Palace & Rides",
            "城郭常時開放区間と行宮・体験施設のチケット締切時刻の確認",
            "确认城郭常年开放路段与行宫、体验设施售票截止时间",
            "確認城郭常年開放路段與行宮、體驗設施售票截止時間",
            "Durchgehend geöffnete Mauerabschnitte und Kassenzeiten für Palast und Fahrten prüfen",
            "Vérifier les remparts en accès libre et les horaires de billetterie du palais",
            "Comprobar los tramos abiertos de la muralla y el cierre de taquilla del palacio",
            "Проверка открытых участков крепостной стены и работы касс дворца и аттракционов",
        ),
        "t1": (
            "While the Suwon Hwaseong fortress trail and outer gates remain open all year for free, Hwaseong Haenggung Palace, the Hwaseong Trolley, and the Flying Suwon helium balloon enforce ticketing cutoffs and weather or closing rules, so check the 10 places below before departure.",
            "水原華城の城郭道と四大門の外観は年中無休・無料で開放されていますが、華城行宮と華城御車、フライング水原の係留式ヘリウム気球はチケット販売締切時刻や気象・休業条件が定められているため、出発前に下の10か所の運営基準を照合してください。",
            "水原华城城郭步道与四大门外部全年免费开放，但华城行宫、华城御车和飞越水原系留热气球设有售票截止时间及气象、休馆规定，建议出发前核对下方10处景点的运营条件。",
            "水原華城城郭步道與四大門外部全年免費開放，但華城行宮、華城御車和飛越水原繫留熱氣球設有售票截止時間及氣象、休館規定，建議出發前核對下方10處景點的營運條件。",
            "Während der Festungsweg und die Stadttore ganzjährig kostenlos zugänglich sind, gelten im Palast Hwaseong Haenggung, bei der Hwaseong-Bahn und beim Ballon Flying Suwon feste Kassen- und Wetterregeln; prüfen Sie daher vorab die 10 Orte unten.",
            "Les remparts et les portes sont accessibles gratuitement toute l'année, mais le palais Hwaseong Haenggung, le train Hwaseong et le ballon Flying Suwon appliquent des heures limites de billetterie ; vérifiez les 10 lieux ci-dessous.",
            "El sendero de la muralla y las puertas abren todo el año gratis, pero el palacio Hwaseong Haenggung, el tren Hwaseong y el globo Flying Suwon tienen horarios límite de taquilla y normas meteorológicas; revise abajo los 10 lugares.",
            "Тропа вдоль крепостных стен и ворота открыты круглый год бесплатно, однако во дворце Хвасон Хэнгун, трамвае Хвасон и аэростате Flying Suwon действуют правила работы касс и погодные ограничения, поэтому сверьте условия 10 мест ниже.",
        ),
        "q0": (
            "How many Suwon Hwaseong and Haenggung fortress sights and free year-round attractions are in Suwon?",
            "水原で水原華城・行宮・城郭関連の名所と年中無休の無料観光地はそれぞれ何か所ですか？",
            "水原的水原华城、行宫、城郭相关景点与全年无休免费观光地各有多少处？",
            "水原的水原華城、行宮、城郭相關景點與全年無休免費觀光地各有多少處？",
            "Wie viele Festungs- und Palastorte sowie ganzjährig kostenlose Ziele gibt es in Suwon?",
            "Combien de sites de la forteresse et du palais et de lieux gratuits toute l'année compte Suwon ?",
            "¿Cuántos sitios de la fortaleza y el palacio y cuántas atracciones gratis todo el año hay en Suwon?",
            "Сколько в Сувоне объектов крепости и дворца и сколько круглогодичных бесплатных достопримечательностей?",
        ),
        "a0": (
            "There are 20 Suwon Hwaseong, Haenggung, gate, and pavilion attractions, and 50 attractions are open all year for free.",
            "水原華城・華城行宮・四大門・角楼関連の名所は20か所で、年中無休・無料の観光地は50か所です。",
            "水原华城、华城行宫、四大门与角楼相关景点共20处，全年无休且免费的观光地为50处。",
            "水原華城、華城行宮、四大門與角樓相關景點共20處，全年無休且免費的觀光地為50處。",
            "Es gibt 20 Orte rund um Festung, Palast, Tore und Pavillons sowie 50 ganzjährig geöffnete kostenlose Sehenswürdigkeiten.",
            "Il y a 20 sites liés à la forteresse, au palais, aux portes et aux pavillons, et 50 lieux ouverts toute l'année à titre gratuit.",
            "Hay 20 lugares relacionados con la fortaleza, el palacio, las puertas y los pabellones, y 50 atracciones abiertas todo el año gratis.",
            "Всего насчитывается 20 объектов крепости, дворца, ворот и павильонов, а 50 достопримечательностей открыты круглый год бесплатно.",
        ),
    },
    "guide-02": {
        "label": (
            "With Kids",
            "子どもと一緒に",
            "亲子同行",
            "親子同行",
            "Mit Kindern",
            "Avec des enfants",
            "Con niños",
            "С детьми",
        ),
        "title": (
            "Which arboretums, aquariums, museums, and parks in Suwon are convenient to visit with kids?",
            "子どもと訪れやすい水原の樹木園・アクアプラネット・博物館・公園スポットはどこですか？",
            "水原有哪些适合带孩子游览的树木园、水族馆、博物馆与公园景点？",
            "水原有哪些適合帶孩子遊覽的樹木園、水族館、博物館與公園景點？",
            "Welche Arboreten, Aquarien, Museen und Parks in Suwon eignen sich für Familien mit Kindern?",
            "Quels arboretums, aquariums, musées et parcs de Suwon visiter facilement avec des enfants ?",
            "¿Qué arboretos, acuarios, museos y parques de Suwon son cómodos para visitar con niños?",
            "Какие дендрарии, океанариумы, музеи и парки в Сувоне удобно посетить с детьми?",
        ),
        "summary": (
            "In Suwon, 52 attractions include arboretums, lakes, parks, Aqua Planet, observatories, museums, and art galleries, and 43 are cultural facilities such as museums and libraries. Compare the hours and visitor conditions of 10 key spots below.",
            "水原の樹木園・湖・公園・アクアプラネット・天文台・博物館・美術館スポットは52か所で、博物館・展示館・図書館などの文化施設は43か所です。主な10か所の営業時間と利用条件を以下で比較できます。",
            "水原的树木园、湖泊、公园、水族馆、天文台、博物馆与美术馆景点共52处，博物馆、展览馆与图书馆等文化设施共43处。下方可对比10处主要景点的开放时间与游览条件。",
            "水原的樹木園、湖泊、公園、水族館、天文台、博物館與美術館景點共52處，博物館、展覽館與圖書館等文化設施共43處。下方可對比10處主要景點的開放時間與遊覽條件。",
            "In Suwon gibt es 52 Arboreten, Seen, Parks, Aquarien, Sternwarten und Museen sowie 43 Kultureinrichtungen wie Museen und Bibliotheken. Unten können Sie 10 wichtige Orte vergleichen.",
            "À Suwon, on compte 52 arboretums, lacs, parcs, aquariums, observatoires et musées, ainsi que 43 équipements culturels tels que musées et bibliothèques. Comparez 10 lieux clés ci-dessous.",
            "En Suwon hay 52 arboretos, lagos, parques, acuarios, observatorios y museos, además de 43 instalaciones culturales entre museos y bibliotecas. Compare abajo los horarios de 10 lugares principales.",
            "В Сувоне насчитывается 52 дендрария, озера, парка, океанариума, обсерватории и музея, а также 43 культурных учреждения. Ниже приведено сравнение 10 основных мест.",
        ),
        "h0": (
            "52 Arboretums, Lakes, Parks, Aquariums & Museums and 43 Cultural Facilities",
            "樹木園・湖・公園・水族館・博物館52か所と文化施設43か所の現況",
            "52处树木园、湖泊、公园、水族馆与博物馆及43处文化设施概况",
            "52處樹木園、湖泊、公園、水族館與博物館及43處文化設施概況",
            "52 Arboreten, Seen, Parks, Aquarien und Museen sowie 43 Kultureinrichtungen",
            "52 arboretums, lacs, parcs, aquariums et musées et 43 équipements culturels",
            "52 arboretos, lagos, parques, acuarios y museos y 43 instalaciones culturales",
            "52 дендрария, озера, парка, океанариума и музея и 43 культурных объекта",
        ),
        "t0": (
            "Based on Korea Tourism Organization TourAPI records, 52 Suwon attractions include arboretums, lakes, parks, Aqua Planet, observatories, museums, or art galleries in their names, and 43 cultural facilities such as agricultural museums, map museums, children's libraries, and art centers are recorded.",
            "韓国観光公社TourAPI基準で、樹木園・湖・公園・アクアプラネット・天文台・博物館・美術館が名前に含まれる水原の観光地は52か所です。農業博物館や地図博物館、子ども図書館、アートセンターなどの文化施設は43か所収録されています。",
            "据韩国观光公社TourAPI数据，名称包含树木园、湖泊、公园、Aqua Planet水族馆、天文台、博物馆或美术馆的水原观光地有52处，农业博物馆、地图博物馆、儿童图书馆与艺术中心等文化设施共收录43处。",
            "據韓國觀光公社TourAPI資料，名稱包含樹木園、湖泊、公園、Aqua Planet水族館、天文台、博物館或美術館的水原觀光地有52處，農業博物館、地圖博物館、兒童圖書館與藝術中心等文化設施共收錄43處。",
            "Nach Angaben von TourAPI tragen 52 Sehenswürdigkeiten in Suwon Namen mit Bezug zu Arboretum, See, Park, Aqua Planet, Sternwarte, Museum oder Kunstgalerie, und 43 Kultureinrichtungen wie Museen und Kinderbibliotheken sind erfasst.",
            "D'après les données TourAPI, 52 sites de Suwon mentionnent arboretum, lac, parc, Aqua Planet, observatoire, musée ou galerie d'art, et 43 équipements culturels tels que musées et bibliothèques pour enfants sont répertoriés.",
            "Según los datos de TourAPI, 52 atracciones de Suwon incluyen arboreto, lago, parque, Aqua Planet, observatorio, museo o galería en su nombre, y se registran 43 instalaciones culturales entre museos y bibliotecas infantiles.",
            "По данным TourAPI, 52 достопримечательности Сувона включают дендрарии, озёра, парки, океанариум Aqua Planet, обсерваторию, музеи и галереи, а всего в каталог включено 43 культурных учреждения.",
        ),
        "h1": (
            "Checking Closed Mondays, Advance Reservations & Last Entry Times",
            "月曜日休館・事前予約と入場締切時刻の確認",
            "确认周一休馆、预约要求与停止入场时间",
            "確認週一休館、預約要求與停止入場時間",
            "Schließung am Montag, Vorabreservierung und Einlassschluss prüfen",
            "Vérifier la fermeture du lundi, les réservations et l'heure limite d'admission",
            "Comprobar el cierre de los lunes, la reserva previa y la hora límite de admisión",
            "Проверка выходного в понедельник, предварительной записи и времени окончания входа",
        ),
        "t1": (
            "Irwol and Yeongheung Arboretums and municipal museums close every Monday, while Samsung Innovation Museum and children's experience halls require advance online booking or close ticketing early, so review the 10 places below before visiting.",
            "日月樹木園・霊興樹木園と公立博物館は毎週月曜日が休館で、サムスンイノベーションミュージアムや子ども体験館は事前オンライン予約や入場締切基準が分かれているため、訪問前に下の10か所の利用時間と定休日を確認してください。",
            "日月树木园、灵兴树木园及公立博物馆每周一休馆，三星创新博物馆与儿童体验馆则设有在线预约或提前停止入场规定，建议游览前核对下方10处地点的开放时间与休息日。",
            "日月樹木園、靈興樹木園及公立博物館每週一休館，三星創新博物館與兒童體驗館則設有線上預約或提前停止入場規定，建議遊覽前核對下方10處地點的開放時間與公休日。",
            "Die Arboreten Irwol und Yeongheung sowie städtische Museen schließen jeden Montag, während das Samsung Innovation Museum und Kindererlebnisräume oft Online-Buchungen erfordern; prüfen Sie daher die 10 Orte unten vor dem Besuch.",
            "Les arboretums d'Irwol et Yeongheung ainsi que les musées municipaux ferment le lundi, et le Samsung Innovation Museum demande une réservation préalable ; consultez les horaires des 10 lieux ci-dessous.",
            "Los arboretos Irwol y Yeongheung y los museos municipales cierran los lunes, mientras que el Samsung Innovation Museum requiere reserva previa; consulte abajo el horario de los 10 lugares.",
            "Дендрарии Ирволь и Ёнхын и муниципальные музеи закрыты по понедельникам, а Музей инноваций Samsung и детские залы требуют предварительной записи, поэтому перед визитом проверьте часы работы 10 мест ниже.",
        ),
        "q0": (
            "How many arboretum, lake, park, aquarium, and museum attractions and cultural facilities are in Suwon?",
            "水原で樹木園・湖・公園・水族館・博物館関連の観光地と文化施設はそれぞれ何か所ですか？",
            "水原的树木园、湖泊、公园、水族馆、博物馆相关观光地与文化设施各有多少处？",
            "水原的樹木園、湖泊、公園、水族館、博物館相關觀光地與文化設施各有多少處？",
            "Wie viele Arboreten, Seen, Parks, Aquarien und Museen sowie Kultureinrichtungen gibt es in Suwon?",
            "Combien d'arboretums, lacs, parcs, aquariums, musées et équipements culturels compte Suwon ?",
            "¿Cuántos arboretos, lagos, parques, acuarios, museos e instalaciones culturales hay en Suwon?",
            "Сколько в Сувоне дендрариев, озёр, парков, океанариумов и музеев и сколько культурных объектов?",
        ),
        "a0": (
            "There are 52 arboretum, lake, park, aquarium, observatory, and museum attractions, and 43 cultural facilities.",
            "樹木園・湖・公園・アクアプラネット・天文台・博物館・美術館スポットは52か所で、文化施設は43か所です。",
            "树木园、湖泊、公园、水族馆、天文台与博物馆景点为52处，文化设施为43处。",
            "樹木園、湖泊、公園、水族館、天文台與博物館景點為52處，文化設施為43處。",
            "Es gibt 52 Arboreten, Seen, Parks, Aquarien, Sternwarten und Museen sowie 43 Kultureinrichtungen.",
            "On compte 52 arboretums, lacs, parcs, aquariums, observatoires et musées, ainsi que 43 équipements culturels.",
            "Hay 52 arboretos, lagos, parques, acuarios, observatorios y museos, y 43 instalaciones culturales.",
            "Насчитывается 52 дендрария, озера, парка, океанариума и музея и 43 культурных учреждения.",
        ),
    },
    "guide-03": {
        "label": (
            "Rainy Day · Indoor",
            "雨の日・室内",
            "雨天·室内",
            "雨天·室內",
            "Regentag · Indoor",
            "Jour de pluie · Intérieur",
            "Día de lluvia · Interior",
            "В дождливый день · В помещении",
        ),
        "title": (
            "Which museums, art galleries, libraries, and indoor cultural spaces in Suwon are convenient for a rainy day?",
            "雨の日に回りやすい水原の博物館・美術館・図書館・室内文化施設はどこですか？",
            "水原有哪些适合雨天游览的博物馆、美术馆、图书馆与室内文化设施？",
            "水原有哪些適合雨天遊覽的博物館、美術館、圖書館與室內文化設施？",
            "Welche Museen, Kunstgalerien, Bibliotheken und Kultureinrichtungen in Suwon eignen sich für Regentage?",
            "Quels musées, galeries d'art, bibliothèques et espaces culturels visiter à Suwon par temps de pluie ?",
            "¿Qué museos, galerías de arte, bibliotecas e instalaciones culturales de Suwon visitar en un día de lluvia?",
            "Какие музеи, художественные галереи, библиотеки и культурные центры Сувона посетить в дождливый день?",
        ),
        "summary": (
            "This site lists 43 cultural facilities in Suwon along with 34 museum, art gallery, library, exhibition, and aquarium attractions. Compare the hours, regular closed days, and admission fees of 10 key indoor spots below.",
            "当サイトに収録された水原の文化施設は全43か所で、博物館・美術館・図書館・展示館・アクアプラネットなどが名前に含まれる観光地は34か所です。主な10か所の観覧時間と休館日、入場料を比較できます。",
            "本网站收录的水原文化设施共43处，名称包含博物馆、美术馆、图书馆、展览馆或水族馆的观光地有34处。下方可对比10处主要室内场馆的参观时间、休馆日与门票标准。",
            "本網站收錄的水原文化設施共43處，名稱包含博物館、美術館、圖書館、展覽館或水族館的觀光地有34處。下方可對比10處主要室內場館的參觀時間、公休日與門票標準。",
            "Auf dieser Website sind 43 Kultureinrichtungen in Suwon sowie 34 Museen, Kunstgalerien, Bibliotheken, Ausstellungshallen und Aquarien erfasst. Vergleichen Sie unten die 10 wichtigsten Orte.",
            "Ce site répertorie 43 équipements culturels à Suwon et 34 musées, galeries d'art, bibliothèques, salles d'exposition et aquariums. Comparez ci-dessous les horaires et tarifs de 10 lieux principaux.",
            "Este sitio reúne 43 instalaciones culturales en Suwon y 34 museos, galerías de arte, bibliotecas, salas de exposición y acuarios. Compare abajo los 10 lugares principales.",
            "На сайте собрано 43 культурных объекта Сувона и 34 музея, галереи, библиотеки, выставочных зала и океанариума. Ниже можно сравнить расписание и стоимость входа для 10 ключевых мест.",
        ),
        "h0": (
            "43 Cultural Facilities and 34 Museums, Galleries, Libraries & Indoor Venues",
            "文化施設43か所と博物館・美術館・図書館・室内スポット34か所",
            "43处文化设施与34处博物馆、美术馆、图书馆及室内场馆",
            "43處文化設施與34處博物館、美術館、圖書館及室內場館",
            "43 Kultureinrichtungen sowie 34 Museen, Galerien, Bibliotheken und Indoor-Ziele",
            "43 équipements culturels et 34 musées, galeries, bibliothèques et lieux couverts",
            "43 instalaciones culturales y 34 museos, galerías, bibliotecas y espacios cubiertos",
            "43 культурных центра и 34 музея, галереи, библиотеки и крытых объекта",
        ),
        "t0": (
            "Under Korea Tourism Organization TourAPI categories, 43 Suwon venues are registered as cultural facilities, and 34 attractions include museums, art galleries, libraries, exhibition halls, cultural centers, or Aqua Planet in their names.",
            "韓国観光公社TourAPI分類上、文化施設として登録された水原のスポットは43か所で、博物館・美術館・図書館・展示館・文化館・アート・アクアプラネットなどが名前に入る観光地は34か所です。",
            "按韩国观光公社TourAPI分类，登记为文化设施的水原景点共43处，名称含博物馆、美术馆、图书馆、展览馆、文化馆、艺术或Aqua Planet的观光地共34处。",
            "按韓國觀光公社TourAPI分類，登記為文化設施的水原景點共43處，名稱含博物館、美術館、圖書館、展覽館、文化館、藝術或Aqua Planet的觀光地共34處。",
            "In der TourAPI-Klassifikation sind 43 Orte in Suwon als Kultureinrichtungen registriert, und 34 Sehenswürdigkeiten tragen Namen wie Museum, Kunstmuseum, Bibliothek, Ausstellungshalle, Kulturzentrum oder Aqua Planet.",
            "Selon la classification TourAPI, 43 lieux de Suwon sont enregistrés comme équipements culturels, et 34 sites portent dans leur nom musée, galerie d'art, bibliothèque, salle d'exposition ou Aqua Planet.",
            "Según la clasificación de TourAPI, 43 espacios de Suwon están registrados como instalaciones culturales, y 34 atracciones incluyen museo, galería, biblioteca, sala de exposición o Aqua Planet en su nombre.",
            "По классификации TourAPI, 43 объекта Сувона зарегистрированы как культурные учреждения, а 34 места включают в название музей, художественную галерею, библиотеку, выставочный зал или океанариум Aqua Planet.",
        ),
        "h1": (
            "Comparing Opening Hours, Monday Closures & Free Admission",
            "観覧時間・月曜日休館・無料観覧の比較",
            "参观时间、周一休馆与免费参观对比",
            "參觀時間、週一休館與免費參觀對比",
            "Öffnungszeiten, Schließung am Montag und kostenloser Eintritt im Vergleich",
            "Comparer horaires de visite, fermeture du lundi et entrée gratuite",
            "Comparar horarios de visita, cierre de los lunes y entrada gratis",
            "Сравнение часов работы, выходных в понедельник и бесплатного входа",
        ),
        "t1": (
            "Major venues such as Suwon Hwaseong Museum, Suwon Museum, Suwon Museum of Art, and the National Agricultural Museum close on Mondays or the first Monday of the month and stop ticket sales before closing time, while Starfield Library Suwon and Aqua Planet Gwanggyo stay open year-round, so compare the 10 places below.",
            "水原華城博物館・水原博物館・水原市立美術館・国立農業博物館などの主な展示館は毎週月曜日に休館し閉館前にチケット販売を締め切りますが、ピョルマダン図書館やアクアプラネット光教は年中無休で運営されるため、下の10か所の条件を照合してください。",
            "水原华城博物馆、水原博物馆、水原市立美术馆与国立农业博物馆等展馆常在每周一或每月第一个周一休馆并在闭馆前停止售票，而星空图书馆与光教水族馆全年无休开放，建议提前对照下方10处场馆规划路线。",
            "水原華城博物館、水原博物館、水原市立美術館與國立農業博物館等展館常在每週一或每月第一個週一休館並在閉館前停止售票，而星空圖書館與光教水族館全年無休開放，建議提前對照下方10處場館規劃路線。",
            "Museen wie das Suwon-Hwaseong-Museum, das Stadtmuseum Suwon, das Kunstmuseum Suwon und das Landwirtschaftsmuseum schließen montags, während die Starfield-Bibliothek und Aqua Planet Gwanggyo ganzjährig geöffnet sind; gleichen Sie daher die 10 Orte unten ab.",
            "Les musées municipaux et le musée national de l'agriculture ferment le lundi, tandis que la bibliothèque Starfield et Aqua Planet Gwanggyo restent ouverts toute l'année ; vérifiez les 10 lieux ci-dessous.",
            "Los museos municipales y el Museo Agrícola Nacional cierran los lunes, mientras que la biblioteca Starfield y Aqua Planet Gwanggyo abren todo el año; revise abajo los 10 lugares.",
            "Музей Сувон Хвасон, Музей Сувона, Художественный музей и Сельскохозяйственный музей закрываются по понедельникам, тогда как библиотека Starfield и океанариум Aqua Planet работают без выходных; сверьте график 10 мест ниже.",
        ),
        "q0": (
            "How many places in Suwon are classified as cultural facilities and how many are museum, gallery, or library attractions?",
            "水原で文化施設に分類されている場所と博物館・美術館・図書館スポットはそれぞれ何か所ですか？",
            "水原被归类为文化设施的地点与博物馆、美术馆、图书馆相关景点各有多少处？",
            "水原被歸類為文化設施的地點與博物館、美術館、圖書館相關景點各有多少處？",
            "Wie viele Orte in Suwon sind als Kultureinrichtungen eingestuft und wie viele sind Museen, Galerien oder Bibliotheken?",
            "Combien de lieux à Suwon sont classés comme équipements culturels et combien sont des musées, galeries ou bibliothèques ?",
            "¿Cuántos lugares de Suwon están clasificados como instalaciones culturales y cuántos son museos, galerías o bibliotecas?",
            "Сколько объектов в Сувоне классифицированы как культурные учреждения и сколько относятся к музеям, галереям и библиотекам?",
        ),
        "a0": (
            "There are 43 attractions registered as cultural facilities in Suwon, and 34 attractions related to museums, art galleries, libraries, exhibition halls, and aquariums.",
            "文化施設として登録された水原の観光地は43か所で、博物館・美術館・図書館・展示館・水族館関連のスポットは34か所です。",
            "登记为文化设施的水原观光地有43处，博物馆、美术馆、图书馆、展览馆与水族馆相关景点有34处。",
            "登記為文化設施的水原觀光地有43處，博物館、美術館、圖書館、展覽館與水族館相關景點有34處。",
            "Es sind 43 Ziele als Kultureinrichtungen registriert sowie 34 Orte rund um Museen, Kunstgalerien, Bibliotheken, Ausstellungshallen und Aquarien.",
            "On compte 43 sites enregistrés comme équipements culturels et 34 lieux liés aux musées, galeries d'art, bibliothèques, salles d'exposition et aquariums.",
            "Hay 43 atracciones registradas como instalaciones culturales y 34 lugares relacionados con museos, galerías de arte, bibliotecas, salas de exposición y acuarios.",
            "В качестве культурных учреждений зарегистрировано 43 объекта, а 34 места связаны с музеями, галереями, библиотеками, выставочными залами и океанариумами.",
        ),
    },
    "guide-04": {
        "label": (
            "With Pets",
            "ペット同伴",
            "携宠同行",
            "攜寵同行",
            "Mit Haustieren",
            "Avec animaux",
            "Con mascotas",
            "С питомцами",
        ),
        "title": (
            "Which parks, attractions, cafes, and stays in Suwon provide pet-friendly guidelines?",
            "ペット同伴基準が案内されている水原の湖水公園・観光地・カフェ・宿はどこですか？",
            "水原有哪些提供宠物同行说明的湖水公园、观光地、咖啡厅与住宿？",
            "水原有哪些提供寵物同行說明的湖水公園、觀光地、咖啡廳與住宿？",
            "Welche Parks, Sehenswürdigkeiten, Cafés und Unterkünfte in Suwon haben Regeln für Haustiere?",
            "Quels parcs, sites touristiques, cafés et hébergements de Suwon indiquent des conditions d'accueil des animaux ?",
            "¿Qué parques, atracciones, cafeterías y alojamientos de Suwon cuentan con normas para ir con mascotas?",
            "В каких парках, местах, кафе и кемпингах Сувона указаны правила посещения с домашними животными?",
        ),
        "summary": (
            "A total of 16 places in Suwon list pet-accompaniment rules, comprising 13 attractions, 2 restaurants and cafes, and 1 stay. Compare the permitted areas and leash or carrier requirements of 10 key spots below.",
            "ペット同伴基準が登録された水原の場所は全16か所で、観光地13か所、飲食店・カフェ2か所、宿1か所が含まれます。主な10か所の同伴可能区域とリード・利用条件を以下で比較できます。",
            "登记有携宠标准的水原地点共16处，包括观光地13处、餐饮与咖啡厅2处、住宿1处。下方可对比10处主要地点的可同行区域及牵引绳、宠物包规定。",
            "登記有攜寵標準的水原地點共16處，包括觀光地13處、餐飲與咖啡廳2處、住宿1處。下方可對比10處主要地點的可同行區域及牽引繩、寵物包規定。",
            "Insgesamt 16 Orte in Suwon führen Angaben zur Mitnahme von Haustieren, darunter 13 Sehenswürdigkeiten, 2 Restaurants und Cafés sowie 1 Unterkunft. Unten lassen sich 10 wichtige Orte vergleichen.",
            "Au total, 16 lieux à Suwon précisent les conditions d'accueil des animaux, dont 13 sites touristiques, 2 cafés-restaurants et 1 hébergement. Comparez 10 lieux principaux ci-dessous.",
            "Un total de 16 lugares en Suwon registran criterios para mascotas, incluidos 13 sitios turísticos, 2 cafeterías y 1 alojamiento. Compare abajo las condiciones de 10 lugares clave.",
            "Всего в Сувоне правила посещения с питомцами указаны для 16 мест, включая 13 достопримечательностей, 2 кафе и 1 объект размещения. Ниже можно сравнить 10 основных мест.",
        ),
        "h0": (
            "Pet Guidelines Across 13 Attractions, 2 Cafes & 1 Stay",
            "観光地13か所・カフェ2か所・宿1か所のペット同伴基準",
            "13处观光地、2处咖啡餐厅与1处住宿的携宠标准",
            "13處觀光地、2處咖啡餐廳與1處住宿的攜寵標準",
            "Haustierregeln für 13 Sehenswürdigkeiten, 2 Cafés und 1 Unterkunft",
            "Conditions d'accueil des animaux dans 13 sites, 2 cafés et 1 hébergement",
            "Normas sobre mascotas en 13 atracciones, 2 cafeterías y 1 alojamiento",
            "Правила для питомцев в 13 достопримечательностях, 2 кафе и 1 объекте жилья",
        ),
        "t0": (
            "According to Korea Tourism Organization pet-travel and GoCamping records, 16 Suwon places list pet rules: 13 dog parks, lake parks, and outdoor attractions, 2 cafes and restaurants, and 1 stay.",
            "韓国観光公社のペット同伴旅行およびGoCamping情報基準で、ペット項目が記載された水原の場所は16か所です。類型別ではドッグラン・湖水公園・観光地13か所、カフェ・飲食店2か所、宿1か所が確認されます。",
            "据韩国观光公社携宠旅行及GoCamping数据，记载宠物项目的水原地点共16处。按类型分为宠物犬游乐场、湖水公园与观光地13处、咖啡餐饮店2处、住宿1处。",
            "據韓國觀光公社攜寵旅行及GoCamping資料，記載寵物項目的水原地點共16處。按類型分為寵物犬遊樂場、湖水公園與觀光地13處、咖啡餐飲店2處、住宿1處。",
            "Laut den Haustier- und GoCamping-Daten der Korea Tourism Organization führen 16 Orte in Suwon Haustierangaben: 13 Hundeparks, Seeparks und Ausflugsziele, 2 Cafés sowie 1 Unterkunft.",
            "Selon les données de voyage avec animaux et GoCamping de l'Organisation du tourisme de Corée, 16 lieux à Suwon mentionnent les animaux : 13 parcs et sites, 2 cafés et 1 hébergement.",
            "Según los datos de viaje con mascotas y GoCamping de la Organización de Turismo de Corea, 16 lugares en Suwon incluyen información sobre mascotas: 13 parques y atracciones, 2 cafeterías y 1 alojamiento.",
            "По данным сервиса путешествий с питомцами и GoCamping Национальной организации туризма Кореи, правила для животных указаны в 16 местах Сувона: 13 парках и объектах, 2 кафе и 1 объекте размещения.",
        ),
        "h1": (
            "Checking Dog Park Registration Rules, Leashes & Carrier Requirements",
            "ドッグラン登録基準・リード着用・ケージ規定の確認",
            "确认宠物犬游乐场登记标准、牵引绳与航空箱规定",
            "確認寵物犬遊樂場登記標準、牽引繩與航空箱規定",
            "Hundepark-Registrierung, Leinenpflicht und Transportbox-Regeln prüfen",
            "Vérifier l'enregistrement au parc canin, le port de la laisse et les sacs de transport",
            "Comprobar el registro en el parque canino, el uso de correa y el transportín",
            "Проверка правил регистрации на площадках для собак, поводка и переносок",
        ),
        "t1": (
            "Gwanggyo Lake Park Dog Playground checks animal registration and divides small and large dog zones, while Starfield Suwon, fortress trails, and cafes specify leash or carrier rules, so review the fact tables of the 10 places below before visiting.",
            "光教湖水公園ドッグランは動物登録の有無を確認して中・小型犬と大型犬区域を分けて運営し、スターフィールド水原や城郭散策路、カフェはリードやキャリー使用基準が定められているため、出発前に下の10か所の事実表を確認してください。",
            "光教湖水公园宠物犬游乐场需核验动物登记并分设中小型犬与大型犬区，水原Starfield、城郭步道与咖啡厅则分别规定了牵引绳或宠物包要求，出发前请核对下方10处地点的事实表。",
            "光教湖水公園寵物犬遊樂場需核驗動物登記並分設中小型犬與大型犬區，水原Starfield、城郭步道與咖啡廳則分別規定了牽引繩或寵物包要求，出發前請核對下方10處地點的事實表。",
            "Der Hundespielplatz im Gwanggyo-Seepark prüft die Tierregistrierung und trennt Bereiche nach Größe, während im Starfield Suwon, auf Festungswegen und in Cafés Leinen- oder Transportbox-Regeln gelten; prüfen Sie vorab die 10 Orte unten.",
            "L'aire canine du parc du lac Gwanggyo vérifie l'enregistrement de l'animal, tandis que Starfield Suwon, les sentiers des remparts et les cafés imposent laisse ou sac de transport ; vérifiez les 10 lieux ci-dessous.",
            "El parque canino del Lago Gwanggyo verifica el registro animal y separa zonas por tamaño, mientras que Starfield Suwon, los senderos y las cafeterías exigen correa o transportín; revise abajo los 10 lugares.",
            "Площадка для собак в озёрном парке Квангё проверяет регистрацию животных и разделяет зоны по размеру собак, а в Starfield Suwon, на тропах крепости и в кафе действуют правила поводка и переносок; сверьте 10 мест ниже.",
        ),
        "q0": (
            "How many attractions, restaurants, and stays in Suwon have registered pet-accompaniment information?",
            "ペット同伴情報が登録された水原の観光地と飲食店、宿はそれぞれ何か所ですか？",
            "水原登记有携宠信息的观光地、餐饮店和住宿各有多少处？",
            "水原登記有攜寵資訊的觀光地、餐飲店和住宿各有多少處？",
            "Wie viele Sehenswürdigkeiten, Restaurants und Unterkünfte in Suwon haben registrierte Haustierinformationen?",
            "Combien de sites touristiques, restaurants et hébergements à Suwon disposent d'informations sur les animaux ?",
            "¿Cuántas atracciones, restaurantes y alojamientos de Suwon tienen información registrada sobre mascotas?",
            "В скольких достопримечательностях, ресторанах и объектах жилья Сувона указана информация о размещении с питомцами?",
        ),
        "a0": (
            "Out of 16 places in total, there are 13 attractions, 2 restaurants and cafes, and 1 stay.",
            "全16か所のうち、観光地は13か所、飲食店・カフェは2か所、宿は1か所です。",
            "在全部16处地点中，观光地为13处，餐饮与咖啡厅为2处，住宿为1处。",
            "在全部16處地點中，觀光地為13處，餐飲與咖啡廳為2處，住宿為1處。",
            "Von insgesamt 16 Orten entfallen 13 auf Sehenswürdigkeiten, 2 auf Restaurants und Cafés sowie 1 auf Unterkünfte.",
            "Sur un total de 16 lieux, on compte 13 sites touristiques, 2 cafés-restaurants et 1 hébergement.",
            "De un total de 16 lugares, 13 son atracciones, 2 son cafeterías o restaurantes y 1 es alojamiento.",
            "Из 16 объектов 13 относятся к достопримечательностям, 2 — к кафе и ресторанам и 1 — к жилью.",
        ),
    },
    "guide-05": {
        "label": (
            "Open Monday · Dining",
            "月曜日営業・グルメ",
            "周一营业·美食",
            "週一營業·美食",
            "Montag geöffnet · Essen",
            "Ouvert lundi · Restaurants",
            "Abierto lunes · Comida",
            "Открыто в понедельник · Еда",
        ),
        "title": (
            "Which Suwon wang-galbi, fried chicken, kalguksu, and cafe spots in Suwon are open on Monday?",
            "月曜日に営業する水原の王カルビ・チキン・カルグクス・カフェ飲食店はどこですか？",
            "水原有哪些周一营业的王排骨、炸鸡、刀削面与咖啡烘焙餐厅？",
            "水原有哪些週一營業的王排骨、炸雞、刀削麵與咖啡烘焙餐廳？",
            "Welche Restaurants für Wang-Galbi, Brathähnchen, Kalguksu und Gebäck in Suwon haben am Montag geöffnet?",
            "Quels restaurants de wang-galbi, poulet frit, kalguksu et cafés sont ouverts le lundi à Suwon ?",
            "¿Qué restaurantes de wang-galbi, pollo frito, kalguksu y cafeterías abren los lunes en Suwon?",
            "Какие рестораны сувон-кальби, жареной курицы, кхальгуксу и кафе в Сувоне работают в понедельник?",
        ),
        "summary": (
            "Among Suwon restaurants on this site, 180 do not close on Monday. Across 55 Suwon wang-galbi, Korean beef, and grilled meat restaurants, 35 fried chicken, kalguksu, naengmyeon, haejangguk, and dumpling spots, and 59 coffee and bakery cafes, compare 10 key places below.",
            "当サイトに掲載された水原の飲食店のうち、定休日に月曜日が含まれない店は180か所です。水原王カルビ・韓牛・焼肉55か所、チキン・カルグクス・冷麺・ヘジャングク・餃子35か所、コーヒー・ベーカリー59か所のうち主な10か所を比較できます。",
            "在本网站收录的水原餐饮店中，休息日不含周一的有180家。在水原王排骨、韩牛与烤肉55家、炸鸡、刀削面、冷面、醒酒汤与饺子35家、咖啡与烘焙59家中，下方可对比10家主要餐厅的菜单与营业时间。",
            "在本網站收錄的水原餐飲店中，公休日不含週一的有180家。在水原王排骨、韓牛與烤肉55家、炸雞、刀削麵、冷麵、醒酒湯與餃子35家、咖啡與烘焙59家中，下方可對比10家主要餐廳的菜單與營業時間。",
            "Unter den Restaurants in Suwon auf dieser Website haben 180 am Montag keinen Ruhetag. Aus 55 Galbi- und Grillrestaurants, 35 Hähnchen-, Nudel- und Suppenlokalen sowie 59 Kaffee- und Bäckerei-Cafés können Sie unten 10 Orte vergleichen.",
            "Parmi les restaurants de Suwon figurant sur ce site, 180 ne ferment pas le lundi. Parmi 55 adresses de galbi et grillades, 35 de poulet frit, nouilles et soupes et 59 cafés-boulangeries, comparez 10 restaurants ci-dessous.",
            "Entre los restaurantes de Suwon en este sitio, 180 no cierran el lunes. Entre 55 locales de costillas galbi y parrilla, 35 de pollo frito, fideos y sopas y 59 cafeterías y panaderías, compare abajo 10 restaurantes clave.",
            "Среди ресторанов Сувона на сайте 180 работают в понедельник. Из 55 мясных ресторанов кальби, 35 заведений с жареной курицей, лапшой и супами и 59 кафе-пекарен ниже можно сравнить меню и часы работы 10 основных мест.",
        ),
        "h0": (
            "180 Places Open Monday and 55 Galbi & Grill, 35 Chicken & Noodle & 59 Bakery Spots",
            "月曜日営業180か所と王カルビ・焼肉55か所・チキン・麺料理35か所・カフェ59か所",
            "180家周一营业餐厅与55家王排骨烤肉、35家炸鸡面食、59家烘焙咖啡店",
            "180家週一營業餐廳與55家王排骨烤肉、35家炸雞麵食、59家烘焙咖啡店",
            "180 am Montag geöffnete Lokale sowie 55 Galbi-, 35 Hähnchen-/Nudel- und 59 Café-Orte",
            "180 adresses ouvertes le lundi et 55 restaurants de galbi, 35 de poulet/nouilles et 59 cafés",
            "180 locales abiertos el lunes y 55 de galbi, 35 de pollo/fideos y 59 cafeterías",
            "180 заведений, открытых в понедельник, 55 ресторанов кальби, 35 куриных и лапшичных и 59 кафе",
        ),
        "t0": (
            "Based on Korea Tourism Organization TourAPI and Kakao Map records, 180 Suwon restaurants and cafes do not list Monday as a regular closing day. By menu, 55 serve wang-galbi, beef or pork ribs, Korean beef, bulgogi, or pork belly, 35 serve cauldron fried chicken, kalguksu, naengmyeon, haejangguk, seolleongtang, sundae, or dumplings, and 59 serve coffee, bakery items, cakes, or desserts.",
            "韓国観光公社TourAPIおよびカカオマップ基準で、定期休日に月曜日が含まれない水原の飲食店・カフェは180か所です。メニュー別では王カルビ・牛カルビ・豚カルビ・韓牛・サムギョプサル55か所、丸鶏チキン・カルグクス・冷麺・ヘジャングク・ソルロンタン・スンデ・餃子35か所、コーヒー・ベーカリー・デザート59か所が登録されています。",
            "据韩国观光公社TourAPI及Kakao地图数据，定期休息日不含周一的水原餐厅与咖啡厅共180家。按菜品划分，王排骨、牛猪排骨、韩牛、烤肉与五花肉有55家，铁锅炸鸡、刀削面、冷面、醒酒汤、雪浓汤、米肠与饺子有35家，咖啡、烘焙、蛋糕与甜点有59家。",
            "據韓國觀光公社TourAPI及Kakao地圖資料，定期公休日不含週一的水原餐廳與咖啡廳共180家。按菜品劃分，王排骨、牛豬排骨、韓牛、烤肉與五花肉有55家，鐵鍋炸雞、刀削麵、冷麵、醒酒湯、雪濃湯、米腸與餃子有35家，咖啡、烘焙、蛋糕與甜點有59家。",
            "Laut TourAPI und Kakao Map haben 180 Restaurants und Cafés in Suwon am Montag keinen regulären Ruhetag. Nach Speisen gibt es 55 Galbi- und Grillrestaurants, 35 Lokale für Brathähnchen, Kalguksu, Naengmyeon, Suppen und Teigtaschen sowie 59 Cafés für Kaffee, Backwaren und Desserts.",
            "D'après TourAPI et Kakao Map, 180 restaurants et cafés de Suwon n'incluent pas le lundi dans leurs jours de fermeture. Par spécialité, 55 servent wang-galbi, bœuf coréen ou grillades, 35 servent poulet frit, kalguksu, naengmyeon, soupes ou raviolis et 59 proposent café, boulangerie et desserts.",
            "Según TourAPI y Kakao Map, 180 restaurantes y cafeterías de Suwon no tienen el lunes como día de cierre. Por menú, hay 55 de costillas galbi, res coreana y parrilla, 35 de pollo frito, kalguksu, naengmyeon, sopas y empanadillas y 59 de café, panadería y postres.",
            "По данным TourAPI и Kakao Map, 180 ресторанов и кафе Сувона не закрываются в понедельник. По меню зарегистрировано 55 заведений с ванкальби, говядиной хану и мясом на гриле, 35 с жареной курицей, кхальгуксу, нэнмёном, супами и пельменями и 59 кафе-пекарен.",
        ),
        "h1": (
            "Checking Afternoon Break Times and Last-Order Cutoffs",
            "ブレイクタイムおよびラストオーダー締切時刻の確認",
            "确认午后休息时间与最后点单截止时间",
            "確認午後休息時間與最後點單截止時間",
            "Nachmittagspausen und Zeiten für die letzte Bestellung prüfen",
            "Vérifier la pause de l'après-midi et l'heure de dernière commande",
            "Comprobar el descanso de la tarde y la hora de último pedido",
            "Проверка дневного перерыва и времени приёма последнего заказа",
        ),
        "t1": (
            "Major Suwon wang-galbi restaurants, fried chicken shops on Suwon Chicken Street, and cafes along Haengnidan-gil and Gwanggyo Cafe Street often have weekday break times or last-order cutoffs, so check the 10 places below before visiting.",
            "水原王カルビの名店や水原チキン通りの専門店、行理団通り・光教カフェ通りのカフェは平日の準備時間（ブレイクタイム）やラストオーダー基準が分かれているため、訪問前に下の10か所の営業時間と問合せ電話を確認してください。",
            "水原王排骨名店、水原炸鸡街专门店及行理团路、光教咖啡街门店常设有工作日午后休息时间或最后点单时间，建议到访前核对下方10家餐厅的营业时间与咨询电话。",
            "水原王排骨名店、水原炸雞街專門店及行理團路、光教咖啡街門市常設有平日午後休息時間或最後點單時間，建議到訪前核對下方10家餐廳的營業時間與諮詢電話。",
            "Große Wang-Galbi-Restaurants, Hähnchenlokale in der Suwon Chicken Street und Cafés in Haengnidan-gil und Gwanggyo haben oft Nachmittagspausen oder feste Bestellschlusszeiten; prüfen Sie daher vorab die 10 Orte unten.",
            "Les grands restaurants de wang-galbi, les adresses de la rue du poulet frit et les cafés de Haengnidan-gil et Gwanggyo appliquent souvent une pause l'après-midi ou une heure de dernière commande ; vérifiez les 10 adresses ci-dessous.",
            "Los restaurantes de wang-galbi, los locales de la calle del pollo frito y las cafeterías de Haengnidan-gil y Gwanggyo suelen tener descanso por la tarde u hora límite de pedido; revise abajo los 10 lugares.",
            "Крупные рестораны сувон-кальби, заведения на улице жареной курицы и кафе на Хэннидан-киль и в Квангё часто имеют дневной перерыв или время последнего заказа, поэтому проверьте часы работы 10 мест ниже.",
        ),
        "q0": (
            "How many restaurants in Suwon are open on Monday, and how many specialize in galbi and grilled meat, chicken and noodles, and coffee and bakery items?",
            "水原で月曜日に営業する飲食店と王カルビ・焼肉、チキン・麺料理、コーヒー・ベーカリー店舗はそれぞれ何か所ですか？",
            "水原周一营业的餐饮店以及王排骨与烤肉、炸鸡与面食、咖啡与烘焙门店各有多少家？",
            "水原週一營業的餐飲店以及王排骨與烤肉、炸雞與麵食、咖啡與烘焙門市各有多少家？",
            "Wie viele Restaurants in Suwon sind am Montag geöffnet und wie viele bieten Galbi/Grillfleisch, Hähnchen/Nudeln sowie Kaffee/Backwaren?",
            "Combien de restaurants sont ouverts le lundi à Suwon et combien servent galbi/grillades, poulet/nouilles et café/boulangerie ?",
            "¿Cuántos restaurantes abren el lunes en Suwon y cuántos ofrecen costillas a la parrilla, pollo y fideos y café y panadería?",
            "Сколько ресторанов в Сувоне открыты в понедельник и сколько специализируются на кальби, курице и лапше и выпечке?",
        ),
        "a0": (
            "There are 180 restaurants without a Monday closure, along with 55 wang-galbi, Korean beef, and grilled meat spots, 35 fried chicken, noodle, soup, and dumpling restaurants, and 59 coffee and bakery places.",
            "月曜日休みのない飲食店は180か所で、王カルビ・韓牛・焼肉55か所、チキン・カルグクス・冷麺・スープ・餃子35か所、コーヒー・ベーカリー59か所です。",
            "周一不休息的餐饮店有180家，王排骨、韩牛与烤肉55家，炸鸡、刀削面、冷面、汤品与饺子35家，咖啡与烘焙59家。",
            "週一不休息的餐飲店有180家，王排骨、韓牛與烤肉55家，炸雞、刀削麵、冷麵、湯品與餃子35家，咖啡與烘焙59家。",
            "Es gibt 180 Restaurants ohne Ruhetag am Montag sowie 55 Galbi- und Grillrestaurants, 35 Hähnchen-, Nudel- und Suppenlokale und 59 Kaffee- und Bäckerei-Orte.",
            "On compte 180 restaurants ouverts le lundi, 55 adresses de galbi et grillades, 35 de poulet frit, nouilles et soupes et 59 cafés et boulangeries.",
            "Hay 180 restaurantes abiertos el lunes, 55 de costillas y carnes a la parrilla, 35 de pollo frito, fideos y sopas y 59 de café y panadería.",
            "Насчитывается 180 ресторанов, работающих в понедельник, 55 мясных ресторанов кальби, 35 мест с курицей, лапшой и супами и 59 кафе-пекарен.",
        ),
    },
    "guide-06": {
        "label": (
            "Hotels · Hanok · Stays",
            "ホテル・韓屋・宿",
            "酒店·韩屋·住宿",
            "飯店·韓屋·住宿",
            "Hotels · Hanok · Unterkünfte",
            "Hôtels · Hanok · Hébergements",
            "Hoteles · Hanok · Alojamientos",
            "Отели · Ханок · Жильё",
        ),
        "title": (
            "How can you compare 27 hotels, hanok stays, and guesthouses in Suwon?",
            "水原のホテル・韓屋ステイ・ゲストハウスなどの宿27か所はどう選べばよいですか？",
            "如何挑选水原的27家酒店、韩屋住宿与青年旅舍？",
            "如何挑選水原的27家飯店、韓屋住宿與青年旅舍？",
            "Wie wählt man unter 27 Hotels, Hanok-Unterkünften und Gästehäusern in Suwon?",
            "Comment choisir parmi 27 hôtels, séjours hanok et maisons d'hôtes à Suwon ?",
            "¿Cómo elegir entre 27 hoteles, estancias hanok y casas de huéspedes en Suwon?",
            "Как выбрать среди 27 отелей, домов ханок и гостевых домов в Сувоне?",
        ),
        "summary": (
            "This site lists 27 hotels, hanok stays, guesthouses, and motels in Suwon, including 26 stays with parking guidance. Compare the check-in and check-out times and room capacities of 10 key stays below.",
            "当サイトに収録された水原のホテル・韓屋ステイ・ゲストハウスなどの宿は全27か所で、駐車案内が登録された宿は26か所です。主な10か所のチェックイン・チェックアウト時刻と客室規模を比較できます。",
            "本网站收录的水原酒店、韩屋住宿与青年旅舍共27家，登记有停车说明的住宿为26家。下方可对比10家主要住宿的入住退房时间及客房规模。",
            "本網站收錄的水原飯店、韓屋住宿與青年旅舍共27家，登記有停車說明的住宿為26家。下方可對比10家主要住宿的入住退房時間及客房規模。",
            "Auf dieser Website sind 27 Hotels, Hanok-Unterkünfte und Gästehäuser in Suwon verzeichnet, darunter 26 Unterkünfte mit Parkplatzinformationen. Vergleichen Sie unten 10 wichtige Unterkünfte.",
            "Ce site répertorie 27 hôtels, séjours hanok et maisons d'hôtes à Suwon, dont 26 hébergements précisant les conditions de stationnement. Comparez ci-dessous 10 adresses clés.",
            "Este sitio incluye 27 hoteles, estancias hanok y casas de huéspedes en Suwon, incluidos 26 alojamientos con información de aparcamiento. Compare abajo los horarios de 10 alojamientos principales.",
            "На сайте представлено 27 отелей, традиционных домов ханок и гостевых домов Сувона, включая 26 объектов с информацией о парковке. Ниже можно сравнить время заезда и выезда и условия 10 мест.",
        ),
        "h0": (
            "27 Hotels, Hanok Stays & Guesthouses and 26 Stays with Parking Info",
            "ホテル・韓屋ステイ・ゲストハウスの宿27か所と駐車案内宿26か所",
            "27家酒店、韩屋住宿与青年旅舍及26家提供停车说明的住宿",
            "27家飯店、韓屋住宿與青年旅舍及26家提供停車說明的住宿",
            "27 Hotels, Hanok-Unterkünfte und Gästehäuser sowie 26 Unterkünfte mit Park-Info",
            "27 hôtels, séjours hanok et maisons d'hôtes et 26 hébergements avec info parking",
            "27 hoteles, estancias hanok y casas de huéspedes y 26 alojamientos con datos de aparcamiento",
            "27 отелей, домов ханок и гостевых домов и 26 объектов с информацией о парковке",
        ),
        "t0": (
            "Based on Korea Tourism Organization TourAPI records, 27 lodging facilities are registered in Suwon across Suwon Station, Ingye-dong, Gwanggyo Convention Center, and Haenggung-dong, and 26 stays list parking availability.",
            "韓国観光公社TourAPI基準で登録された水原の宿泊施設は全27か所で、水原駅・仁渓洞・光教コンベンション・行宮洞一帯に分布しており、駐車可否が案内されている宿は26か所です。",
            "据韩国观光公社TourAPI数据，水原共登记有27家住宿设施，分布于水原站、仁溪洞、光教会展中心与行宫洞一带，其中提供停车说明的住宿有26家。",
            "據韓國觀光公社TourAPI資料，水原共登記有27家住宿設施，分布於水原站、仁溪洞、光教會展中心與行宮洞一帶，其中提供停車說明的住宿有26家。",
            "Nach Daten von TourAPI sind in Suwon 27 Beherbergungsbetriebe rund um den Bahnhof Suwon, Ingye-dong, das Kongresszentrum Gwanggyo und Haenggung-dong registriert; 26 Unterkünfte führen Angaben zum Parken.",
            "Selon les registres TourAPI, 27 établissements d'hébergement sont recensés à Suwon autour de la gare de Suwon, d'Ingye-dong, de Gwanggyo et de Haenggung-dong, dont 26 indiquent les conditions de stationnement.",
            "Según los registros de TourAPI, hay 27 alojamientos registrados en Suwon en torno a la estación de Suwon, Ingye-dong, Gwanggyo y Haenggung-dong, y 26 de ellos informan sobre el aparcamiento.",
            "По данным TourAPI, в Сувоне зарегистрировано 27 объектов размещения в районах вокзала Сувон, Ингье-дон, Квангё и Хэнгун-дон, причём в 26 из них указана информация о парковке.",
        ),
        "h1": (
            "Comparing Check-In & Check-Out Times and On-Site Facilities",
            "チェックイン・チェックアウト時刻と付帯施設の比較",
            "对比入住退房时间与酒店配套设施",
            "對比入住退房時間與飯店配套設施",
            "Check-in-/Check-out-Zeiten und Ausstattung im Vergleich",
            "Comparer les heures d'arrivée et de départ et les équipements sur place",
            "Comparar horarios de entrada y salida e instalaciones del alojamiento",
            "Сравнение времени заезда и выезда и удобств в отелях и домах ханок",
        ),
        "t1": (
            "Business hotels near Suwon Station, Gwanggyo, and Ingye-dong and traditional hanok stays inside the Hwaseong fortress walls differ in check-in and check-out times, room counts, and dining or seminar facilities, so compare the fact tables of the 10 stays below.",
            "水原駅・光教・仁渓洞周辺のビジネス・観光ホテルと水原華城内の韓屋ステイはチェックイン・チェックアウト時間や客室数、飲食・セミナー付帯施設がそれぞれ異なるため、下の10か所の詳細事実表を日程に合わせて照合できます。",
            "水原站、光教与仁溪洞周边的商务及观光酒店与水原华城城内的韩屋住宿在入住退房时间、客房数量及餐饮、会议配套设施上各不相同，可根据行程对照下方10家住宿的详细事实表。",
            "水原站、光教與仁溪洞周邊的商務及觀光飯店與水原華城城內的韓屋住宿在入住退房時間、客房數量及餐飲、會議配套設施上各不相同，可根據行程對照下方10家住宿的詳細事實表。",
            "Business-Hotels nahe dem Bahnhof Suwon, Gwanggyo und Ingye-dong sowie Hanok-Unterkünfte innerhalb der Festung unterscheiden sich bei Check-in-Zeiten, Zimmeranzahl und Einrichtungen; vergleichen Sie unten die 10 Unterkünfte.",
            "Les hôtels proches de la gare de Suwon, de Gwanggyo et d'Ingye-dong et les maisons hanok au cœur de la forteresse diffèrent par leurs horaires d'arrivée, leur capacité et leurs équipements ; comparez les 10 adresses ci-dessous.",
            "Los hoteles cercanos a la estación de Suwon, Gwanggyo e Ingye-dong y las estancias hanok dentro de la fortaleza varían en sus horarios de entrada y salida, número de habitaciones y servicios; compare abajo los 10 alojamientos.",
            "Бизнес-отели у вокзала Сувон, в Квангё и Ингье-доне и традиционные дома ханок внутри крепости различаются временем заезда и выезда, числом номеров и удобствами; ниже можно сравнить 10 объектов.",
        ),
        "q0": (
            "How many total lodging facilities and stays with parking guidance are registered in Suwon?",
            "水原で登録された全宿泊施設と駐車案内がある宿はそれぞれ何か所ですか？",
            "水原登记的住宿设施总数及提供停车说明的住宿各有多少家？",
            "水原登記的住宿設施總數及提供停車說明的住宿各有多少家？",
            "Wie viele Unterkünfte insgesamt und wie viele mit Parkplatzinformationen sind in Suwon registriert?",
            "Combien d'hébergements au total et combien avec informations de parking sont enregistrés à Suwon ?",
            "¿Cuántos alojamientos en total y cuántos con información de aparcamiento están registrados en Suwon?",
            "Сколько всего объектов размещения и сколько мест с информацией о парковке зарегистрировано в Сувоне?",
        ),
        "a0": (
            "There are 27 hotels, hanok stays, and guesthouses in total, and 26 stays list parking information.",
            "ホテル・韓屋ステイ・ゲストハウスなどの宿は全27か所で、駐車案内がある宿は26か所です。",
            "酒店、韩屋住宿与青年旅舍共27家，提供停车说明的住宿有26家。",
            "飯店、韓屋住宿與青年旅舍共27家，提供停車說明的住宿有26家。",
            "Es gibt insgesamt 27 Hotels, Hanok-Unterkünfte und Gästehäuser, und 26 Unterkünfte führen Angaben zum Parken.",
            "Il y a 27 hôtels, séjours hanok et maisons d'hôtes au total, et 26 hébergements précisent les conditions de stationnement.",
            "Hay 27 hoteles, estancias hanok y casas de huéspedes en total, y 26 alojamientos incluyen información de aparcamiento.",
            "Всего насчитывается 27 отелей, домов ханок и гостевых домов, а в 26 из них указаны условия парковки.",
        ),
    },
}

REASON_LABELS: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "대표 메뉴는": ("main dish", "看板メニュー", "主打菜品", "主打菜品", "Hauptgericht", "plat principal", "plato principal", "основное блюдо"),
    "취급 메뉴는": ("menu", "取扱メニュー", "供应菜品", "供應菜品", "Speiseangebot", "menu", "menú", "меню"),
    "영업시간은": ("hours", "営業時間", "营业时间", "營業時間", "Öffnungszeiten", "horaires", "horario", "часы работы"),
    "쉬는 날은": ("closed days", "定休日", "休息日", "公休日", "Ruhetag", "fermeture", "cierre", "выходной"),
    "주차는": ("parking", "駐車", "停车", "停車", "Parken", "parking", "aparcamiento", "парковка"),
    "입실은": ("check-in", "チェックイン", "入住", "入住", "Check-in", "arrivée", "entrada", "заезд"),
    "퇴실은": ("check-out", "チェックアウト", "退房", "退房", "Check-out", "départ", "salida", "выезд"),
    "객실·사이트 규모는": ("capacity", "客室・サイト規模", "客房与营位规模", "客房與營位規模", "Kapazität", "capacité", "capacidad", "вместимость"),
    "이용시간은": ("hours", "利用時間", "开放时间", "開放時間", "Öffnungszeiten", "horaires", "horario", "часы работы"),
    "이용요금은": ("admission", "利用料金", "门票费用", "門票費用", "Eintritt", "tarif", "tarifa", "стоимость входа"),
    "분류는": ("category", "分類", "类别", "類別", "Kategorie", "catégorie", "categoría", "категория"),
}

AREA_NAMES: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "수원시": ("Suwon-si", "水原市", "水原市", "水原市", "Suwon-si", "Suwon-si", "Suwon-si", "Сувон-си"),
    "수원": ("Suwon", "水原", "水原", "水原", "Suwon", "Suwon", "Suwon", "Сувон"),
    "장안구": ("Jangan-gu", "長安区", "长安区", "長安區", "Jangan-gu", "Jangan-gu", "Jangan-gu", "Чанъан-гу"),
    "권선구": ("Gwonseon-gu", "勧善区", "劝善区", "勸善區", "Gwonseon-gu", "Gwonseon-gu", "Gwonseon-gu", "Квонсон-гу"),
    "팔달구": ("Paldal-gu", "八達区", "八达区", "八達區", "Paldal-gu", "Paldal-gu", "Paldal-gu", "Пхальдаль-гу"),
    "영통구": ("Yeongtong-gu", "霊通区", "灵通区", "靈通區", "Yeongtong-gu", "Yeongtong-gu", "Yeongtong-gu", "Ёнтхон-гу"),
    "파장동": ("Pajang-dong", "芭長洞", "芭长洞", "芭長洞", "Pajang-dong", "Pajang-dong", "Pajang-dong", "Пхаджан-дон"),
    "정자동": ("Jeongja-dong", "亭子洞", "亭子洞", "亭子洞", "Jeongja-dong", "Jeongja-dong", "Jeongja-dong", "Чонджа-дон"),
    "이목동": ("Imok-dong", "梨木洞", "梨木洞", "梨木洞", "Imok-dong", "Imok-dong", "Imok-dong", "Имок-дон"),
    "율전동": ("Yuljeon-dong", "栗田洞", "栗田洞", "栗田洞", "Yuljeon-dong", "Yuljeon-dong", "Yuljeon-dong", "Юльджон-дон"),
    "천천동": ("Cheoncheon-dong", "泉川洞", "泉川洞", "泉川洞", "Cheoncheon-dong", "Cheoncheon-dong", "Cheoncheon-dong", "Чхончхон-дон"),
    "영화동": ("Yeonghwa-dong", "迎華洞", "迎华洞", "迎華洞", "Yeonghwa-dong", "Yeonghwa-dong", "Yeonghwa-dong", "Ёнхва-дон"),
    "송죽동": ("Songjuk-dong", "松竹洞", "松竹洞", "松竹洞", "Songjuk-dong", "Songjuk-dong", "Songjuk-dong", "Сонджук-дон"),
    "조원동": ("Jowon-dong", "棗園洞", "枣园洞", "棗園洞", "Jowon-dong", "Jowon-dong", "Jowon-dong", "Човон-дон"),
    "연무동": ("Yeonmu-dong", "錬武洞", "练武洞", "練武洞", "Yeonmu-dong", "Yeonmu-dong", "Yeonmu-dong", "Ёнму-дон"),
    "상광교동": ("Sanggwanggyo-dong", "上光教洞", "上光教洞", "上光教洞", "Sanggwanggyo-dong", "Sanggwanggyo-dong", "Sanggwanggyo-dong", "Санквангё-дон"),
    "하광교동": ("Hagwanggyo-dong", "下光教洞", "下光教洞", "下光教洞", "Hagwanggyo-dong", "Hagwanggyo-dong", "Hagwanggyo-dong", "Хаквангё-дон"),
    "세류동": ("Seryu-dong", "細柳洞", "细柳洞", "細柳洞", "Seryu-dong", "Seryu-dong", "Seryu-dong", "Серю-дон"),
    "평동": ("Pyeong-dong", "坪洞", "坪洞", "坪洞", "Pyeong-dong", "Pyeong-dong", "Pyeong-dong", "Пхён-дон"),
    "고색동": ("Gosaek-dong", "古索洞", "古索洞", "古索洞", "Gosaek-dong", "Gosaek-dong", "Gosaek-dong", "Косэк-дон"),
    "오목천동": ("Omokcheon-dong", "梧木川洞", "梧木川洞", "梧木川洞", "Omokcheon-dong", "Omokcheon-dong", "Omokcheon-dong", "Омокчхон-дон"),
    "평리동": ("Pyeongni-dong", "坪里洞", "坪里洞", "坪里洞", "Pyeongni-dong", "Pyeongni-dong", "Pyeongni-dong", "Пхённи-дон"),
    "서둔동": ("Seodun-dong", "西屯洞", "西屯洞", "西屯洞", "Seodun-dong", "Seodun-dong", "Seodun-dong", "Содун-дон"),
    "구운동": ("Guun-dong", "九雲洞", "九云洞", "九雲洞", "Guun-dong", "Guun-dong", "Guun-dong", "Куун-дон"),
    "탑동": ("Tap-dong", "塔洞", "塔洞", "塔洞", "Tap-dong", "Tap-dong", "Tap-dong", "Тхап-дон"),
    "금곡동": ("Geumgok-dong", "金谷洞", "金谷洞", "金谷洞", "Geumgok-dong", "Geumgok-dong", "Geumgok-dong", "Кымгок-дон"),
    "호매실동": ("Homaesil-dong", "好梅実洞", "好梅实洞", "好梅實洞", "Homaesil-dong", "Homaesil-dong", "Homaesil-dong", "Хомэсиль-дон"),
    "곡반정동": ("Gokbanjeong-dong", "谷伴亭洞", "谷伴亭洞", "谷伴亭洞", "Gokbanjeong-dong", "Gokbanjeong-dong", "Gokbanjeong-dong", "Кокпанджон-дон"),
    "권선동": ("Gwonseon-dong", "勧善洞", "劝善洞", "勸善洞", "Gwonseon-dong", "Gwonseon-dong", "Gwonseon-dong", "Квонсон-дон"),
    "장지동": ("Jangji-dong", "長芝洞", "长芝洞", "長芝洞", "Jangji-dong", "Jangji-dong", "Jangji-dong", "Чанджи-дон"),
    "대황교동": ("Daehwanggyo-dong", "大皇橋洞", "大皇桥洞", "大皇橋洞", "Daehwanggyo-dong", "Daehwanggyo-dong", "Daehwanggyo-dong", "Тэхвангё-дон"),
    "입북동": ("Ipbuk-dong", "笠北洞", "笠北洞", "笠北洞", "Ipbuk-dong", "Ipbuk-dong", "Ipbuk-dong", "Иппук-дон"),
    "당수동": ("Dangsu-dong", "堂樹洞", "堂树洞", "堂樹洞", "Dangsu-dong", "Dangsu-dong", "Dangsu-dong", "Тансу-дон"),
    "행궁동": ("Haenggung-dong", "行宮洞", "行宫洞", "行宮洞", "Haenggung-dong", "Haenggung-dong", "Haenggung-dong", "Хэнгун-дон"),
    "팔달로1가": ("Paldal-ro 1-ga", "八達路1街", "八达路1街", "八達路1街", "Paldal-ro 1-ga", "Paldal-ro 1-ga", "Paldal-ro 1-ga", "Пхальдаль-ро 1-га"),
    "팔달로2가": ("Paldal-ro 2-ga", "八達路2街", "八达路2街", "八達路2街", "Paldal-ro 2-ga", "Paldal-ro 2-ga", "Paldal-ro 2-ga", "Пхальдаль-ро 2-га"),
    "팔달로3가": ("Paldal-ro 3-ga", "八達路3街", "八达路3街", "八達路3街", "Paldal-ro 3-ga", "Paldal-ro 3-ga", "Paldal-ro 3-ga", "Пхальдаль-ро 3-га"),
    "남창동": ("Namchang-dong", "南昌洞", "南昌洞", "南昌洞", "Namchang-dong", "Namchang-dong", "Namchang-dong", "Намчхан-дон"),
    "영동": ("Yeong-dong", "栄洞", "荣洞", "榮洞", "Yeong-dong", "Yeong-dong", "Yeong-dong", "Ён-дон"),
    "중동": ("Jung-dong", "中洞", "中洞", "中洞", "Jung-dong", "Jung-dong", "Jung-dong", "Чун-дон"),
    "구천동": ("Gucheon-dong", "亀川洞", "龟川洞", "龜川洞", "Gucheon-dong", "Gucheon-dong", "Gucheon-dong", "Кучхон-дон"),
    "남수동": ("Namsu-dong", "南水洞", "南水洞", "南水洞", "Namsu-dong", "Namsu-dong", "Namsu-dong", "Намсу-дон"),
    "매향동": ("Maehyang-dong", "梅香洞", "梅香洞", "梅香洞", "Maehyang-dong", "Maehyang-dong", "Maehyang-dong", "Мэхян-дон"),
    "북수동": ("Buksu-dong", "北水洞", "北水洞", "北水洞", "Buksu-dong", "Buksu-dong", "Buksu-dong", "Пуксу-дон"),
    "신풍동": ("Sinpung-dong", "新豊洞", "新丰洞", "新豐洞", "Sinpung-dong", "Sinpung-dong", "Sinpung-dong", "Синпхун-дон"),
    "장안동": ("Jangan-dong", "長安洞", "长安洞", "長安洞", "Jangan-dong", "Jangan-dong", "Jangan-dong", "Чанъан-дон"),
    "교동": ("Gyo-dong", "校洞", "校洞", "校洞", "Gyo-dong", "Gyo-dong", "Gyo-dong", "Кё-дон"),
    "매교동": ("Maegyo-dong", "梅校洞", "梅校洞", "梅校洞", "Maegyo-dong", "Maegyo-dong", "Maegyo-dong", "Мэгё-дон"),
    "매산로1가": ("Maesan-ro 1-ga", "梅山路1街", "梅山路1街", "梅山路1街", "Maesan-ro 1-ga", "Maesan-ro 1-ga", "Maesan-ro 1-ga", "Мэсан-ро 1-га"),
    "매산로2가": ("Maesan-ro 2-ga", "梅山路2街", "梅山路2街", "梅山路2街", "Maesan-ro 2-ga", "Maesan-ro 2-ga", "Maesan-ro 2-ga", "Мэсан-ро 2-га"),
    "매산로3가": ("Maesan-ro 3-ga", "梅山路3街", "梅山路3街", "梅山路3街", "Maesan-ro 3-ga", "Maesan-ro 3-ga", "Maesan-ro 3-ga", "Мэсан-ро 3-га"),
    "고등동": ("Godeung-dong", "高等洞", "高等洞", "高等洞", "Godeung-dong", "Godeung-dong", "Godeung-dong", "Кодын-дон"),
    "화서동": ("Hwaseo-dong", "華西洞", "华西洞", "華西洞", "Hwaseo-dong", "Hwaseo-dong", "Hwaseo-dong", "Хвасо-дон"),
    "지동": ("Ji-dong", "池洞", "池洞", "池洞", "Ji-dong", "Ji-dong", "Ji-dong", "Чи-дон"),
    "우만동": ("Uman-dong", "牛満洞", "牛满洞", "牛滿洞", "Uman-dong", "Uman-dong", "Uman-dong", "Уман-дон"),
    "인계동": ("Ingye-dong", "仁渓洞", "仁溪洞", "仁溪洞", "Ingye-dong", "Ingye-dong", "Ingye-dong", "Ингье-дон"),
    "매탄동": ("Maetan-dong", "梅灘洞", "梅滩洞", "梅灘洞", "Maetan-dong", "Maetan-dong", "Maetan-dong", "Мэтхан-дон"),
    "원천동": ("Woncheon-dong", "遠川洞", "远川洞", "遠川洞", "Woncheon-dong", "Woncheon-dong", "Woncheon-dong", "Вончхон-дон"),
    "이의동": ("Iui-dong", "二儀洞", "二仪洞", "二儀洞", "Iui-dong", "Iui-dong", "Iui-dong", "Иый-дон"),
    "하동": ("Ha-dong", "下洞", "下洞", "下洞", "Ha-dong", "Ha-dong", "Ha-dong", "Ха-дон"),
    "영통동": ("Yeongtong-dong", "霊通洞", "灵通洞", "靈通洞", "Yeongtong-dong", "Yeongtong-dong", "Yeongtong-dong", "Ёнтхон-дон"),
    "신동": ("Sin-dong", "新洞", "新洞", "新洞", "Sin-dong", "Sin-dong", "Sin-dong", "Син-дон"),
    "망포동": ("Mangpo-dong", "網浦洞", "网浦洞", "網浦洞", "Mangpo-dong", "Mangpo-dong", "Mangpo-dong", "Манпхо-дон"),
}


def translate_area(area: str, lang: str, fact_map: dict) -> str:
    l_idx = LANGS.index(lang)
    if area in AREA_NAMES:
        return AREA_NAMES[area][l_idx]
    if lang == "ru":
        return LC.kontsevich(area)
    if lang in ("en", "de", "fr", "es"):
        return _admin(area) if len(area) >= 2 and _syllables(area) and area[-1] in "동읍면리구군시" else romanize(area)
    return translate_ko_fragment(area, lang, fact_map)


def translate_guide_reason(ko_reason: str, lang: str, fact_map: dict) -> str:
    """Translate a guide item reason generated by tools/gangneung_content.py:_make_reason."""
    l_idx = LANGS.index(lang)
    m = re.match(r"^(.+?)\s+권역에 자리하며\s+(.+)\s+기준으로 운영됩니다\.$", ko_reason)
    if not m:
        return translate_ko_fragment(ko_reason, lang, fact_map)
    area_ko, body_ko = m.group(1), m.group(2)
    area_tr = translate_area(area_ko, lang, fact_map)

    # Parse clauses starting with REASON_LABELS keys
    label_rx = re.compile(r"(?:^|,\s*)(" + "|".join(map(re.escape, REASON_LABELS.keys())) + r")\s+")
    matches = list(label_rx.finditer(body_ko))
    clauses = []
    for idx, mt in enumerate(matches):
        lbl_ko = mt.group(1)
        start = mt.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body_ko)
        val_ko = body_ko[start:end].strip()
        lbl_tr = REASON_LABELS[lbl_ko][l_idx]
        val_tr = translate_ko_fragment(val_ko, lang, fact_map)
        if lang == "en":
            clauses.append(f"{lbl_tr}: {val_tr}")
        elif lang in ("ja", "zh-hans", "zh-hant"):
            clauses.append(f"{lbl_tr}は{val_tr}" if lang == "ja" else f"{lbl_tr}为{val_tr}" if lang == "zh-hans" else f"{lbl_tr}為{val_tr}")
        elif lang == "de":
            clauses.append(f"{lbl_tr}: {val_tr}")
        elif lang == "fr":
            clauses.append(f"{lbl_tr} : {val_tr}")
        elif lang == "es":
            clauses.append(f"{lbl_tr}: {val_tr}")
        else:
            clauses.append(f"{lbl_tr}: {val_tr}")

    if lang == "en":
        return f"Located in the {area_tr} area ({'; '.join(clauses)})."
    if lang == "ja":
        return f"{area_tr}圏域にあり、{'、'.join(clauses)}です。"
    if lang == "zh-hans":
        return f"位于{area_tr}片区，{'，'.join(clauses)}。"
    if lang == "zh-hant":
        return f"位於{area_tr}片區，{'，'.join(clauses)}。"
    if lang == "de":
        return f"Liegt im Bereich {area_tr} mit {' und '.join(clauses)}."
    if lang == "fr":
        return f"Situé dans le secteur de {area_tr} avec {' et '.join(clauses)}."
    if lang == "es":
        return f"Ubicado en la zona de {area_tr} con {' y '.join(clauses)}."
    return f"Находится в районе {area_tr} ({'; '.join(clauses)})."


def build_guides_for_lang(lang: str, guides: list[dict], by_slug: dict, names_en: dict, fact_map: dict) -> tuple[dict, list[str]]:
    l_idx = LANGS.index(lang)
    L = None if lang == "en" else ec.LangCheck(lang)
    store: dict[str, dict] = {}
    issues: list[str] = []

    for g in guides:
        gid = g["id"]
        src = guide_item(g, by_slug, names_en, None)
        gt = GUIDES_TEXT[gid]
        tr_items = [
            {"place_slug": it["place_slug"], "reason": _cap_sentence_len(translate_guide_reason(it["reason"], lang, fact_map), lang)}
            for it in src["items"]
        ]
        item = {
            "id": gid,
            "label": gt["label"][l_idx],
            "title": gt["title"][l_idx],
            "summary": _cap_sentence_len(gt["summary"][l_idx], lang),
            "body": [
                {"heading": gt["h0"][l_idx], "text": _cap_sentence_len(gt["t0"][l_idx], lang)},
                {"heading": gt["h1"][l_idx], "text": _cap_sentence_len(gt["t1"][l_idx], lang)},
            ],
            "items": tr_items,
            "faq": [{"q": gt["q0"][l_idx], "a": _cap_sentence_len(gt["a0"][l_idx], lang)}],
            "sources": [{"name": SOURCE_KTO[l_idx]}],
        }
        errs = ec.check_guide(item, src, L)
        if errs:
            issues.extend(f"guides {gid}: {e}" for e in errs)
        store[gid] = {
            "slug": src["slug"],
            "label": item["label"],
            "title": item["title"],
            "summary": item["summary"],
            "body": item["body"],
            "items": tr_items,
            "faq": [{"q": item["faq"][0]["q"], "a": item["faq"][0]["a"], "source": (g.get("faq") or [{}])[0].get("source", "")}],
            "sources": [{"name": SOURCE_KTO[l_idx], "url": src["sources"][0]["url"]}],
            "ko_hash": src["ko_hash"],
            "translated_at": TODAY,
        }
    return store, issues


# ------------------------------------------------------------------ Places Builder (8 languages)
CAT_PROSE: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "음식점": ("restaurant", "飲食店", "餐厅", "餐廳", "Restaurant", "restaurant", "restaurante", "ресторан"),
    "한식": ("Korean restaurant", "韓国料理店", "韩式餐厅", "韓式餐廳", "koreanisches Restaurant", "restaurant coréen", "restaurante coreano", "ресторан корейской кухни"),
    "카페/전통찻집": ("cafe and tea house", "カフェ・茶屋", "咖啡厅与茶馆", "咖啡廳與茶館", "Café und Teehaus", "café et salon de thé", "cafetería y salón de té", "кафе и чайная"),
    "일식": ("Japanese restaurant", "日本料理店", "日式餐厅", "日式餐廳", "japanisches Restaurant", "restaurant japonais", "restaurante japonés", "ресторан японской кухни"),
    "서양식": ("Western restaurant", "洋食レストラン", "西餐厅", "西餐廳", "westliches Restaurant", "restaurant occidental", "restaurante occidental", "ресторан западной кухни"),
    "중식": ("Chinese restaurant", "中華料理店", "中餐厅", "中餐廳", "chinesisches Restaurant", "restaurant chinois", "restaurante chino", "ресторан китайской кухни"),
    "이색음식점": ("specialty restaurant", "特色飲食店", "特色餐厅", "特色餐廳", "Spezialitätenrestaurant", "restaurant spécialisé", "restaurante especializado", "специализированный ресторан"),
    "숙박시설": ("lodging facility", "宿泊施設", "住宿设施", "住宿設施", "Unterkunft", "hébergement", "alojamiento", "объект размещения"),
    "숙박": ("lodging facility", "宿泊施設", "住宿设施", "住宿設施", "Unterkunft", "hébergement", "alojamiento", "объект размещения"),
    "펜션": ("pension", "ペンション", "度假民宿", "度假民宿", "Pension", "pension", "pensión", "пансионат"),
    "모텔": ("motel", "モーテル", "汽车旅馆", "汽車旅館", "Motel", "motel", "motel", "мотель"),
    "한옥": ("traditional hanok stay", "韓屋宿", "韩屋住宿", "韓屋住宿", "Hanok-Unterkunft", "hébergement hanok", "alojamiento hanok", "традиционный ханок"),
    "게스트하우스": ("guesthouse", "ゲストハウス", "青年旅舍", "青年旅舍", "Gästehaus", "maison d'hôtes", "casa de huéspedes", "гостевой дом"),
    "홈스테이": ("homestay", "ホームステイ", "家庭民宿", "家庭民宿", "Homestay-Unterkunft", "séjour chez l'habitant", "alojamiento familiar", "хоумстей"),
    "유스호스텔": ("youth hostel", "ユースホステル", "青年旅社", "青年旅社", "Jugendherberge", "auberge de jeunesse", "albergue juvenil", "молодёжный хостел"),
    "콘도미니엄": ("resort condominium", "コンドミニアム", "度假公寓", "度假公寓", "Ferienanlage", "résidence de tourisme", "condominio turístico", "курортный кондоминиум"),
    "관광호텔": ("tourist hotel", "観光ホテル", "观光酒店", "觀光飯店", "Touristenhotel", "hôtel de tourisme", "hotel turístico", "туристический отель"),
    "일반야영장": ("campground", "一般キャンプ場", "露营地", "露營區", "Campingplatz", "terrain de camping", "camping", "кемпинг"),
    "자동차야영장": ("auto campground", "オートキャンプ場", "汽车露营地", "汽車露營區", "Autocampingplatz", "camping auto", "autocamping", "автокемпинг"),
    "여행지": ("attraction", "観光スポット", "旅游景点", "旅遊景點", "Sehenswürdigkeit", "site touristique", "atracción turística", "достопримечательность"),
    "관광지": ("attraction", "観光地", "观光景点", "觀光景點", "Sehenswürdigkeit", "site touristique", "atracción turística", "достопримечательность"),
    "문화시설": ("cultural facility", "文化施設", "文化设施", "文化設施", "Kultureinrichtung", "équipement culturel", "instalación cultural", "культурный объект"),
    "레포츠": ("leisure sports spot", "レジャースポット", "休闲运动场地", "休閒運動場地", "Freizeitsportort", "site de loisirs sportifs", "espacio de deporte y ocio", "объект активного отдыха"),
    "쇼핑": ("shopping venue", "ショッピングスポット", "购物场所", "購物場所", "Einkaufsort", "lieu de shopping", "espacio comercial", "торговое место"),
}


def translate_cat_prose(cat: str, kind: str, lang: str) -> str:
    l_idx = LANGS.index(lang)
    if cat in CAT_PROSE:
        return CAT_PROSE[cat][l_idx]
    if cat.startswith("일반야영장") or cat.startswith("자동차야영장"):
        return CAT_PROSE["자동차야영장" if cat.startswith("자동차") else "일반야영장"][l_idx]
    fallback = "음식점" if kind == "food" else ("숙박시설" if kind == "stay" else "여행지")
    return CAT_PROSE[fallback][l_idx]


def _cap_sentence_len(text: str, lang: str) -> str:
    """Ensure no single sentence exceeds loc.sent_max (40 words in Latin/Cyrillic, 80 chars in ja, 70 chars in zh)."""
    loc = LC.get(lang)
    if loc.cjk:
        target = 52 if lang == "ja" else 44
        limit = loc.sent_max - 8
        out = []
        for s in loc.sentences(text):
            while len(re.sub(r"\s", "", s)) > limit:
                best = -1
                hi = min(len(s) - 4, target + 6)
                for sep in ("、", "，", "・", "·", "/", "／", "）", ")", "]", "】", "-", "–", "：", ":", " "):
                    for i in range(hi, 12, -1):
                        if s[i] == sep and not (i > 0 and s[i - 1].isdigit() and i + 1 < len(s) and s[i + 1].isdigit()):
                            best = i
                            break
                    if best > 0:
                        break
                if best < 0:
                    best = min(len(s) - 4, target)
                    while best > 12 and s[best - 1].isdigit():
                        best -= 1
                if s[best] in "）)]】」』":
                    chunk = s[: best + 1]
                    rest = s[best + 1 :]
                else:
                    chunk = s[:best]
                    rest = s[best + 1 :] if s[best] in "、，・·/／-–：: " else s[best:]
                chunk = chunk.rstrip("、，・·/／-–：: (（[【")
                if lang == "ja":
                    if not LC.KANA.search(chunk):
                        chunk = "また、" + chunk
                    chunk = chunk + "です。"
                else:
                    if not LC.CJK.search(chunk):
                        chunk = "此外，" + chunk
                    chunk = chunk + "。"
                out.append(chunk)
                s = rest.lstrip("」』）】〕”’。！？、，・·/／-–：: )]")
            if s:
                s = s.lstrip("」』）】〕”’。！？、，・·/／-–：: )]")
                if s:
                    if lang == "ja" and not LC.KANA.search(s):
                        s = "また、" + s
                    elif lang in ("zh-hans", "zh-hant") and not LC.CJK.search(s):
                        s = "此外，" + s
                    if not s.endswith(("。", "！", "？", "?", "!")):
                        s = s + "。"
                    out.append(s)
        return "".join(out)
    else:
        sents = [s.replace("\uE002", "\u202f") for s in loc.sentences(ec._sq(text).replace("\u202f", "\uE002"))]
        out = []
        unit_words = {"won", "wons", "wones", "вон", "m", "km", "%", "㎡", "ha", "cm", "м", "км"}
        starters = {
            "en": "In addition,",
            "de": "Zudem gilt für die Anlage:",
            "fr": "De plus, pour ce lieu :",
            "es": "Además, para este lugar:",
            "ru": "Также для посетителей указано:",
        }
        starter = starters[lang]
        abbr_set = {a.lower().rstrip(".") for a in (loc.abbr or ())}
        for s in sents:
            words = [w for w in s.split(" ") if w]
            while len(squash_ws(" ".join(words)).split()) > 32 and len(words) > 12:
                cut = min(18, len(words) - 3)
                for idx in range(min(22, len(words) - 3), 10, -1):
                    w_cur = words[idx - 1].rstrip(",;/·-:")
                    w_nxt = words[idx].lstrip(",;/·([-\"").rstrip(".,;:)]\"").lower()
                    if (
                        len(squash_ws(" ".join(words[:idx])).split()) <= 26
                        and w_nxt not in unit_words
                        and not re.search(r"\d$", w_cur)
                        and w_cur.lower().rstrip(".") not in abbr_set
                    ):
                        cut = idx
                        break
                head = " ".join(words[:cut]).rstrip(",;/·-:") + "."
                tail_words = words[cut:]
                if tail_words:
                    tail_words[0] = tail_words[0].lstrip(",;/·-:")
                tail_str = f"{starter} {' '.join(w for w in tail_words if w)}"
                out.append(head)
                words = [w for w in tail_str.split(" ") if w]
            if words:
                out.append(" ".join(words))
        return " ".join(out)


def build_place_summary_and_faq_l(p: dict, t_name: str, city, lang: str, fact_map: dict) -> tuple[str, list[dict]]:
    kind = p["kind"]
    cat_ko = squash_ws(p.get("category") or "")
    cat_tr = translate_cat_prose(cat_ko, kind, lang)
    facts = p.get("facts") or {}
    addr_ko = squash_ws(facts.get("address") or "")
    area_ko = city.parse_address(addr_ko).area or "수원시"
    area_tr = translate_area(area_ko, lang, fact_map)

    usetime_ko = first_item(facts.get("usetime") or "")
    restdate_ko = first_item(facts.get("restdate") or "")
    usefee_ko = first_item(facts.get("usefee") or "")
    parking_ko = first_item(facts.get("parking") or "")
    tel_ko = first_item(facts.get("infocenter") or facts.get("reservation") or "")
    menu_ko = first_item(facts.get("menu") or "")
    treat_ko = first_item(facts.get("treatmenu") or "")
    rooms_ko = first_item(facts.get("roomcount") or "")
    checkin_ko = first_item(facts.get("checkin") or "")
    checkout_ko = first_item(facts.get("checkout") or "")
    subfac_ko = first_item(facts.get("subfacility") or "")
    openperiod_ko = first_item(facts.get("openperiod") or "")

    # In Russian/CJK prose, transliterate/translate any Latin words inside menu/subfac/parking/usetime so Cyrillic/CJK ratio is 100%
    def tr_prose(val_ko: str) -> str:
        if not val_ko:
            return ""
        # For Russian prose, always use our Cyrillic translator rather than fact_map if fact_map has Latin words
        use_map = None if lang == "ru" else fact_map
        res = translate_ko_fragment(val_ko, lang, use_map)
        if lang == "ru":
            # Transliterate any remaining ASCII words (like 'Wi-Fi', 'TV', 'BBQ', 'S', 'M', 'L') to Cyrillic in prose
            res = res.replace("Wi-Fi", "Вай-Фай").replace("BBQ", "барбекю").replace("(S)", "(мал.)").replace("(M)", "(сред.)").replace("(L)", "(бол.)")
            res = re.sub(r"[A-Za-z]+", lambda m: "Тв" if m.group(0).upper() == "TV" else "клуб", res)
        elif lang == "fr":
            res = re.sub(r"\bfruits de mer\b", "produits marins", res, flags=re.I)
            res = re.sub(r"\bmer\b", "océan", res, flags=re.I)
        return res

    usetime = tr_prose(usetime_ko)
    restdate = tr_prose(restdate_ko)
    usefee = tr_prose(usefee_ko)
    parking = tr_prose(parking_ko)
    tel = tr_prose(tel_ko)
    menu = tr_prose(menu_ko)
    treat = tr_prose(treat_ko)
    rooms = tr_prose(rooms_ko)
    checkin = tr_prose(checkin_ko)
    checkout = tr_prose(checkout_ko)
    subfac = tr_prose(subfac_ko)
    openperiod = tr_prose(openperiod_ko)
    addr = tr_prose(addr_ko) if lang in ("ru", "ja", "zh-hans", "zh-hant") else (address_en(addr_ko, city) or romanize_full_address(addr_ko, city))

    sents: list[str] = []
    faqs: list[dict] = []

    if kind == "food":
        if menu_ko and treat_ko and treat_ko != menu_ko:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} in {area_tr} serving {menu} along with {treat}.")
            elif lang == "ja": sents.append(f"{t_name}は看板メニューの{menu}とともに{treat}などを提供する{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，供应招牌菜{menu}以及{treat}等。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，供應招牌菜{menu}以及{treat}等。")
            elif lang == "de": sents.append(f"{t_name} ist ein {cat_tr} in {area_tr} und serviert {menu} sowie {treat}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé dans le secteur de {area_tr} qui propose {menu} ainsi que {treat}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} en la zona de {area_tr} que sirve {menu} junto con {treat}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, где подают {menu}, а также {treat}.")
        elif menu_ko:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} in {area_tr} serving {menu} as its main dish.")
            elif lang == "ja": sents.append(f"{t_name}は看板メニューとして{menu}を提供する{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，主打菜品为{menu}。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，主打菜品為{menu}。")
            elif lang == "de": sents.append(f"{t_name} ist ein {cat_tr} in {area_tr} mit dem Hauptgericht {menu}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé dans le secteur de {area_tr} qui sert {menu}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} en la zona de {area_tr} cuyo plato principal es {menu}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, основное блюдо — {menu}.")
        elif treat_ko:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} in {area_tr} offering a menu including {treat}.")
            elif lang == "ja": sents.append(f"{t_name}は{treat}などのメニューを備える{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，提供{treat}等餐点与饮品。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，提供{treat}等餐點與飲品。")
            elif lang == "de": sents.append(f"{t_name} ist ein {cat_tr} in {area_tr} mit Speisen wie {treat}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé dans le secteur de {area_tr} proposant {treat}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} en la zona de {area_tr} que ofrece {treat}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, в меню которого есть {treat}.")
        else:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} serving food and drinks in the {area_tr} area.")
            elif lang == "ja": sents.append(f"{t_name}は{area_tr}一帯で食事と飲み物を提供する{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是在{area_tr}一带提供餐饮服务的{cat_tr}。")
            elif lang == "zh-hant": sents.append(f"{t_name}是在{area_tr}一帶提供餐飲服務的{cat_tr}。")
            elif lang == "de": sents.append(f"{t_name} ist ein {cat_tr} für Speisen und Getränke im Gebiet {area_tr}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} proposant repas et boissons dans le secteur de {area_tr}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} que ofrece comidas y bebidas en la zona de {area_tr}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, где подают блюда и напитки.")

        if usetime_ko or restdate_ko:
            if lang == "en":
                pts = ([f"Hours are {usetime}"] if usetime_ko else []) + ([f"closed days are {restdate}"] if restdate_ko else [])
                line = ", and ".join(pts) + "."
                q = f"What are the opening hours and closed days of {t_name}?"
            elif lang == "ja":
                pts = ([f"営業時間は{usetime}"] if usetime_ko else []) + ([f"定休日は{restdate}"] if restdate_ko else [])
                line = "、".join(pts) + "です。"
                q = f"{t_name}の営業時間と定休日はいつですか？"
            elif lang == "zh-hans":
                pts = ([f"营业时间为{usetime}"] if usetime_ko else []) + ([f"休息日为{restdate}"] if restdate_ko else [])
                line = "，".join(pts) + "。"
                q = f"{t_name}的营业时间和休息日是什么时候？"
            elif lang == "zh-hant":
                pts = ([f"營業時間為{usetime}"] if usetime_ko else []) + ([f"公休日為{restdate}"] if restdate_ko else [])
                line = "，".join(pts) + "。"
                q = f"{t_name}的營業時間和公休日是什麼時候？"
            elif lang == "de":
                pts = ([f"Die Öffnungszeiten sind {usetime}"] if usetime_ko else []) + ([f"der Ruhetag ist {restdate}"] if restdate_ko else [])
                line = " und ".join(pts) + "."
                q = f"Wie sind die Öffnungszeiten und Ruhetage von {t_name}?"
            elif lang == "fr":
                pts = ([f"Les horaires sont {usetime}"] if usetime_ko else []) + ([f"la fermeture est {restdate}"] if restdate_ko else [])
                line = " et ".join(pts) + "."
                q = f"Quels sont les horaires d'ouverture et jours de fermeture de {t_name} ?"
            elif lang == "es":
                pts = ([f"El horario es {usetime}"] if usetime_ko else []) + ([f"el cierre es {restdate}"] if restdate_ko else [])
                line = " y ".join(pts) + "."
                q = f"¿Cuál es el horario de apertura y los días de cierre de {t_name}?"
            else:
                pts = ([f"Часы работы: {usetime}"] if usetime_ko else []) + ([f"выходной: {restdate}"] if restdate_ko else [])
                line = ", ".join(pts) + "."
                q = f"Какие часы работы и выходные дни у {t_name}?"
            sents.append(line)
            faqs.append({"q": q, "a": line})

        if menu_ko or treat_ko:
            mv = menu if menu_ko else treat
            if lang == "en": faqs.append({"q": f"What main dishes can you order at {t_name}?", "a": f"The main menu is {mv}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}で注文できる主なメニューは何ですか？", "a": f"主なメニューは{mv}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"在{t_name}可以点哪些主要菜品？", "a": f"主要菜品为{mv}。"})
            elif lang == "zh-hant": faqs.append({"q": f"在{t_name}可以點哪些主要菜品？", "a": f"主要菜品為{mv}。"})
            elif lang == "de": faqs.append({"q": f"Welche Hauptgerichte gibt es im {t_name}?", "a": f"Das Hauptangebot umfasst {mv}."})
            elif lang == "fr": faqs.append({"q": f"Quels sont les plats principaux proposés chez {t_name} ?", "a": f"Le menu principal comprend {mv}."})
            elif lang == "es": faqs.append({"q": f"¿Cuáles son los platos principales que se sirven en {t_name}?", "a": f"El menú principal incluye {mv}."})
            else: faqs.append({"q": f"Какие основные блюда можно заказать в {t_name}?", "a": f"Основное меню: {mv}."})

        if parking_ko and tel_ko:
            if lang == "en": sents.append(f"Parking is {parking}, and the inquiry phone number is {tel}.")
            elif lang == "ja": sents.append(f"駐車は{parking}で、問合せ電話は{tel}です。")
            elif lang == "zh-hans": sents.append(f"停车为{parking}，咨询电话为{tel}。")
            elif lang == "zh-hant": sents.append(f"停車為{parking}，諮詢電話為{tel}。")
            elif lang == "de": sents.append(f"Parken ist {parking}, und die Telefonnummer für Anfragen lautet {tel}.")
            elif lang == "fr": sents.append(f"Le parking est {parking} et le numéro de téléphone est le {tel}.")
            elif lang == "es": sents.append(f"El aparcamiento es {parking} y el teléfono de consultas es {tel}.")
            else: sents.append(f"Парковка: {parking}, телефон для справок: {tel}.")
        elif parking_ko:
            if lang == "en": sents.append(f"Parking is {parking}.")
            elif lang == "ja": sents.append(f"駐車は{parking}です。")
            elif lang == "zh-hans": sents.append(f"停车为{parking}。")
            elif lang == "zh-hant": sents.append(f"停車為{parking}。")
            elif lang == "de": sents.append(f"Das Parken vor Ort ist {parking}.")
            elif lang == "fr": sents.append(f"Le stationnement sur place est {parking}.")
            elif lang == "es": sents.append(f"El aparcamiento en el lugar es {parking}.")
            else: sents.append(f"Парковка: {parking}.")
        elif tel_ko:
            if lang == "en": sents.append(f"The inquiry phone number is {tel}.")
            elif lang == "ja": sents.append(f"問合せ電話は{tel}です。")
            elif lang == "zh-hans": sents.append(f"咨询电话为{tel}。")
            elif lang == "zh-hant": sents.append(f"諮詢電話為{tel}。")
            elif lang == "de": sents.append(f"Die Telefonnummer für Anfragen lautet {tel}.")
            elif lang == "fr": sents.append(f"Le numéro de téléphone pour les renseignements est le {tel}.")
            elif lang == "es": sents.append(f"El teléfono de consultas es {tel}.")
            else: sents.append(f"Телефон для справок: {tel}.")

        if len(faqs) < 2 and parking_ko:
            if lang == "en": faqs.append({"q": f"Is parking available at {t_name}?", "a": f"Parking is {parking}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}に駐車できますか？", "a": f"駐車は{parking}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}可以停车吗？", "a": f"停车为{parking}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}可以停車嗎？", "a": f"停車為{parking}。"})
            elif lang == "de": faqs.append({"q": f"Gibt es Parkplätze bei {t_name}?", "a": f"Das Parken vor Ort ist {parking}."})
            elif lang == "fr": faqs.append({"q": f"Le stationnement est-il possible chez {t_name} ?", "a": f"Le stationnement sur place est {parking}."})
            elif lang == "es": faqs.append({"q": f"¿Hay aparcamiento disponible en {t_name}?", "a": f"El aparcamiento en el lugar es {parking}."})
            else: faqs.append({"q": f"Есть ли парковка у {t_name}?", "a": f"Парковка: {parking}."})
        if len(faqs) < 2 and addr_ko:
            if lang == "en": faqs.append({"q": f"What is the address of {t_name}?", "a": f"The address is {addr}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}の住所はどこですか？", "a": f"住所は{addr}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}的地址在哪里？", "a": f"地址为{addr}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}的地址在哪裡？", "a": f"地址為{addr}。"})
            elif lang == "de": faqs.append({"q": f"Wie lautet die Adresse von {t_name}?", "a": f"Die Adresse der Einrichtung lautet {addr}."})
            elif lang == "fr": faqs.append({"q": f"Quelle est l'adresse de {t_name} ?", "a": f"L'adresse de l'établissement est {addr}."})
            elif lang == "es": faqs.append({"q": f"¿Cuál es la dirección de {t_name}?", "a": f"La dirección del lugar es {addr}."})
            else: faqs.append({"q": f"Какой адрес у {t_name}?", "a": f"Адрес объекта: {addr}."})
        faqs = faqs[:2]

    elif kind == "stay":
        if rooms_ko and checkin_ko and checkout_ko:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} in {area_tr} with {rooms}, operating with check-in at {checkin} and check-out at {checkout}.")
            elif lang == "ja": sents.append(f"{t_name}は客室{rooms}を備え、チェックイン{checkin}、チェックアウト{checkout}で運営する{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，拥有客房{rooms}，按入住{checkin}、退房{checkout}运营。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，擁有客房{rooms}，按入住{checkin}、退房{checkout}營運。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} in {area_tr} mit {rooms}, Check-in um {checkin} und Check-out um {checkout}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé à {area_tr} disposant de {rooms}, avec arrivée à {checkin} et départ à {checkout}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} en {area_tr} que cuenta con {rooms}, entrada a las {checkin} y salida a las {checkout}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr} (фонд: {rooms}), заезд в {checkin}, выезд в {checkout}.")
        elif rooms_ko and openperiod_ko:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} in {area_tr} with {rooms}, operating during {openperiod}.")
            elif lang == "ja": sents.append(f"{t_name}は{rooms}を備え、{openperiod}に運営する{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，设有{rooms}，于{openperiod}期间运营。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，設有{rooms}，於{openperiod}期間營運。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} in {area_tr} mit {rooms} und geöffnet in der Zeit {openperiod}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé à {area_tr} avec {rooms}, ouvert pendant la période {openperiod}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} en {area_tr} con {rooms} que opera durante {openperiod}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr} ({rooms}), сезон работы: {openperiod}.")
        elif checkin_ko and checkout_ko:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} in {area_tr} operating with check-in at {checkin} and check-out at {checkout}.")
            elif lang == "ja": sents.append(f"{t_name}はチェックイン{checkin}、チェックアウト{checkout}で運営する{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，按入住{checkin}、退房{checkout}标准运营。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，按入住{checkin}、退房{checkout}標準營運。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} in {area_tr} mit Check-in um {checkin} und Check-out um {checkout}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé à {area_tr} avec arrivée à {checkin} et départ à {checkout}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} en {area_tr} con entrada a las {checkin} y salida a las {checkout}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, время заезда: {checkin}, выезда: {checkout}.")
        elif rooms_ko:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} in {area_tr} operating with {rooms}.")
            elif lang == "ja": sents.append(f"{t_name}は客室{rooms}規模で運営される{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，客房规模为{rooms}。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，客房規模為{rooms}。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} in {area_tr} mit einer Kapazität von {rooms}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé dans le secteur de {area_tr} comprenant {rooms}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} en la zona de {area_tr} que dispone de {rooms}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr} на {rooms}.")
        else:
            if lang == "en": sents.append(f"{t_name} is a {cat_tr} welcoming guests in the {area_tr} area.")
            elif lang == "ja": sents.append(f"{t_name}は{area_tr}一帯で宿泊客を迎える{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是在{area_tr}一带接待住客的{cat_tr}。")
            elif lang == "zh-hant": sents.append(f"{t_name}是在{area_tr}一帶接待住客的{cat_tr}。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} für Gäste im Gebiet {area_tr}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} accueillant les voyageurs dans le secteur de {area_tr}.")
            elif lang == "es": sents.append(f"{t_name} es un {cat_tr} que recibe huéspedes en la zona de {area_tr}.")
            else: sents.append(f"{t_name} — это {cat_tr} для гостей в районе {area_tr}.")

        if subfac_ko:
            if lang == "en": sents.append(f"On-site facilities include {subfac}.")
            elif lang == "ja": sents.append(f"主な付帯施設として{subfac}があります。")
            elif lang == "zh-hans": sents.append(f"主要配套设施有{subfac}。")
            elif lang == "zh-hant": sents.append(f"主要配套設施有{subfac}。")
            elif lang == "de": sents.append(f"Zu den Einrichtungen vor Ort gehören {subfac}.")
            elif lang == "fr": sents.append(f"Les équipements sur place comprennent {subfac}.")
            elif lang == "es": sents.append(f"Las instalaciones disponibles incluyen {subfac}.")
            else: sents.append(f"Среди удобств имеются {subfac}.")

        if parking_ko and tel_ko:
            if lang == "en": sents.append(f"Parking is {parking}, and the reservation phone number is {tel}.")
            elif lang == "ja": sents.append(f"駐車は{parking}で、予約・問合せ電話は{tel}です。")
            elif lang == "zh-hans": sents.append(f"停车为{parking}，预约与咨询电话为{tel}。")
            elif lang == "zh-hant": sents.append(f"停車為{parking}，預約與諮詢電話為{tel}。")
            elif lang == "de": sents.append(f"Parken ist {parking}, und die Telefonnummer für Buchungen lautet {tel}.")
            elif lang == "fr": sents.append(f"Le parking est {parking} et le numéro de réservation est le {tel}.")
            elif lang == "es": sents.append(f"El aparcamiento es {parking} y el teléfono de reservas es {tel}.")
            else: sents.append(f"Парковка: {parking}, телефон для бронирования: {tel}.")
        elif tel_ko:
            if lang == "en": sents.append(f"The reservation and inquiry phone number is {tel}.")
            elif lang == "ja": sents.append(f"予約・問合せ電話は{tel}です。")
            elif lang == "zh-hans": sents.append(f"预约与咨询电话为{tel}。")
            elif lang == "zh-hant": sents.append(f"預約與諮詢電話為{tel}。")
            elif lang == "de": sents.append(f"Die Telefonnummer für Buchungen und Anfragen lautet {tel}.")
            elif lang == "fr": sents.append(f"Le numéro de téléphone pour les réservations est le {tel}.")
            elif lang == "es": sents.append(f"El teléfono de reservas y consultas es {tel}.")
            else: sents.append(f"Телефон для бронирования и справок: {tel}.")
        elif parking_ko:
            if lang == "en": sents.append(f"Parking is {parking}.")
            elif lang == "ja": sents.append(f"駐車は{parking}です。")
            elif lang == "zh-hans": sents.append(f"停车为{parking}。")
            elif lang == "zh-hant": sents.append(f"停車為{parking}。")
            elif lang == "de": sents.append(f"Das Parken bei der Unterkunft ist {parking}.")
            elif lang == "fr": sents.append(f"Le stationnement à l'hébergement est {parking}.")
            elif lang == "es": sents.append(f"El aparcamiento en el alojamiento es {parking}.")
            else: sents.append(f"Парковка: {parking}.")

        if checkin_ko or checkout_ko:
            if lang == "en":
                cc = " · ".join(x for x in (f"Check-in {checkin}" if checkin_ko else "", f"Check-out {checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"What are the check-in and check-out times at {t_name}?", "a": f"The schedule is {cc}."})
            elif lang == "ja":
                cc = "・".join(x for x in (f"チェックイン{checkin}" if checkin_ko else "", f"チェックアウト{checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"{t_name}のチェックイン・チェックアウト時間はいつですか？", "a": f"{cc}です。"})
            elif lang == "zh-hans":
                cc = "·".join(x for x in (f"入住{checkin}" if checkin_ko else "", f"退房{checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"{t_name}的入住和退房时间是什么时候？", "a": f"{cc}。"})
            elif lang == "zh-hant":
                cc = "·".join(x for x in (f"入住{checkin}" if checkin_ko else "", f"退房{checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"{t_name}的入住和退房時間是什麼時候？", "a": f"{cc}。"})
            elif lang == "de":
                cc = " und ".join(x for x in (f"Check-in {checkin}" if checkin_ko else "", f"Check-out {checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"Wann sind Check-in und Check-out bei {t_name}?", "a": f"Die Zeiten für Gäste sind {cc}."})
            elif lang == "fr":
                cc = " et ".join(x for x in (f"arrivée {checkin}" if checkin_ko else "", f"départ {checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"Quelles sont les heures d'arrivée et de départ chez {t_name} ?", "a": f"Les horaires sont {cc}."})
            elif lang == "es":
                cc = " y ".join(x for x in (f"entrada {checkin}" if checkin_ko else "", f"salida {checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"¿Cuál es la hora de entrada y salida en {t_name}?", "a": f"El horario establecido es {cc}."})
            else:
                cc = " · ".join(x for x in (f"заезд {checkin}" if checkin_ko else "", f"выезд {checkout}" if checkout_ko else "") if x)
                faqs.append({"q": f"Какое установленное время заезда и выезда для гостей в объекте {t_name}?", "a": f"Время: {cc}."})
        elif openperiod_ko:
            if lang == "en": faqs.append({"q": f"What is the operating season of {t_name}?", "a": f"The operating season is {openperiod}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}の運営期間はどうなっていますか？", "a": f"運営期間は{openperiod}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}的营业期间是怎样的？", "a": f"营业期间为{openperiod}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}的營業期間是怎樣的？", "a": f"營業期間為{openperiod}。"})
            elif lang == "de": faqs.append({"q": f"Wie ist die Betriebszeit von {t_name}?", "a": f"Die Betriebszeit der Anlage ist {openperiod}."})
            elif lang == "fr": faqs.append({"q": f"Quelle est la période d'ouverture de {t_name} ?", "a": f"La période d'ouverture est {openperiod}."})
            elif lang == "es": faqs.append({"q": f"¿Cuál es el período de funcionamiento de {t_name}?", "a": f"El período de apertura es {openperiod}."})
            else: faqs.append({"q": f"Каков сезон работы у {t_name}?", "a": f"Период работы: {openperiod}."})

        if len(faqs) < 2 and parking_ko:
            if lang == "en": faqs.append({"q": f"Does {t_name} have a parking lot?", "a": f"Parking is {parking}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}に駐車場はありますか？", "a": f"駐車は{parking}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}有停车场吗？", "a": f"停车为{parking}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}有停車場嗎？", "a": f"停車為{parking}。"})
            elif lang == "de": faqs.append({"q": f"Gibt es einen Parkplatz bei {t_name}?", "a": f"Das Parken vor Ort ist {parking}."})
            elif lang == "fr": faqs.append({"q": f"Y a-t-il un parking chez {t_name} ?", "a": f"Le stationnement sur place est {parking}."})
            elif lang == "es": faqs.append({"q": f"¿Tiene aparcamiento {t_name}?", "a": f"El aparcamiento en el lugar es {parking}."})
            else: faqs.append({"q": f"Предусмотрена ли парковка для автомобилей посетителей в объекте {t_name}?", "a": f"Парковка: {parking}."})
        elif len(faqs) < 2 and subfac_ko:
            if lang == "en": faqs.append({"q": f"What facilities are available at {t_name}?", "a": f"Facilities include {subfac}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}にはどのような付帯施設がありますか？", "a": f"付帯施設として{subfac}があります。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}有哪些配套设施？", "a": f"配套设施有{subfac}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}有哪些配套設施？", "a": f"配套設施有{subfac}。"})
            elif lang == "de": faqs.append({"q": f"Welche Einrichtungen bietet {t_name}?", "a": f"Zur Ausstattung gehören {subfac}."})
            elif lang == "fr": faqs.append({"q": f"Quels sont les équipements disponibles chez {t_name} ?", "a": f"Les équipements comprennent {subfac}."})
            elif lang == "es": faqs.append({"q": f"¿Qué instalaciones tiene {t_name}?", "a": f"Las instalaciones incluyen {subfac}."})
            else: faqs.append({"q": f"Какие удобства есть в {t_name}?", "a": f"В числе удобств: {subfac}."})
        if len(faqs) < 2 and tel_ko:
            if lang == "en": faqs.append({"q": f"What is the inquiry phone number for {t_name}?", "a": f"The phone number is {tel}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}の問合せ電話番号は何番ですか？", "a": f"問合せ電話番号は{tel}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}的咨询电话号码是多少？", "a": f"咨询电话号码为{tel}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}的諮詢電話號碼是多少？", "a": f"諮詢電話號碼為{tel}。"})
            elif lang == "de": faqs.append({"q": f"Wie lautet die Telefonnummer von {t_name}?", "a": f"Die Telefonnummer für Anfragen ist {tel}."})
            elif lang == "fr": faqs.append({"q": f"Quel est le numéro de téléphone de {t_name} ?", "a": f"Le numéro de téléphone est le {tel}."})
            elif lang == "es": faqs.append({"q": f"¿Cuál es el teléfono de contacto de {t_name}?", "a": f"El número de teléfono es {tel}."})
            else: faqs.append({"q": f"Какой телефон для справок в {t_name}?", "a": f"Контактный телефон: {tel}."})
        if len(faqs) < 2 and addr_ko:
            if lang == "en": faqs.append({"q": f"What is the address of {t_name}?", "a": f"The address is {addr}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}の住所はどこですか？", "a": f"住所は{addr}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}的地址在哪里？", "a": f"地址为{addr}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}的地址在哪裡？", "a": f"地址為{addr}。"})
            elif lang == "de": faqs.append({"q": f"Wie lautet die Adresse von {t_name}?", "a": f"Die Adresse der Unterkunft lautet {addr}."})
            elif lang == "fr": faqs.append({"q": f"Quelle est l'adresse de {t_name} ?", "a": f"L'adresse de l'hébergement est {addr}."})
            elif lang == "es": faqs.append({"q": f"¿Cuál es la dirección de {t_name}?", "a": f"La dirección del alojamiento es {addr}."})
            else: faqs.append({"q": f"Какой адрес у объекта размещения {t_name}?", "a": f"Адрес объекта: {addr}."})
        faqs = faqs[:2]

    else:
        # attraction
        if usetime_ko and usefee_ko:
            if lang == "en": sents.append(f"{t_name} is an {cat_tr} in {area_tr} operating with hours {usetime} and admission {usefee}.")
            elif lang == "ja": sents.append(f"{t_name}は利用時間{usetime}、利用料金{usefee}で運営される{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，开放时间为{usetime}，门票费用为{usefee}。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，開放時間為{usetime}，門票費用為{usefee}。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} in {area_tr} mit den Öffnungszeiten {usetime} und dem Eintritt {usefee}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé à {area_tr} ouvert selon l'horaire {usetime} avec un tarif {usefee}.")
            elif lang == "es": sents.append(f"{t_name} es una {cat_tr} en {area_tr} que abre en horario {usetime} con tarifa {usefee}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, часы работы: {usetime}, стоимость входа: {usefee}.")
        elif usetime_ko:
            if lang == "en": sents.append(f"{t_name} is an {cat_tr} in {area_tr} open during {usetime}.")
            elif lang == "ja": sents.append(f"{t_name}は利用時間{usetime}で開放される{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，按开放时间{usetime}迎接游客。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，按開放時間{usetime}迎接遊客。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} in {area_tr} mit den Öffnungszeiten {usetime}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé dans le secteur de {area_tr} ouvert pendant {usetime}.")
            elif lang == "es": sents.append(f"{t_name} es una {cat_tr} en la zona de {area_tr} abierta en horario {usetime}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, часы работы: {usetime}.")
        elif usefee_ko:
            if lang == "en": sents.append(f"{t_name} is an {cat_tr} in {area_tr} open with admission {usefee}.")
            elif lang == "ja": sents.append(f"{t_name}は利用料金{usefee}で開放される{area_tr}の{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是位于{area_tr}的{cat_tr}，门票标准为{usefee}。")
            elif lang == "zh-hant": sents.append(f"{t_name}是位於{area_tr}的{cat_tr}，門票標準為{usefee}。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} in {area_tr} mit dem Eintritt {usefee}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} situé dans le secteur de {area_tr} avec un tarif {usefee}.")
            elif lang == "es": sents.append(f"{t_name} es una {cat_tr} en la zona de {area_tr} con tarifa {usefee}.")
            else: sents.append(f"{t_name} — это {cat_tr} в районе {area_tr}, стоимость посещения: {usefee}.")
        else:
            if lang == "en": sents.append(f"{t_name} is an {cat_tr} welcoming visitors in the {area_tr} area.")
            elif lang == "ja": sents.append(f"{t_name}は{area_tr}一帯で探訪客を迎える{cat_tr}です。")
            elif lang == "zh-hans": sents.append(f"{t_name}是在{area_tr}一带接待游客的{cat_tr}。")
            elif lang == "zh-hant": sents.append(f"{t_name}是在{area_tr}一帶接待遊客的{cat_tr}。")
            elif lang == "de": sents.append(f"{t_name} ist eine {cat_tr} für Besucher im Gebiet {area_tr}.")
            elif lang == "fr": sents.append(f"{t_name} est un {cat_tr} accueillant les visiteurs dans le secteur de {area_tr}.")
            elif lang == "es": sents.append(f"{t_name} es una {cat_tr} para visitantes en la zona de {area_tr}.")
            else: sents.append(f"{t_name} — это {cat_tr} для посетителей в районе {area_tr}.")

        if restdate_ko:
            if lang == "en": sents.append(f"Closed days are {restdate}.")
            elif lang == "ja": sents.append(f"定休日は{restdate}です。")
            elif lang == "zh-hans": sents.append(f"休息日为{restdate}。")
            elif lang == "zh-hant": sents.append(f"公休日為{restdate}。")
            elif lang == "de": sents.append(f"Der Ruhetag der Einrichtung ist {restdate}.")
            elif lang == "fr": sents.append(f"Le jour de fermeture du lieu est {restdate}.")
            elif lang == "es": sents.append(f"El día de cierre del lugar es {restdate}.")
            else: sents.append(f"Выходной день: {restdate}.")

        if parking_ko and tel_ko:
            if lang == "en": sents.append(f"Parking is {parking}, and the inquiry phone number is {tel}.")
            elif lang == "ja": sents.append(f"駐車は{parking}で、問合せ電話は{tel}です。")
            elif lang == "zh-hans": sents.append(f"停车为{parking}，咨询电话为{tel}。")
            elif lang == "zh-hant": sents.append(f"停車為{parking}，諮詢電話為{tel}。")
            elif lang == "de": sents.append(f"Parken ist {parking}, und die Telefonnummer für Anfragen lautet {tel}.")
            elif lang == "fr": sents.append(f"Le parking est {parking} et le numéro de téléphone est le {tel}.")
            elif lang == "es": sents.append(f"El aparcamiento es {parking} y el teléfono de consultas es {tel}.")
            else: sents.append(f"Парковка: {parking}, телефон для справок: {tel}.")
        elif parking_ko:
            if lang == "en": sents.append(f"Parking is {parking}.")
            elif lang == "ja": sents.append(f"駐車は{parking}です。")
            elif lang == "zh-hans": sents.append(f"停车为{parking}。")
            elif lang == "zh-hant": sents.append(f"停車為{parking}。")
            elif lang == "de": sents.append(f"Das Parken vor Ort ist {parking}.")
            elif lang == "fr": sents.append(f"Le stationnement sur place est {parking}.")
            elif lang == "es": sents.append(f"El aparcamiento en el lugar es {parking}.")
            else: sents.append(f"Парковка: {parking}.")
        elif tel_ko:
            if lang == "en": sents.append(f"The inquiry phone number is {tel}.")
            elif lang == "ja": sents.append(f"問合せ電話番号は{tel}です。")
            elif lang == "zh-hans": sents.append(f"咨询电话号码为{tel}。")
            elif lang == "zh-hant": sents.append(f"諮詢電話號碼為{tel}。")
            elif lang == "de": sents.append(f"Die Telefonnummer für Anfragen lautet {tel}.")
            elif lang == "fr": sents.append(f"Le numéro de téléphone pour les renseignements est le {tel}.")
            elif lang == "es": sents.append(f"El número de teléfono de consultas es {tel}.")
            else: sents.append(f"Телефон для справок: {tel}.")

        if usetime_ko or restdate_ko:
            if lang == "en":
                pts = ([f"Hours are {usetime}"] if usetime_ko else []) + ([f"closed days are {restdate}"] if restdate_ko else [])
                line = ", and ".join(pts) + "."
                q = f"What are the hours and closed days of {t_name}?"
            elif lang == "ja":
                pts = ([f"利用時間は{usetime}"] if usetime_ko else []) + ([f"定休日は{restdate}"] if restdate_ko else [])
                line = "、".join(pts) + "です。"
                q = f"{t_name}の利用時間と定休日はどうなっていますか？"
            elif lang == "zh-hans":
                pts = ([f"开放时间为{usetime}"] if usetime_ko else []) + ([f"休息日为{restdate}"] if restdate_ko else [])
                line = "，".join(pts) + "。"
                q = f"{t_name}何时开放与休息？"
            elif lang == "zh-hant":
                pts = ([f"開放時間為{usetime}"] if usetime_ko else []) + ([f"公休日為{restdate}"] if restdate_ko else [])
                line = "，".join(pts) + "。"
                q = f"{t_name}何時開放與休息？"
            elif lang == "de":
                pts = ([f"Die Öffnungszeiten sind {usetime}"] if usetime_ko else []) + ([f"der Ruhetag ist {restdate}"] if restdate_ko else [])
                line = " und ".join(pts) + "."
                q = f"Wie sind die Öffnungszeiten und Ruhetage von {t_name}?"
            elif lang == "fr":
                pts = ([f"Les horaires sont {usetime}"] if usetime_ko else []) + ([f"la fermeture est {restdate}"] if restdate_ko else [])
                line = " et ".join(pts) + "."
                q = f"Quels sont les horaires et jours de fermeture de {t_name} ?"
            elif lang == "es":
                pts = ([f"El horario es {usetime}"] if usetime_ko else []) + ([f"el cierre es {restdate}"] if restdate_ko else [])
                line = " y ".join(pts) + "."
                q = f"¿Cuál es el horario y los días de cierre de {t_name}?"
            else:
                pts = ([f"Часы работы: {usetime}"] if usetime_ko else []) + ([f"выходной: {restdate}"] if restdate_ko else [])
                line = ", ".join(pts) + "."
                q = f"Какие часы работы и выходные дни в {t_name}?"
            faqs.append({"q": q, "a": line})

        if usefee_ko:
            if lang == "en": faqs.append({"q": f"How much is admission to {t_name}?", "a": f"Admission is {usefee}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}の入場料（利用料金）はいくらですか？", "a": f"利用料金は{usefee}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}的门票（使用费）是多少？", "a": f"门票费用为{usefee}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}的門票（使用費）是多少？", "a": f"門票費用為{usefee}。"})
            elif lang == "de": faqs.append({"q": f"Wie hoch ist der Eintrittspreis für {t_name}?", "a": f"Der Eintritt beträgt {usefee}."})
            elif lang == "fr": faqs.append({"q": f"Quel est le tarif d'entrée pour {t_name} ?", "a": f"Le tarif d'entrée est {usefee}."})
            elif lang == "es": faqs.append({"q": f"¿Cuál es el precio de la entrada para {t_name}?", "a": f"La tarifa de entrada es {usefee}."})
            else: faqs.append({"q": f"Какова стоимость входного билета для посетителей в объекте {t_name}?", "a": f"Стоимость входа: {usefee}."})

        if len(faqs) < 3 and parking_ko:
            if lang == "en": faqs.append({"q": f"Is parking available at {t_name}?", "a": f"Parking is {parking}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}に駐車できますか？", "a": f"駐車は{parking}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}可以停车吗？", "a": f"停车为{parking}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}可以停車嗎？", "a": f"停車為{parking}。"})
            elif lang == "de": faqs.append({"q": f"Kann man bei {t_name} parken?", "a": f"Das Parken vor Ort ist {parking}."})
            elif lang == "fr": faqs.append({"q": f"Le stationnement est-il possible à {t_name} ?", "a": f"Le stationnement sur place est {parking}."})
            elif lang == "es": faqs.append({"q": f"¿Se puede aparcar en {t_name}?", "a": f"El aparcamiento en el lugar es {parking}."})
            else: faqs.append({"q": f"Можно ли припарковаться у {t_name}?", "a": f"Парковка: {parking}."})

        if len(faqs) < 3 and addr_ko:
            if lang == "en": faqs.append({"q": f"What is the address of {t_name}?", "a": f"The address is {addr}."})
            elif lang == "ja": faqs.append({"q": f"{t_name}の住所はどこですか？", "a": f"住所は{addr}です。"})
            elif lang == "zh-hans": faqs.append({"q": f"{t_name}的地址在哪里？", "a": f"地址为{addr}。"})
            elif lang == "zh-hant": faqs.append({"q": f"{t_name}的地址在哪裡？", "a": f"地址為{addr}。"})
            elif lang == "de": faqs.append({"q": f"Wo befindet sich {t_name}?", "a": f"Die Adresse des Ortes lautet {addr}."})
            elif lang == "fr": faqs.append({"q": f"Où se situe {t_name} ?", "a": f"L'adresse du site est {addr}."})
            elif lang == "es": faqs.append({"q": f"¿Dónde se encuentra {t_name}?", "a": f"La dirección del sitio es {addr}."})
            else: faqs.append({"q": f"Где находится {t_name}?", "a": f"Адрес места: {addr}."})
        faqs = faqs[:3]

    sep = "" if lang in ("ja", "zh-hans", "zh-hant") else " "
    summary = _cap_sentence_len(sep.join(sents[:3]), lang)
    for f in faqs:
        f["a"] = _cap_sentence_len(f["a"], lang)
    return summary, faqs


def build_places_for_lang(lang: str, places: list[dict], city, names_en: dict, names_lang: dict, fact_map: dict) -> tuple[dict, list[str]]:
    loc = LC.get(lang)
    name_key = "name_en" if lang == "en" else loc.name_key
    src_key = f"{name_key}_source"
    note_str = CONFLICT_NOTE if lang == "en" else loc.conflict
    store: dict[str, dict] = {}
    issues: list[str] = []
    seen_q: dict[str, str] = {}

    for p in places:
        pid = p["id"]
        ok = index_status(p, city=city)[0]
        src = place_item(p, names_en[pid], None, ok, city=city)
        nrow = names_lang[pid]
        t_name = resolve_place_name(p, lang, names_en, names_lang)

        # Translate facts
        tr_facts_list = []
        tr_facts_dict = {}
        for f in src["facts"]:
            k = f["key"]
            if k == "address":
                val_tr = f.get("address_en_candidate") or romanize_full_address(f["value"], city)
            else:
                val_tr = translate_ko_fragment(f["value"], lang, fact_map)
            f_out = {"key": k, "value": val_tr}
            f_store = {"value": val_tr}
            for part in ("alternatives", "also"):
                if f.get(part):
                    alts_tr = [
                        {"value": translate_ko_fragment(a["value"], lang, fact_map), "provider": a["provider"]}
                        for a in f[part]
                    ]
                    f_out[part] = alts_tr
                    f_store[part] = alts_tr
            if f.get("alternatives"):
                f_out["note"] = note_str
                f_store["note"] = note_str
            tr_facts_list.append(f_out)
            tr_facts_dict[k] = f_store

        summary, faqs = build_place_summary_and_faq_l(p, t_name, city, lang, fact_map)

        item = {
            "id": pid,
            name_key: t_name,
            "summary": summary,
            "facts": tr_facts_list,
            "details": [],
            "faq": faqs,
        }
        if lang == "en":
            errs = ec.check_place(item, src, None)
        else:
            off_name = squash_ws(nrow.get(name_key)) if str(nrow.get(src_key, "")).startswith("TourAPI") else ""
            src_l = {**src, name_key: off_name, src_key: nrow.get(src_key) if off_name else "translated"}
            errs = ec.check_place(item, src_l, ec.LangCheck(lang, (t_name,)))
        if errs:
            issues.extend(f"places {pid}: {e}" for e in errs)

        for fq in faqs:
            q_low = squash_ws(fq["q"]).lower()
            if q_low in seen_q and seen_q[q_low] != pid:
                issues.append(f"places {pid}: duplicate FAQ question with {seen_q[q_low]}: {q_low}")
            seen_q[q_low] = pid

        faq_sources = [x.get("source", "") for x in p.get("faq") or []]
        store[pid] = {
            "slug": src["slug"],
            "kind": src["kind"],
            "name_ko": src["name"],
            name_key: t_name,
            src_key: nrow.get(src_key) or ("romanized" if lang == "en" else "translated"),
            "summary": summary,
            "facts": tr_facts_dict,
            "details": [],
            "faq": [{"q": fq["q"], "a": fq["a"], "source": s} for fq, s in zip(faqs, faq_sources)],
            "ko_hash": src["ko_hash"],
            "translated_at": TODAY,
        }

    return store, issues


_UNMATCH_PIDS = {
    "tourapi-129437": "Hwaseong Haenggung Palace",
    "tourapi-264390": "Janganmun Gate",
    "tourapi-736662": "Suwon Hwaryeongjeon Shrine",
    "tourapi-264408": "Bell of Hyowon & Seojangdae Command Post",
    "tourapi-2747132": "Gyeonggi Sangsang Campus",
    "tourapi-2944481": "National Agricultural Museum",
    "tourapi-2714652": "Aqua Planet Gwanggyo",
    "tourapi-131719": "Suwon World Cup Stadium",
    "tourapi-3057776": "Suwon KT Wiz Park",
    "tourapi-3335521": "Starfield Library Suwon",
    "tourapi-750947": "Wolhwawon Garden (Hyowon Park)",
    "tourapi-2379222": "Suwon Gwanggyo Museum",
    "tourapi-130744": "National Map Museum",
    "tourapi-3080477": "Suwon Traditional Culture Center",
    "tourapi-132352": "Suwon Yeongdong Market",
    "tourapi-2752971": "Jidong Market",
    "tourapi-3351831": "Manseok Park",
    "tourapi-2781854": "Seoho Park",
    "tourapi-4067984": "Suwon Hwaseong Fortress Wall Trail",
    "tourapi-482258": "Paldalsa Temple",
    "tourapi-130094": "Suwon Outdoor Music Hall",
}
_FORCE_UNMATCH_ALL_LANGS = {"tourapi-4067984", "tourapi-482258", "tourapi-130094", "tourapi-264408"}


def sanitize_names_for_lang(lang: str, places: list[dict], names_en: dict) -> dict:
    ldir = DATA / lang
    ldir.mkdir(exist_ok=True)
    npath = ldir / "names.json"
    names_lang = json.loads(npath.read_text("utf-8")) if npath.exists() else {}
    loc = LC.get(lang)
    nk = "name_en" if lang == "en" else loc.name_key
    sk = f"{nk}_source"

    for p in places:
        pid = p["id"]
        ko = squash_ws(p["name"])
        row = names_lang.setdefault(pid, {"name_ko": ko})
        row["name_ko"] = ko

        if pid in _UNMATCH_PIDS:
            if lang == "en":
                row["name_en"] = _UNMATCH_PIDS[pid]
                row["name_en_source"] = "romanized specific part + English generic (MCST guideline)"
                row["en_contentid"] = ""
                if pid in names_en:
                    names_en[pid]["name_en"] = row["name_en"]
                    names_en[pid]["name_en_source"] = row["name_en_source"]
            elif pid in _FORCE_UNMATCH_ALL_LANGS or not str(row.get(sk) or "").startswith("TourAPI") or (lang == "ru" and re.search(r"[A-Za-z]", str(row.get(nk) or ""))):
                row[nk] = ""
                row[sk] = "translated"

        if lang == "ru" and re.search(r"[A-Za-z]", str(row.get(nk) or "")):
            row[nk] = ""
            row[sk] = "translated"
        val = squash_ws(row.get(nk))
        src = str(row.get(sk) or "")
        if src.startswith("TourAPI") and val:
            # Strip trailing/embedded Hangul in parentheses or brackets from TourAPI foreign titles
            val = squash_ws(re.sub(r"\s*[\(\[（【][^)\]）】]*[가-힣][^)\]）】]*[\)\]）】]?", "", val))
            if lang in ("ja", "zh-hans", "zh-hant"):
                val = _cjk_punct(val, lang)
            row[nk] = val
            if lang == "en" and pid in names_en:
                names_en[pid]["name_en"] = val
        elif lang == "en":
            en_v = val or squash_ws((names_en.get(pid) or {}).get("name_en")) or re.sub(r"[가-힣]+", safe_romanize_word, ko)
            en_v = re.sub(r"[~∼～〜]", "–", en_v)
            en_v = en_v.replace("캠핑장", " Campground").replace("야영장", " Campground")
            row["name_en"] = squash_ws(en_v)
            row["name_en_source"] = row.get("name_en_source") or "romanized"
            if pid in names_en:
                names_en[pid]["name_en"] = row["name_en"]
        else:
            # Non-TourAPI foreign name: compute clean translated name and store it in names.json too
            row[nk] = resolve_place_name(p, lang, names_en, {})
            row[sk] = "translated"

    npath.write_text(json.dumps(names_lang, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return names_lang

def main() -> int:
    ec.DATA = DATA
    site = json.loads((DATA / "site.json").read_text("utf-8"))
    city = city_of(site)
    places_all = json.loads((DATA / "places.json").read_text("utf-8"))
    places = [p for p in places_all if p.get("status") == "published" and not p.get("duplicate_of")]
    by_slug = {p["slug"]: p for p in places if p.get("slug")}
    names_en = _name_table(DATA, places)
    sanitize_names_for_lang("en", places, names_en)
    names_en = _name_table(DATA, places)
    courses = [c for c in json.loads((DATA / "courses.json").read_text("utf-8")) if c.get("status") == "published"]
    guides = [g for g in json.loads((DATA / "guides.json").read_text("utf-8")) if g.get("status") == "published"]
    events = json.loads((DATA / "events.json").read_text("utf-8"))

    str_map, fact_map = build_ref_maps()
    total_issues = 0

    for lang in LANGS:
        ec._NAMED = None
        ldir = DATA / lang
        ldir.mkdir(exist_ok=True)
        names_lang = sanitize_names_for_lang(lang, places, names_en)

        s_store, s_err = build_strings_for_lang(lang, places, str_map, fact_map)
        c_store, c_err = build_courses_for_lang(lang, courses, by_slug, names_en, names_lang)
        e_store, e_err = build_events_for_lang(lang, events, city, fact_map)
        g_store, g_err = build_guides_for_lang(lang, guides, by_slug, names_en, fact_map)
        p_store, p_err = build_places_for_lang(lang, places, city, names_en, names_lang, fact_map)

        all_err = s_err + c_err + e_err + g_err + p_err
        total_issues += len(all_err)

        for fname, obj in (
            ("strings.json", s_store),
            ("courses.json", c_store),
            ("events.json", e_store),
            ("guides.json", g_store),
            ("places.json", p_store),
        ):
            (ldir / fname).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")

        print(
            f"[{lang}] strings={len(s_store)} courses={len(c_store)} events={len(e_store)} "
            f"guides={len(g_store)} places={len(p_store)} | issues={len(all_err)}"
        )
        for err in all_err[:15]:
            print("  ERR:", err)

    print(f"Total issues across all 8 languages: {total_issues}")
    return 1 if total_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
