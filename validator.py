
import re
from pathlib import Path
from collections import Counter
from xml.dom import minidom, Node
from xml.parsers.expat import ExpatError

from database import inicjalizuj_baze, polacz


# ==========================================
# KONFIGURACJA PROJEKTU
# ==========================================

KATALOG_PROJEKTU = Path(__file__).resolve().parent

FOLDER_ZAMOWIENIA = KATALOG_PROJEKTU / "zamowienia"
FOLDER_NOWE = FOLDER_ZAMOWIENIA / "nowe"

FOLDER_POPRAWNE = FOLDER_ZAMOWIENIA / "poprawne"
FOLDER_ODRZUCONE = FOLDER_ZAMOWIENIA / "odrzucone"
FOLDER_DO_WERYFIKACJI = FOLDER_ZAMOWIENIA / "do_weryfikacji"

MAX_ILOSC = 100

WZOR_ID = re.compile(r"^ZAM-\d{4,}$")


# ==========================================
# SLOWNIKI PRODUKTOW
# ==========================================

ROWERY = {
    "MTB": [
        "Giant Talon 3",
        "Kross Level 4.0",
        "Trek Marlin 5"
    ],

    "Miejski": [
        "Kross Trans 5.0",
        "Romet Gazela",
        "Giant Escape 3"
    ],

    "Szosowy": [
        "Specialized Allez",
        "Trek Domane AL 2",
        "Giant Contend 3"
    ]
}

ROZMIARY = ["S", "M", "L", "XL"]


# ==========================================
# POMOCNICZE FUNKCJE DOM
# ==========================================

def pobierz_dzieci(element, nazwa):
    """
    Zwraca bezposrednie elementy potomne
    o podanej nazwie.
    """

    return [
        dziecko
        for dziecko in element.childNodes
        if dziecko.nodeType == Node.ELEMENT_NODE
        and dziecko.tagName == nazwa
    ]


def pobierz_tekst(element):
    """
    Pobiera tekst znajdujacy sie wewnatrz
    elementu XML.
    """

    tekst = ""

    for dziecko in element.childNodes:
        if dziecko.nodeType in (
            Node.TEXT_NODE,
            Node.CDATA_SECTION_NODE
        ):
            tekst += dziecko.data

    return tekst.strip()


def pobierz_pole(element, nazwa, opis, bledy):
    """
    Sprawdza, czy wymagane pole istnieje,
    wystepuje tylko raz i nie jest puste.
    """

    if element is None:
        return None

    znalezione = pobierz_dzieci(element, nazwa)

    if len(znalezione) == 0:
        bledy.append(f"Brak wymaganego pola: {opis}")
        return None

    if len(znalezione) > 1:
        bledy.append(f"Pole wystepuje wiecej niz raz: {opis}")
        return None

    wartosc = pobierz_tekst(znalezione[0])

    if not wartosc:
        bledy.append(f"Puste pole: {opis}")
        return None

    return wartosc


def pobierz_kontener(element, nazwa, opis, bledy):
    """
    Sprawdza istnienie wymaganego kontenera XML.
    """

    znalezione = pobierz_dzieci(element, nazwa)

    if len(znalezione) == 0:
        bledy.append(f"Brak sekcji: {opis}")
        return None

    if len(znalezione) > 1:
        bledy.append(f"Sekcja wystepuje wielokrotnie: {opis}")
        return None

    return znalezione[0]


# ==========================================
# OBSLUGA BAZY DANYCH
# ==========================================

def pobierz_id_z_bazy():
    """
    Pobiera identyfikatory zamowien, ktore
    zostaly juz zarejestrowane w SQLite.
    """

    inicjalizuj_baze()

    conn = polacz()

    try:
        wynik = conn.execute(
            "SELECT id FROM zamowienia"
        ).fetchall()

        return {
            rekord["id"]
            for rekord in wynik
        }

    finally:
        conn.close()


# ==========================================
# WYKRYWANIE DUPLIKATOW ID
# ==========================================

def znajdz_duplikaty_id(pliki):
    """
    Przeglada wszystkie nowe zamowienia
    i wykrywa powtarzajace sie numery ID.
    """

    wystapienia = Counter()

    for plik in pliki:
        try:
            doc = minidom.parse(str(plik))
            root = doc.documentElement

            if root.tagName != "zamowienie":
                continue

            elementy_id = pobierz_dzieci(root, "id")

            if len(elementy_id) != 1:
                continue

            numer = pobierz_tekst(elementy_id[0])

            if numer:
                wystapienia[numer] += 1

        except (ExpatError, OSError, UnicodeError):
            continue

    return {
        numer
        for numer, liczba in wystapienia.items()
        if liczba > 1
    }


