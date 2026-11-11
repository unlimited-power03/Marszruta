
import os
import time
import random
from pathlib import Path
from xml.dom.minidom import Document

from database import (
    inicjalizuj_baze,
    zarezerwuj_numer_zamowienia
)


# ==========================================
# KONFIGURACJA PROJEKTU
# ==========================================

KATALOG_PROJEKTU = Path(__file__).resolve().parent
FOLDER_ZAMOWIENIA = KATALOG_PROJEKTU / "zamowienia" / "nowe"

INTERWAL_GENEROWANIA = 1


# ==========================================
# DANE DO LOSOWANIA
# ==========================================

IMIONA = [
    "Jan", "Anna", "Piotr", "Marta",
    "Tomasz", "Katarzyna", "Adam", "Julia"
]

NAZWISKA = [
    "Kowalski", "Nowak", "Wisniewski",
    "Wojcik", "Kaminski", "Lewandowski"
]

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
# SCENARIUSZE GENEROWANIA ZAMOWIEN
# ==========================================

SCENARIUSZE = {
    "poprawne": 70,

    "brak_id": 5,
    "brak_nazwiska": 5,
    "ilosc_zero": 5,
    "ilosc_ujemna": 5,
    "nieznany_typ": 2,
    "nieznany_model": 3,

    "bledny_rozmiar": 2,
    "niezgodny_model_typ": 3
}


# ==========================================
# LOSOWANIE SCENARIUSZA
# ==========================================

def losuj_scenariusz():

    return random.choices(
        population=list(SCENARIUSZE.keys()),
        weights=list(SCENARIUSZE.values()),
        k=1
    )[0]


# ==========================================
# GENEROWANIE ZAMOWIENIA XML
# ==========================================

def generuj_zamowienie(zamowienie_id):

    # Losowanie danych klienta
    imie = random.choice(IMIONA)
    nazwisko = random.choice(NAZWISKA)

    # Losowanie typu roweru
    typ = random.choice(list(ROWERY.keys()))

    # Losowanie modelu pasujacego do typu
    model = random.choice(ROWERY[typ])

    # Losowanie pozostalych danych
    rozmiar = random.choice(ROZMIARY)
    ilosc = random.randint(1, 3)

    # Losowanie scenariusza
    scenariusz = losuj_scenariusz()

    # ======================================
    # WPROWADZANIE KONTROLOWANYCH BLEDOW
    # ======================================

    if scenariusz == "brak_id":
        pass

    elif scenariusz == "brak_nazwiska":
        nazwisko = ""

    elif scenariusz == "ilosc_zero":
        ilosc = 0

    elif scenariusz == "ilosc_ujemna":
        ilosc = -2

    elif scenariusz == "nieznany_typ":
        typ = "Elektryczny"

    elif scenariusz == "nieznany_model":
        model = "Nieznany Model X"

    elif scenariusz == "bledny_rozmiar":
        rozmiar = "XXL"

    elif scenariusz == "niezgodny_model_typ":
        typ = "Miejski"
        model = "Giant Talon 3"

    # ======================================
    # TWORZENIE DOKUMENTU DOM
    # ======================================

    doc = Document()

    zamowienie = doc.createElement("zamowienie")
    doc.appendChild(zamowienie)

    # Numer zamowienia
    if scenariusz != "brak_id":

        id_element = doc.createElement("id")
        id_element.appendChild(
            doc.createTextNode(zamowienie_id)
        )
        zamowienie.appendChild(id_element)

    # Dane klienta
    klient = doc.createElement("klient")
    zamowienie.appendChild(klient)

    imie_element = doc.createElement("imie")
    imie_element.appendChild(doc.createTextNode(imie))
    klient.appendChild(imie_element)

    if nazwisko:

        nazwisko_element = doc.createElement("nazwisko")
        nazwisko_element.appendChild(
            doc.createTextNode(nazwisko)
        )
        klient.appendChild(nazwisko_element)

    # Dane produktu
    produkt = doc.createElement("produkt")
    zamowienie.appendChild(produkt)

    model_element = doc.createElement("model")
    model_element.appendChild(doc.createTextNode(model))
    produkt.appendChild(model_element)

    typ_element = doc.createElement("typ")
    typ_element.appendChild(doc.createTextNode(typ))
    produkt.appendChild(typ_element)

    rozmiar_element = doc.createElement("rozmiar_ramy")
    rozmiar_element.appendChild(
        doc.createTextNode(rozmiar)
    )
    produkt.appendChild(rozmiar_element)

    # Ilosc zamowionych rowerow
    ilosc_element = doc.createElement("ilosc")
    ilosc_element.appendChild(
        doc.createTextNode(str(ilosc))
    )
    zamowienie.appendChild(ilosc_element)

    # ======================================
    # ZAPIS DOKUMENTU XML
    # ======================================

    nazwa_pliku = f"{zamowienie_id}.xml"
    sciezka = FOLDER_ZAMOWIENIA / nazwa_pliku

    # Najpierw zapisujemy plik tymczasowy
    sciezka_tmp = FOLDER_ZAMOWIENIA / (
        nazwa_pliku + ".tmp"
    )

    with open(sciezka_tmp, "w", encoding="utf-8") as plik:

        doc.writexml(
            plik,
            indent="  ",
            addindent="  ",
            newl="\n"
        )

    # Publikujemy XML dopiero po zakonczeniu zapisu
    os.replace(sciezka_tmp, sciezka)

    # ======================================
    # INFORMACJE W KONSOLI
    # ======================================

    print("\n========================================")
    print(f"UTWORZONO: {nazwa_pliku}")
    print("========================================")

    print(f"Scenariusz: {scenariusz}")
    print(f"Klient: {imie} {nazwisko}")
    print(f"Model: {model}")
    print(f"Typ: {typ}")
    print(f"Rozmiar ramy: {rozmiar}")
    print(f"Ilosc: {ilosc}")
    print(f"Zapisano w: {sciezka}")


# ==========================================
# GLOWNA PETLA PROGRAMU
# ==========================================

def main():

    FOLDER_ZAMOWIENIA.mkdir(
        parents=True,
        exist_ok=True
    )

    # Upewniamy sie, ze baza i licznik istnieja
    inicjalizuj_baze()

    print("========================================")
    print("       GENERATOR ZAMOWIEN XML")
    print("========================================")

    print("Numeracja zamowien: baza SQLite")
    print(f"Folder docelowy: {FOLDER_ZAMOWIENIA}")
    print(f"Interwal generowania: {INTERWAL_GENEROWANIA} sekund")

    print("\nROZKLAD SCENARIUSZY:")

    for nazwa, waga in SCENARIUSZE.items():
        print(f"{nazwa}: {waga}%")

    print("\nAby zatrzymac program, nacisnij CTRL+C.")

    try:

        while True:

            # Rezerwujemy nowy numer bezposrednio w bazie
            zamowienie_id = zarezerwuj_numer_zamowienia()

            generuj_zamowienie(zamowienie_id)

            time.sleep(INTERWAL_GENEROWANIA)

    except KeyboardInterrupt:

        print("\nGenerator zostal zatrzymany.")


# ==========================================
# START PROGRAMU
# ==========================================

if __name__ == "__main__":
    main()
