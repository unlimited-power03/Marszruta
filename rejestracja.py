
from pathlib import Path
from xml.dom import minidom, Node

from database import (
    inicjalizuj_baze,
    zarejestruj_zamowienie
)


# ==========================================
# KONFIGURACJA
# ==========================================

KATALOG_PROJEKTU = Path(__file__).resolve().parent

FOLDER_POPRAWNE = (
    KATALOG_PROJEKTU / "zamowienia" / "poprawne"
)


# ==========================================
# ODCZYT DANYCH XML
# ==========================================

def pobierz_tekst(element, nazwa_tag):
    """
    Pobiera tekst z bezposredniego elementu potomnego.
    """

    znalezione = [
        dziecko
        for dziecko in element.childNodes
        if dziecko.nodeType == Node.ELEMENT_NODE
        and dziecko.tagName == nazwa_tag
    ]

    if len(znalezione) != 1:
        return None

    element_pola = znalezione[0]

    tekst = ""

    for dziecko in element_pola.childNodes:
        if dziecko.nodeType in (
            Node.TEXT_NODE,
            Node.CDATA_SECTION_NODE
        ):
            tekst += dziecko.data

    tekst = tekst.strip()

    return tekst if tekst else None


def odczytaj_zamowienie(sciezka):
    """
    Odczytuje dane zamowienia z pliku XML.
    """

    dokument = minidom.parse(str(sciezka))
    korzen = dokument.documentElement

    if korzen.tagName != "zamowienie":
        raise ValueError("Nieprawidlowy element glowny XML")

    zamowienie_id = pobierz_tekst(korzen, "id")
    ilosc_tekst = pobierz_tekst(korzen, "ilosc")

    # Odczyt sekcji produkt
    produkty = [
        dziecko
        for dziecko in korzen.childNodes
        if dziecko.nodeType == Node.ELEMENT_NODE
        and dziecko.tagName == "produkt"
    ]

    if len(produkty) != 1:
        raise ValueError(
            "Brak elementu <produkt> lub wystepuje on wielokrotnie"
        )

    produkt = produkty[0]

    typ = pobierz_tekst(produkt, "typ")
    model = pobierz_tekst(produkt, "model")
    rozmiar = pobierz_tekst(produkt, "rozmiar_ramy")

    if not all([
        zamowienie_id,
        typ,
        model,
        rozmiar,
        ilosc_tekst
    ]):
        raise ValueError(
            "Brak wymaganych danych zamowienia"
        )

    try:
        ilosc = int(ilosc_tekst)

    except ValueError:
        raise ValueError(
            "Nieprawidlowa ilosc rowerow"
        )

    if ilosc <= 0:
        raise ValueError(
            "Ilosc rowerow musi byc wieksza od zera"
        )

    return {
        "id": zamowienie_id,
        "typ": typ,
        "model": model,
        "rozmiar": rozmiar,
        "ilosc": ilosc
    }


# ==========================================
# REJESTRACJA POJEDYNCZEGO ZAMOWIENIA
# ==========================================

def zarejestruj_plik(sciezka):
    """
    Rejestruje pojedyncze zamowienie w SQLite.

    Plik XML pozostaje w folderze poprawne.
    Jego przeniesieniem zajmie sie router.
    """

    dane = odczytaj_zamowienie(sciezka)

    dodano = zarejestruj_zamowienie(
        zamowienie_id=dane["id"],
        plik_xml=str(sciezka.resolve()),
        typ=dane["typ"],
        model=dane["model"],
        rozmiar=dane["rozmiar"],
        ilosc=dane["ilosc"]
    )

    if dodano:

        print(
            f"[NOWE] {dane['id']} | "
            f"{dane['typ']} | {dane['model']} | "
            f"{dane['ilosc']} szt."
        )

    else:

        print(
            f"[POMINIETO] {dane['id']} "
            f"- zamowienie juz znajduje sie w bazie"
        )

    return dodano


# ==========================================
# REJESTRACJA ZAMOWIEN
# ==========================================

def rejestruj_zamowienia():
    """
    Odczytuje poprawne zamowienia i rejestruje
    je w bazie danych.
    """

    inicjalizuj_baze()

    FOLDER_POPRAWNE.mkdir(
        parents=True,
        exist_ok=True
    )

    pliki = sorted(
        FOLDER_POPRAWNE.glob("*.xml")
    )

    liczba_nowych = 0
    liczba_pominietych = 0
    liczba_bledow = 0

    print("\n========== REJESTRACJA ZAMOWIEN ==========\n")

    if not pliki:

        print("Brak poprawnych zamowien do rejestracji.")

        return

    print(f"Znaleziono plikow: {len(pliki)}")

    for sciezka in pliki:

        try:

            dodano = zarejestruj_plik(sciezka)

            if dodano:
                liczba_nowych += 1

            else:
                liczba_pominietych += 1

        except Exception as blad:

            liczba_bledow += 1

            print(
                f"[BLAD] {sciezka.name}: {blad}"
            )

    # --------------------------------------
    # PODSUMOWANIE
    # --------------------------------------

    print("\n========== PODSUMOWANIE ==========")

    print(f"Nowe zamowienia:       {liczba_nowych}")
    print(f"Pominiete zamowienia:  {liczba_pominietych}")
    print(f"Bledy:                 {liczba_bledow}")

    print("\nPliki XML pozostaja w:")
    print(FOLDER_POPRAWNE)

    print("==================================\n")


# ==========================================
# START PROGRAMU
# ==========================================

if __name__ == "__main__":

    rejestruj_zamowienia()