# ==========================================
# GLOWNA WALIDACJA ZAMOWIENIA
# ==========================================

def waliduj_zamowienie(sciezka, duplikaty, id_w_bazie):

    bledy = []
    ostrzezenia = []

    numer_id = None

    # --------------------------------------
    # 1. ODCZYT XML
    # --------------------------------------

    try:
        doc = minidom.parse(str(sciezka))
        root = doc.documentElement

    except (ExpatError, OSError, UnicodeError) as blad:

        return {
            "status": "ODRZUCONE",
            "id": None,
            "bledy": [f"Nie mozna odczytac XML: {blad}"],
            "ostrzezenia": []
        }

    # --------------------------------------
    # 2. SPRAWDZENIE GLOWNEGO ELEMENTU
    # --------------------------------------

    if root.tagName != "zamowienie":

        return {
            "status": "ODRZUCONE",
            "id": None,
            "bledy": [
                "Nieprawidlowa struktura XML. "
                "Oczekiwano elementu zamowienie."
            ],
            "ostrzezenia": []
        }

    # --------------------------------------
    # 3. WALIDACJA ID
    # --------------------------------------

    numer_id = pobierz_pole(
        root,
        "id",
        "numer zamowienia",
        bledy
    )

    if numer_id is not None:

        if not WZOR_ID.fullmatch(numer_id):

            bledy.append(
                f"Nieprawidlowy format ID: {numer_id}"
            )

        elif numer_id in duplikaty:

            bledy.append(
                f"Zduplikowany numer zamowienia: {numer_id}"
            )

        elif numer_id in id_w_bazie:

            bledy.append(
                f"Zamowienie o ID {numer_id} istnieje juz w bazie danych."
            )

    # --------------------------------------
    # 4. WALIDACJA DANYCH KLIENTA
    # --------------------------------------

    klient = pobierz_kontener(
        root,
        "klient",
        "klient",
        bledy
    )

    if klient is not None:

        imie = pobierz_pole(
            klient,
            "imie",
            "imie klienta",
            bledy
        )

        nazwisko = pobierz_pole(
            klient,
            "nazwisko",
            "nazwisko klienta",
            bledy
        )

    # --------------------------------------
    # 5. WALIDACJA PRODUKTU
    # --------------------------------------

    produkt = pobierz_kontener(
        root,
        "produkt",
        "produkt",
        bledy
    )

    if produkt is not None:

        model = pobierz_pole(
            produkt,
            "model",
            "model roweru",
            bledy
        )

        typ = pobierz_pole(
            produkt,
            "typ",
            "typ roweru",
            bledy
        )

        rozmiar = pobierz_pole(
            produkt,
            "rozmiar_ramy",
            "rozmiar ramy",
            bledy
        )

    else:
        model = None
        typ = None
        rozmiar = None

    # --------------------------------------
    # 6. WALIDACJA ILOSCI
    # --------------------------------------

    ilosc = pobierz_pole(
        root,
        "ilosc",
        "ilosc rowerow",
        bledy
    )

    if ilosc is not None:

        try:
            ilosc_num = int(ilosc)

            if ilosc_num <= 0:

                bledy.append(
                    "Ilosc rowerow musi byc wieksza od zera."
                )

            elif ilosc_num > MAX_ILOSC:

                bledy.append(
                    f"Przekroczono maksymalna ilosc: {MAX_ILOSC}."
                )

        except ValueError:

            bledy.append(
                f"Ilosc musi byc liczba calkowita: {ilosc}"
            )

    # --------------------------------------
    # 7. WALIDACJA TYPU ROWERU
    # --------------------------------------

    if typ is not None:

        if typ not in ROWERY:

            bledy.append(
                f"Nieobslugiwany typ roweru: {typ}"
            )

    # --------------------------------------
    # 8. WALIDACJA MODELU
    # --------------------------------------

    if model is not None:

        wszystkie_modele = [
            model_roweru
            for modele in ROWERY.values()
            for model_roweru in modele
        ]

        if model not in wszystkie_modele:

            bledy.append(
                f"Nieznany model roweru: {model}"
            )

        elif typ in ROWERY:

            if model not in ROWERY[typ]:

                ostrzezenia.append(
                    f"Model {model} nie pasuje do typu {typ}."
                )

    # --------------------------------------
    # 9. WALIDACJA ROZMIARU RAMY
    # --------------------------------------

    if rozmiar is not None:

        if rozmiar not in ROZMIARY:

            ostrzezenia.append(
                f"Nieobslugiwany rozmiar ramy: {rozmiar}"
            )

    # --------------------------------------
    # 10. USTALENIE WYNIKU WALIDACJI
    # --------------------------------------

    if bledy:
        status = "ODRZUCONE"

    elif ostrzezenia:
        status = "DO_WERYFIKACJI"

    else:
        status = "POPRAWNE"

    return {
        "status": status,
        "id": numer_id,
        "bledy": bledy,
        "ostrzezenia": ostrzezenia
    }


