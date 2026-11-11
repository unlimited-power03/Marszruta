
from pathlib import Path

from database import (
    inicjalizuj_baze,
    pobierz_zamowienia_do_przekazania,
    oznacz_zamowienie_przekazane
)


# ==========================================
# KONFIGURACJA PROJEKTU
# ==========================================

KATALOG_PROJEKTU = Path(__file__).resolve().parent

FOLDER_POPRAWNE = (
    KATALOG_PROJEKTU / "zamowienia" / "poprawne"
)

FOLDER_PRODUKCJA = (
    KATALOG_PROJEKTU / "produkcja" / "kolejki"
)


# ==========================================
# KONFIGURACJA MARSZRUT
# ==========================================

MARSZRUTY = {
    "MTB": "MTB",
    "Miejski": "Miejski",
    "Szosowy": "Szosowy"
}


# ==========================================
# PRZYGOTOWANIE FOLDEROW
# ==========================================

def przygotuj_kolejki():
    """
    Tworzy foldery kolejek produkcyjnych.
    """

    for folder in MARSZRUTY.values():

        sciezka = FOLDER_PRODUKCJA / folder

        sciezka.mkdir(
            parents=True,
            exist_ok=True
        )


# ==========================================
# ODCZYT SCIEZKI PLIKU Z BAZY
# ==========================================

def pobierz_sciezke_zrodlowa(zamowienie):
    """
    Odczytuje sciezke XML zapisana w bazie.

    Obsluguje zarowno pelne sciezki, jak i starsze
    wpisy zawierajace tylko nazwe pliku.
    """

    zapisana_sciezka = zamowienie["plik_xml"]

    if not zapisana_sciezka:
        return None

    sciezka = Path(zapisana_sciezka)

    if not sciezka.is_absolute():
        sciezka_projektu = KATALOG_PROJEKTU / sciezka

        if sciezka_projektu.exists():
            return sciezka_projektu

        # Zgodnosc ze starszymi wpisami w bazie
        sciezka_poprawne = FOLDER_POPRAWNE / sciezka.name

        if sciezka_poprawne.exists():
            return sciezka_poprawne

        return sciezka_projektu

    return sciezka


# ==========================================
# PRZEKAZANIE ZAMOWIENIA DO PRODUKCJI
# ==========================================

