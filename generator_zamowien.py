
import os
import time
import random
from pathlib import Path
from xml.dom.minidom import Document


# ==========================================
# KONFIGURACJA PROJEKTU
# ==========================================

KATALOG_PROJEKTU = Path(__file__).resolve().parent

FOLDER_ZAMOWIENIA = KATALOG_PROJEKTU / "zamowienia"


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
# GENEROWANIE ZAMOWIENIA XML
# ==========================================

def generuj_zamowienie(numer):

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

    # Tworzenie dokumentu DOM
    doc = Document()

    zamowienie = doc.createElement("zamowienie")
    doc.appendChild(zamowienie)

    # Numer zamowienia
    id_element = doc.createElement("id")
    id_element.appendChild(
        doc.createTextNode(f"ZAM-{numer:04d}")
    )
    zamowienie.appendChild(id_element)

    # Dane klienta
    klient = doc.createElement("klient")
    zamowienie.appendChild(klient)

    imie_element = doc.createElement("imie")
    imie_element.appendChild(doc.createTextNode(imie))
    klient.appendChild(imie_element)

    nazwisko_element = doc.createElement("nazwisko")
    nazwisko_element.appendChild(doc.createTextNode(nazwisko))
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
    rozmiar_element.appendChild(doc.createTextNode(rozmiar))
    produkt.appendChild(rozmiar_element)

    # Ilosc zamowionych rowerow
    ilosc_element = doc.createElement("ilosc")
    ilosc_element.appendChild(doc.createTextNode(str(ilosc)))
    zamowienie.appendChild(ilosc_element)

    # Zapis dokumentu XML
    nazwa_pliku = f"ZAM-{numer:04d}.xml"
    sciezka = FOLDER_ZAMOWIENIA / nazwa_pliku

    with open(sciezka, "w", encoding="utf-8") as plik:
        doc.writexml(
            plik,
            indent="  ",
            addindent="  ",
            newl="\n"
        )

    print("\n================================")
    print(f"UTWORZONO: {nazwa_pliku}")
    print("================================")
    print(f"Klient: {imie} {nazwisko}")
    print(f"Model: {model}")
    print(f"Typ: {typ}")
    print(f"Rozmiar ramy: {rozmiar}")
    print(f"Ilosc: {ilosc}")
    print(f"Zapisano w: {sciezka}")


# ==========================================
# USTALANIE KOLEJNEGO NUMERU ZAMOWIENIA
# ==========================================

def pobierz_nastepny_numer():

    FOLDER_ZAMOWIENIA.mkdir(
        parents=True,
        exist_ok=True
    )

    najwyzszy_numer = 0

    for plik in os.listdir(FOLDER_ZAMOWIENIA):

        if plik.startswith("ZAM-") and plik.endswith(".xml"):

            try:
                numer = int(plik[4:-4])

                if numer > najwyzszy_numer:
                    najwyzszy_numer = numer

            except ValueError:
                continue

    return najwyzszy_numer + 1


# ==========================================
# GLOWNA PETLA PROGRAMU
# ==========================================

def main():

    # Automatyczne tworzenie folderu zamowien
    FOLDER_ZAMOWIENIA.mkdir(
        parents=True,
        exist_ok=True
    )

    # Ustalenie kolejnego numeru
    numer = pobierz_nastepny_numer()

    print("====================================")
    print("       GENERATOR ZAMOWIEN XML")
    print("====================================")

    print(f"Nastepny numer zamowienia: {numer}")
    print("Nowe zamowienie co 60 sekund.")
    print("Aby zatrzymac program, nacisnij CTRL+C.")

    try:
        while True:

            generuj_zamowienie(numer)

            numer += 1

            time.sleep(60)

    except KeyboardInterrupt:
        print("\nGenerator zostal zatrzymany.")


# ==========================================
# START PROGRAMU
# ==========================================

if __name__ == "__main__":
    main()