# ==========================================
# PRZYGOTOWANIE FOLDEROW
# ==========================================

def przygotuj_foldery():

    FOLDER_NOWE.mkdir(
        parents=True,
        exist_ok=True
    )

    FOLDER_POPRAWNE.mkdir(
        parents=True,
        exist_ok=True
    )

    FOLDER_ODRZUCONE.mkdir(
        parents=True,
        exist_ok=True
    )

    FOLDER_DO_WERYFIKACJI.mkdir(
        parents=True,
        exist_ok=True
    )


# ==========================================
# PRZENOSZENIE ZAMOWIENIA
# ==========================================

def przenies_z_wynikiem(sciezka, wynik):
    """
    Przenosi oryginalny plik XML do folderu
    odpowiadajacego wynikowi walidacji.

    Nie tworzy kopii i nie nadpisuje istniejacych plikow.
    """

    foldery = {
        "POPRAWNE": FOLDER_POPRAWNE,
        "ODRZUCONE": FOLDER_ODRZUCONE,
        "DO_WERYFIKACJI": FOLDER_DO_WERYFIKACJI
    }

    folder_docelowy = foldery[wynik["status"]]
    sciezka_docelowa = folder_docelowy / sciezka.name

    if sciezka_docelowa.exists():

        print(
            f"[BLAD] Nie przeniesiono {sciezka.name}. "
            f"Plik docelowy juz istnieje: {sciezka_docelowa}"
        )

        return False

    try:

        sciezka.rename(sciezka_docelowa)

        return True

    except OSError as blad:

        print(
            f"[BLAD] Nie udalo sie przeniesc "
            f"{sciezka.name}: {blad}"
        )

        return False


# ==========================================
# WALIDACJA NOWYCH ZAMOWIEN
# ==========================================

def przetworz_zamowienia():

    przygotuj_foldery()

    pliki = sorted(
        FOLDER_NOWE.glob("*.xml")
    )

    if not pliki:

        print("\nBrak nowych zamowien do walidacji.")
        return

    # Duplikaty wsrod aktualnych plikow
    duplikaty = znajdz_duplikaty_id(pliki)

    # Identyfikatory juz zarejestrowane w SQLite
    id_w_bazie = pobierz_id_z_bazy()

    print("\n========================================")
    print("          WALIDACJA ZAMOWIEN")
    print("========================================")

    licznik = Counter()
    liczba_przeniesionych = 0

    for plik in pliki:

        wynik = waliduj_zamowienie(
            plik,
            duplikaty,
            id_w_bazie
        )

        status = wynik["status"]

        # Przenosimy plik dopiero po zakonczeniu walidacji
        przeniesiono = przenies_z_wynikiem(
            plik,
            wynik
        )

        print("\n----------------------------------------")
        print(f"PLIK: {plik.name}")
        print(f"ID: {wynik['id']}")
        print(f"WYNIK: {status}")

        for blad in wynik["bledy"]:
            print(f"[BLAD] {blad}")

        for ostrzezenie in wynik["ostrzezenia"]:
            print(f"[OSTRZEZENIE] {ostrzezenie}")

        if status == "POPRAWNE":
            print("Zamowienie moze zostac zarejestrowane.")

        elif status == "DO_WERYFIKACJI":
            print("Zamowienie wymaga sprawdzenia przez pracownika.")

        else:
            print("Zamowienie zostalo odrzucone.")

        if przeniesiono:
            licznik[status] += 1
            liczba_przeniesionych += 1
            print("Plik przeniesiono do folderu wynikowego.")
        else:
            print("Plik pozostal w folderze zamowienia/nowe.")

    # --------------------------------------
    # RAPORT KONCOWY
    # --------------------------------------

    print("\n========================================")
    print("          RAPORT WALIDACJI")
    print("========================================")

    print(f"Znaleziono plikow: {len(pliki)}")
    print(f"Przeniesiono: {liczba_przeniesionych}")

    print(f"Poprawne: {licznik['POPRAWNE']}")
    print(f"Odrzucone: {licznik['ODRZUCONE']}")
    print(f"Do weryfikacji: {licznik['DO_WERYFIKACJI']}")

    print("\nWyniki zapisano w folderach:")
    print(FOLDER_POPRAWNE)
    print(FOLDER_ODRZUCONE)
    print(FOLDER_DO_WERYFIKACJI)

    print("========================================")


# ==========================================
# START PROGRAMU
# ==========================================

if __name__ == "__main__":

    przetworz_zamowienia()