def skieruj_zamowienie(zamowienie):
    """
    Przenosi zamowienie do odpowiedniej kolejki
    produkcyjnej i aktualizuje jego status w SQLite.
    """

    numer = zamowienie["id"]
    typ = zamowienie["typ"]

    print("\n----------------------------------------")
    print(f"ZAMOWIENIE: {numer}")
    print(f"TYP ROWERU: {typ}")

    # --------------------------------------
    # 1. WYBOR MARSZRUTY
    # --------------------------------------

    if typ not in MARSZRUTY:

        print(
            f"[BLAD] Brak marszruty dla typu: {typ}"
        )

        return "BLAD"

    nazwa_kolejki = MARSZRUTY[typ]

    folder_docelowy = (
        FOLDER_PRODUKCJA / nazwa_kolejki
    )

    folder_docelowy.mkdir(
        parents=True,
        exist_ok=True
    )

    sciezka_docelowa = (
        folder_docelowy / f"{numer}.xml"
    )

    # --------------------------------------
    # 2. USTALENIE PLIKU ZRODLOWEGO
    # --------------------------------------

    sciezka_zrodlowa = pobierz_sciezke_zrodlowa(
        zamowienie
    )

    # --------------------------------------
    # 3. ODZYSKIWANIE PO PRZERWANIU ROUTINGU
    # --------------------------------------

    if sciezka_docelowa.exists():

        if sciezka_zrodlowa is not None and sciezka_zrodlowa.exists():

            if sciezka_zrodlowa.resolve() == sciezka_docelowa.resolve():

                pass

            elif sciezka_zrodlowa.read_bytes() == sciezka_docelowa.read_bytes():

                # Plik zostal juz przeniesiony lub skopiowany
                # wczesniej, ale zrodlo nadal istnieje.
                sciezka_zrodlowa.unlink()

            else:

                print(
                    "[BLAD] Plik zrodlowy i docelowy istnieja, "
                    "ale ich zawartosc jest rozna."
                )

                return "BLAD"

        print(
            "[ODZYSKIWANIE] Plik znajduje sie juz w kolejce."
        )

    else:

        # ----------------------------------
        # 4. SPRAWDZENIE PLIKU ZRODLOWEGO
        # ----------------------------------

        if sciezka_zrodlowa is None or not sciezka_zrodlowa.exists():

            print(
                "[BLAD] Nie znaleziono pliku XML "
                "w folderze zrodlowym ani w kolejce."
            )

            return "BLAD"

        # ----------------------------------
        # 5. PRZENIESIENIE PLIKU
        # ----------------------------------

        try:

            sciezka_zrodlowa.replace(
                sciezka_docelowa
            )

        except OSError as blad:

            print(
                f"[BLAD PRZENOSZENIA] {blad}"
            )

            return "BLAD"

        print(
            f"PRZENIESIONO: {sciezka_docelowa}"
        )

    # --------------------------------------
    # 6. AKTUALIZACJA BAZY DANYCH
    # --------------------------------------

    try:

        zaktualizowano = oznacz_zamowienie_przekazane(
            zamowienie_id=numer,
            nowy_plik_xml=str(sciezka_docelowa.resolve())
        )

        if not zaktualizowano:

            print(
                "[BLAD] Plik znajduje sie w kolejce, "
                "ale nie udalo sie zaktualizowac statusu w bazie."
            )

            return "BLAD"

    except Exception as blad:

        print(
            f"[BLAD AKTUALIZACJI BAZY] {blad}"
        )

        return "BLAD"

    print(f"MARSZRUTA: {nazwa_kolejki}")
    print("STATUS: PRZEKAZANO DO PRODUKCJI")

    return "SKIEROWANO"


# ==========================================
# PRZETWARZANIE ZAMOWIEN OCZEKUJACYCH
# ==========================================

def przetworz_zamowienia():

    inicjalizuj_baze()
    przygotuj_kolejki()

    print("\n========================================")
    print("       SYSTEM CYFROWEGO ROUTINGU")
    print("========================================")

    # Pobieramy tylko zamowienia oczekujace
    # na przekazanie do produkcji.
    zamowienia = pobierz_zamowienia_do_przekazania()

    if not zamowienia:

        print("\nBrak zamowien oczekujacych na routing.")

        pokaz_stan_kolejek()

        return

    skierowane = 0
    bledy = 0

    print(
        f"\nZamowienia oczekujace na przekazanie: "
        f"{len(zamowienia)}"
    )

    for zamowienie in zamowienia:

        wynik = skieruj_zamowienie(zamowienie)

        if wynik == "SKIEROWANO":
            skierowane += 1

        else:
            bledy += 1

    # --------------------------------------
    # RAPORT ROUTINGU
    # --------------------------------------

    print("\n========================================")
    print("          RAPORT ROUTINGU")
    print("========================================")

    print(f"Oczekujace zamowienia: {len(zamowienia)}")
    print(f"Przekazane do produkcji: {skierowane}")
    print(f"Bledy routingu: {bledy}")

    pokaz_stan_kolejek()

    print("\nZakonczono routing zamowien.")
    print("========================================")


# ==========================================
# STAN KOLEJEK PRODUKCYJNYCH
# ==========================================

def pokaz_stan_kolejek():

    print("\nSTAN KOLEJEK PRODUKCYJNYCH:")

    for typ in MARSZRUTY.values():

        folder = FOLDER_PRODUKCJA / typ

        liczba = len(
            list(folder.glob("*.xml"))
        )

        print(f"{typ}: {liczba} zamowien")


# ==========================================
# START PROGRAMU
# ==========================================

if __name__ == "__main__":

    przetworz_zamowienia()
