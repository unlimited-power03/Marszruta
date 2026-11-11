import heapq
import random

from pathlib import Path
from collections import deque
from datetime import datetime

from database import (
    inicjalizuj_baze,
    polacz,
    dodaj_operacje,
    ustaw_status_roweru,
    zakoncz_zamowienie,
    pobierz_zamowienia_do_archiwizacji,
    oznacz_zamowienie_zarchiwizowane,
    oznacz_blad_archiwizacji
)


# =====================================================
# KONFIGURACJA STANOWISK PRODUKCYJNYCH
# =====================================================

STANOWISKA = {
    "Kompletacja": {
        "zasoby": 2,
        "czas_min": 8,
        "czas_max": 12
    },
    "Cięcie i obróbka rur": {
        "zasoby": 2,
        "czas_min": 10,
        "czas_max": 16
    },
    "Spawanie ramy": {
        "zasoby": 1,
        "czas_min": 15,
        "czas_max": 22
    },
    "Szlifowanie": {
        "zasoby": 2,
        "czas_min": 8,
        "czas_max": 12
    },
    "Lakiernia": {
        "zasoby": 2,
        "czas_min": 20,
        "czas_max": 30
    },
    "Montaż końcowy": {
        "zasoby": 3,
        "czas_min": 20,
        "czas_max": 30
    },
    "Kontrola jakości": {
        "zasoby": 1,
        "czas_min": 8,
        "czas_max": 12
    },
    "Pakowanie i wysyłka": {
        "zasoby": 2,
        "czas_min": 5,
        "czas_max": 8
    },
    "Poprawki": {
        "zasoby": 2,
        "czas_min": 8,
        "czas_max": 18
    }
}


# =====================================================
# MARSZRUTA PRODUKCYJNA
# =====================================================

MARSZRUTA = [
    "Kompletacja",
    "Cięcie i obróbka rur",
    "Spawanie ramy",
    "Szlifowanie",
    "Lakiernia",
    "Montaż końcowy",
    "Kontrola jakości",
    "Pakowanie i wysyłka"
]


# =====================================================
# KONFIGURACJA KONTROLI JAKOŚCI
# =====================================================

PRAWDOPODOBIENSTWO_USTERKI = 0.10
MAKSYMALNA_LICZBA_POPRAWEK = 2

USTERKI = {
    "HAMULCE": {
        "opis": "Nieprawidłowe działanie układu hamulcowego"
    },
    "NAPED": {
        "opis": "Nieprawidłowa praca układu napędowego"
    },
    "LUZY": {
        "opis": "Wykryto luzy w połączeniach montażowych"
    }
}


# =====================================================
# POBIERANIE OCZEKUJĄCYCH ROWERÓW Z BAZY
# =====================================================


def pobierz_oczekujace_rowery():
    """
    Pobiera rowery z zamowien przekazanych
    przez router i oczekujacych na produkcje.
    """

    with polacz() as conn:
        wynik = conn.execute("""
            SELECT
                r.id AS rower_id,
                r.zamowienie_id,
                r.numer_sztuki,
                r.liczba_poprawek,
                r.ostatnia_usterka,
                z.typ,
                z.model,
                z.rozmiar
            FROM rowery r
            JOIN zamowienia z
                ON r.zamowienie_id = z.id
            WHERE r.status = 'OCZEKUJE'
              AND z.status = 'OCZEKUJE'
              AND z.status_przekazania = 'PRZEKAZANE'
            ORDER BY z.id, r.numer_sztuki
        """).fetchall()

    return wynik


# =====================================================
# ARCHIWIZACJA ZAKONCZONYCH ZAMOWIEN
# =====================================================

KATALOG_PRODUKCJI = Path(__file__).resolve().parent / "produkcja"

FOLDERY_ARCHIWIZACJI = {
    "ZREALIZOWANE": "zrealizowane",
    "ODRZUCONE": "odrzucone",
    "CZESCIOWO_ZREALIZOWANE": "czesciowo_zrealizowane"
}

DOZWOLONE_TYPY = {
    "MTB",
    "Szosowy",
    "Miejski"
}


def archiwizuj_zamowienie(zamowienie):
    """
    Przenosi oryginalny plik XML do archiwum odpowiedniego
    dla wyniku produkcji.

    Operacja jest odporna na ponowne uruchomienie:
    - nie nadpisuje istniejących plików,
    - rozpoznaje plik przeniesiony przed awarią programu,
    - aktualizuje ścieżkę w bazie dopiero po przeniesieniu.
    """

    zamowienie_id = zamowienie["id"]
    status = zamowienie["status"]
    typ = zamowienie["typ"]
    sciezka_zrodlowa = Path(zamowienie["plik_xml"])

    try:
        if status not in FOLDERY_ARCHIWIZACJI:
            raise ValueError(
                f"Nieprawidłowy status zamówienia: {status}"
            )

        if typ not in DOZWOLONE_TYPY:
            raise ValueError(
                f"Nieobsługiwany typ roweru: {typ}"
            )

        if not sciezka_zrodlowa.is_absolute():
            sciezka_zrodlowa = (
                Path(__file__).resolve().parent / sciezka_zrodlowa
            )

        folder_docelowy = (
            KATALOG_PRODUKCJI
            / FOLDERY_ARCHIWIZACJI[status]
            / typ
        )

        folder_docelowy.mkdir(
            parents=True,
            exist_ok=True
        )

        sciezka_docelowa = (
            folder_docelowy / f"{zamowienie_id}.xml"
        )

        # Przypadek 1: plik znajduje się już w archiwum.
        # Możliwe, że program został przerwany po przeniesieniu,
        # ale przed aktualizacją bazy danych.
        if sciezka_docelowa.exists():

            # Jeśli źródło i cel to dokładnie ten sam plik,
            # wystarczy potwierdzić archiwizację.
            if (
                sciezka_zrodlowa.resolve()
                == sciezka_docelowa.resolve()
            ):
                pass

            # Jeśli oba pliki istnieją, sprawdzamy ich zawartość.
            elif sciezka_zrodlowa.exists():

                if (
                    sciezka_zrodlowa.read_bytes()
                    == sciezka_docelowa.read_bytes()
                ):
                    # Identyczna kopia została już przeniesiona.
                    sciezka_zrodlowa.unlink()
                else:
                    raise FileExistsError(
                        "W archiwum istnieje plik o tym samym ID, "
                        "ale jego zawartość jest inna."
                    )

            # Źródło nie istnieje, ale cel istnieje.
            # To poprawny przypadek odzyskiwania po awarii.

        else:
            # Przypadek 2: plik znajduje się jeszcze w kolejce.
            if not sciezka_zrodlowa.is_file():
                raise FileNotFoundError(
                    f"Nie znaleziono pliku XML: {sciezka_zrodlowa}"
                )

            # rename nie nadpisuje istniejącego pliku docelowego
            # na systemie Windows.
            sciezka_zrodlowa.rename(sciezka_docelowa)

        # Dopiero po poprawnym przeniesieniu aktualizujemy bazę.
        aktualizacja = oznacz_zamowienie_zarchiwizowane(
            zamowienie_id,
            sciezka_docelowa
        )

        if not aktualizacja:
            raise RuntimeError(
                "Nie udało się potwierdzić archiwizacji w bazie."
            )

        print(
            f"[ARCHIWIZACJA OK] {zamowienie_id} | "
            f"{status} | {typ} | "
            f"{sciezka_docelowa}"
        )

        return True

    except Exception as blad:

        komunikat = (
            f"Błąd archiwizacji zamówienia "
            f"{zamowienie_id}: {blad}"
        )

        print(f"[ARCHIWIZACJA BŁĄD] {komunikat}")

        try:
            oznacz_blad_archiwizacji(
                zamowienie_id,
                komunikat
            )
        except Exception as blad_bazy:
            print(
                "[BŁĄD BAZY] Nie udało się zapisać "
                f"błędu archiwizacji: {blad_bazy}"
            )

        return False


def archiwizuj_oczekujace_zamowienia():
    """
    Przetwarza wszystkie zamówienia oczekujące
    na archiwizację lub wymagające ponowienia.
    """

    zamowienia = pobierz_zamowienia_do_archiwizacji()

    if not zamowienia:
        return

    print(
        f"\n[ARCHIWIZACJA] "
        f"Zamówienia do przetworzenia: {len(zamowienia)}"
    )

    liczba_sukcesow = 0
    liczba_bledow = 0

    for zamowienie in zamowienia:
        if archiwizuj_zamowienie(zamowienie):
            liczba_sukcesow += 1
        else:
            liczba_bledow += 1

    print(
        f"[ARCHIWIZACJA] Zakończono. "
        f"Sukcesy: {liczba_sukcesow}, "
        f"Błędy: {liczba_bledow}\n"
    )


# =====================================================
# AKTUALIZACJA INFORMACJI O ZAMÓWIENIU
# =====================================================

def rozpocznij_zamowienie(zamowienie_id):
    with polacz() as conn:
        conn.execute("""
            UPDATE zamowienia
            SET status = 'W_TRAKCIE',
                data_startu = ?
            WHERE id = ?
              AND status = 'OCZEKUJE'
        """, (
            datetime.now().isoformat(timespec="seconds"),
            zamowienie_id
        ))


def ustaw_czas_startu_roweru(rower_id, czas):
    with polacz() as conn:
        conn.execute("""
            UPDATE rowery
            SET czas_startu_min = ?
            WHERE id = ?
        """, (czas, rower_id))


def ustaw_czas_zakonczenia_roweru(rower_id, czas):
    with polacz() as conn:
        conn.execute("""
            UPDATE rowery
            SET czas_zakonczenia_min = ?
            WHERE id = ?
        """, (czas, rower_id))


def zapisz_dane_kontroli(rower_id, liczba_poprawek, ostatnia_usterka):
    """
    Zapisuje licznik napraw i ostatnią wykrytą usterkę roweru.
    """
    with polacz() as conn:
        conn.execute("""
            UPDATE rowery
            SET liczba_poprawek = ?,
                ostatnia_usterka = ?
            WHERE id = ?
        """, (
            liczba_poprawek,
            ostatnia_usterka,
            rower_id
        ))


def zwieksz_liczbe_poprawek_zamowienia(zamowienie_id):
    """
    Zwiększa łączną liczbę napraw w zamówieniu.
    """
    with polacz() as conn:
        conn.execute("""
            UPDATE zamowienia
            SET liczba_poprawek = COALESCE(liczba_poprawek, 0) + 1
            WHERE id = ?
        """, (zamowienie_id,))


# =====================================================
# SILNIK SYMULACJI ZDARZENIOWEJ
# =====================================================

class SymulacjaProdukcji:

    def __init__(self, rowery):
        self.rowery = rowery
        self.zegar = 0.0

        self.kolejki = {
            nazwa: deque()
            for nazwa in STANOWISKA
        }

        self.zajete_zasoby = {
            nazwa: 0
            for nazwa in STANOWISKA
        }

        self.zdarzenia = []
        self.licznik_zdarzen = 0

        # Zbiór rowerów, które osiągnęły stan końcowy:
        # GOTOWY albo ODRZUCONY.
        self.zakonczone_rowery = set()
        self.gotowe_rowery = set()
        self.odrzucone_rowery = set()

        self.czas_zakonczenia_zamowien = {}
        self.zamowienia = {}

        self.liczba_kontroli = 0
        self.liczba_wykrytych_usterek = 0
        self.liczba_wykonanych_poprawek = 0

        self.statystyki_stanowisk = {
            nazwa: {
                "operacje": 0,
                "czas_pracy": 0.0,
                "maksymalna_kolejka": 0
            }
            for nazwa in STANOWISKA
        }

    # -------------------------------------------------

    def przygotuj(self):
        for rower in self.rowery:
            zamowienie_id = rower["zamowienie_id"]

            self.zamowienia.setdefault(
                zamowienie_id,
                []
            ).append(rower["rower_id"])

            dane_roweru = {
                "rower_id": rower["rower_id"],
                "zamowienie_id": zamowienie_id,
                "numer_sztuki": rower["numer_sztuki"],
                "typ": rower["typ"],
                "model": rower["model"],
                "rozmiar": rower["rozmiar"],
                "etap": 0,
                "liczba_poprawek": rower["liczba_poprawek"] or 0,
                "ostatnia_usterka": rower["ostatnia_usterka"]
            }

            self.kolejki[MARSZRUTA[0]].append(dane_roweru)

            ustaw_czas_startu_roweru(
                rower["rower_id"],
                0
            )

            rozpocznij_zamowienie(zamowienie_id)

        print(
            f"\nPrzygotowano {len(self.rowery)} "
            f"rowerów do produkcji."
        )

    # -------------------------------------------------

    def dodaj_zdarzenie(
        self,
        czas,
        rower,
        stanowisko,
        czas_startu,
        czas_trwania
    ):
        self.licznik_zdarzen += 1

        heapq.heappush(
            self.zdarzenia,
            (
                czas,
                self.licznik_zdarzen,
                rower,
                stanowisko,
                czas_startu,
                czas_trwania
            )
        )

    # -------------------------------------------------

    def uruchom_stanowiska(self):
        for nazwa, konfiguracja in STANOWISKA.items():
            kolejka = self.kolejki[nazwa]

            while (
                kolejka
                and self.zajete_zasoby[nazwa]
                < konfiguracja["zasoby"]
            ):
                rower = kolejka.popleft()

                czas_trwania = random.uniform(
                    konfiguracja["czas_min"],
                    konfiguracja["czas_max"]
                )

                if nazwa == "Montaż końcowy":
                    if rower["typ"] == "MTB":
                        czas_trwania *= 1.10
                    elif rower["typ"] == "Miejski":
                        czas_trwania *= 1.05

                czas_zakonczenia = self.zegar + czas_trwania

                self.zajete_zasoby[nazwa] += 1

                self.dodaj_zdarzenie(
                    czas_zakonczenia,
                    rower,
                    nazwa,
                    self.zegar,
                    czas_trwania
                )

            # Pomiar kolejki po przydzieleniu dostępnych zasobów.
            self.statystyki_stanowisk[nazwa][
                "maksymalna_kolejka"
            ] = max(
                self.statystyki_stanowisk[nazwa][
                    "maksymalna_kolejka"
                ],
                len(kolejka)
            )

    # -------------------------------------------------

    def przeprowadz_kontrole_jakosci(self, rower):
        """
        Losuje wynik kontroli jakości.
        Zwraca słownik z wynikiem oraz opisem ewentualnej usterki.
        """
        if random.random() >= PRAWDOPODOBIENSTWO_USTERKI:
            return {
                "wynik": "POZYTYWNY",
                "usterka": None,
                "opis": "Produkt spełnia wymagania jakościowe."
            }

        kod_usterki = random.choice(list(USTERKI.keys()))

        return {
            "wynik": "NEGATYWNY",
            "usterka": kod_usterki,
            "opis": USTERKI[kod_usterki]["opis"]
        }

    # -------------------------------------------------

    def zapisz_operacje(
        self,
        rower,
        stanowisko,
        czas_startu,
        czas_zakonczenia,
        status,
        opis
    ):
        dodaj_operacje(
            zamowienie_id=rower["zamowienie_id"],
            numer_sztuki=rower["numer_sztuki"],
            stanowisko=stanowisko,
            czas_startu=czas_startu,
            czas_zakonczenia=czas_zakonczenia,
            status=status,
            opis=opis
        )

    # -------------------------------------------------

    def zakoncz_operacje(
        self,
        rower,
        stanowisko,
        czas_startu,
        czas_trwania
    ):
        self.zajete_zasoby[stanowisko] -= 1
        czas_zakonczenia = self.zegar

        opis = (
            f'{rower["model"]} | '
            f'{rower["typ"]} | '
            f'Rozmiar {rower["rozmiar"]}'
        )

        # Każda operacja, również kontrola i poprawki,
        # jest zapisywana w tabeli operacje.

        if stanowisko == "Kontrola jakości":
            self.liczba_kontroli += 1
            wynik_kontroli = self.przeprowadz_kontrole_jakosci(rower)

            if wynik_kontroli["wynik"] == "POZYTYWNY":
                opis += (
                    " | WYNIK KONTROLI: POZYTYWNY"
                    f" | {wynik_kontroli['opis']}"
                )

                self.zapisz_operacje(
                    rower,
                    stanowisko,
                    czas_startu,
                    czas_zakonczenia,
                    "ZAKONCZONA",
                    opis
                )

                self.statystyki_stanowisk[stanowisko][
                    "operacje"
                ] += 1
                self.statystyki_stanowisk[stanowisko][
                    "czas_pracy"
                ] += czas_trwania

                print(
                    f"[{self.zegar:7.2f} min] "
                    f"{rower['zamowienie_id']} / "
                    f"szt. {rower['numer_sztuki']} | "
                    "[KONTROLA POZYTYWNA] "
                    "Przekazano do pakowania."
                )

                rower["etap"] = MARSZRUTA.index(
                    "Pakowanie i wysyłka"
                )
                ustaw_status_roweru(
                    rower["zamowienie_id"],
                    rower["numer_sztuki"],
                    "OCZEKUJE",
                    "Pakowanie i wysyłka"
                )
                self.kolejki["Pakowanie i wysyłka"].append(rower)
                return

            # Kontrola negatywna.
            self.liczba_wykrytych_usterek += 1
            rower["ostatnia_usterka"] = wynik_kontroli["opis"]

            opis += (
                " | WYNIK KONTROLI: NEGATYWNY"
                f" | Usterka: {wynik_kontroli['opis']}"
            )

            self.zapisz_operacje(
                rower,
                stanowisko,
                czas_startu,
                czas_zakonczenia,
                "ZAKONCZONA",
                opis
            )

            self.statystyki_stanowisk[stanowisko][
                "operacje"
            ] += 1
            self.statystyki_stanowisk[stanowisko][
                "czas_pracy"
            ] += czas_trwania

            print(
                f"[{self.zegar:7.2f} min] "
                f"{rower['zamowienie_id']} / "
                f"szt. {rower['numer_sztuki']} | "
                f"[KONTROLA NEGATYWNA] "
                f"{wynik_kontroli['opis']}"
            )

            if rower["liczba_poprawek"] < MAKSYMALNA_LICZBA_POPRAWEK:
                rower["liczba_poprawek"] += 1

                self.liczba_wykonanych_poprawek += 1

                zapisz_dane_kontroli(
                    rower["rower_id"],
                    rower["liczba_poprawek"],
                    rower["ostatnia_usterka"]
                )
                zwieksz_liczbe_poprawek_zamowienia(
                    rower["zamowienie_id"]
                )

                ustaw_status_roweru(
                    rower["zamowienie_id"],
                    rower["numer_sztuki"],
                    "W_NAPRAWIE",
                    "Poprawki"
                )

                print(
                    f"    [POPRAWKI] "
                    f"Próba {rower['liczba_poprawek']}/"
                    f"{MAKSYMALNA_LICZBA_POPRAWEK}. "
                    "Rower skierowany do naprawy."
                )

                self.kolejki["Poprawki"].append(rower)

            else:
                self.odrzuc_rower(rower)

            return

        # Zakończenie stanowiska Poprawki:
        # po naprawie rower wraca do kontroli jakości.
        if stanowisko == "Poprawki":
            self.zapisz_operacje(
                rower,
                stanowisko,
                czas_startu,
                czas_zakonczenia,
                "ZAKONCZONA",
                (
                    f'{rower["model"]} | '
                    f'{rower["typ"]} | '
                    f'Naprawa nr {rower["liczba_poprawek"]} | '
                    f'Usterka: {rower["ostatnia_usterka"]}'
                )
            )

            self.statystyki_stanowisk[stanowisko][
                "operacje"
            ] += 1
            self.statystyki_stanowisk[stanowisko][
                "czas_pracy"
            ] += czas_trwania

            print(
                f"[{self.zegar:7.2f} min] "
                f"{rower['zamowienie_id']} / "
                f"szt. {rower['numer_sztuki']} | "
                "[NAPRAWA ZAKOŃCZONA] "
                "Powrót do kontroli jakości."
            )

            ustaw_status_roweru(
                rower["zamowienie_id"],
                rower["numer_sztuki"],
                "OCZEKUJE",
                "Kontrola jakości"
            )
            self.kolejki["Kontrola jakości"].append(rower)
            return

        # Standardowe stanowisko produkcyjne.
        self.zapisz_operacje(
            rower,
            stanowisko,
            czas_startu,
            czas_zakonczenia,
            "ZAKONCZONA",
            opis
        )

        self.statystyki_stanowisk[stanowisko][
            "operacje"
        ] += 1
        self.statystyki_stanowisk[stanowisko][
            "czas_pracy"
        ] += czas_trwania

        print(
            f"[{self.zegar:7.2f} min] "
            f"{rower['zamowienie_id']} / "
            f"szt. {rower['numer_sztuki']} | "
            f"{stanowisko} - zakończono"
        )

        nastepny_etap = rower["etap"] + 1

        if nastepny_etap >= len(MARSZRUTA):
            self.zakoncz_rower(rower)
            return

        rower["etap"] = nastepny_etap
        nastepne_stanowisko = MARSZRUTA[nastepny_etap]

        ustaw_status_roweru(
            rower["zamowienie_id"],
            rower["numer_sztuki"],
            "OCZEKUJE",
            nastepne_stanowisko
        )

        self.kolejki[nastepne_stanowisko].append(rower)

    # -------------------------------------------------

    def zakoncz_rower(self, rower):
        """
        Oznacza rower jako gotowy po przejściu całej marszruty.
        """
        rower_id = rower["rower_id"]

        self.zakonczone_rowery.add(rower_id)
        self.gotowe_rowery.add(rower_id)

        ustaw_status_roweru(
            rower["zamowienie_id"],
            rower["numer_sztuki"],
            "GOTOWY",
            None
        )

        ustaw_czas_zakonczenia_roweru(
            rower_id,
            self.zegar
        )

        print(
            f"    [GOTOWY] "
            f"{rower['zamowienie_id']} "
            f"- rower nr {rower['numer_sztuki']}"
        )

        self.sprawdz_zamowienie(rower["zamowienie_id"])

    # -------------------------------------------------

    def odrzuc_rower(self, rower):
        """
        Odrzuca rower po wykorzystaniu limitu napraw
        i kolejnej negatywnej kontroli jakości.
        """
        rower_id = rower["rower_id"]

        zapisz_dane_kontroli(
            rower_id,
            rower["liczba_poprawek"],
            rower["ostatnia_usterka"]
        )

        self.zakonczone_rowery.add(rower_id)
        self.odrzucone_rowery.add(rower_id)

        ustaw_status_roweru(
            rower["zamowienie_id"],
            rower["numer_sztuki"],
            "ODRZUCONY",
            None
        )

        ustaw_czas_zakonczenia_roweru(
            rower_id,
            self.zegar
        )

        print(
            f"    [ODRZUCONY] "
            f"{rower['zamowienie_id']} "
            f"- rower nr {rower['numer_sztuki']}. "
            f"Przyczyna: {rower['ostatnia_usterka']}"
        )

        self.sprawdz_zamowienie(rower["zamowienie_id"])

    # -------------------------------------------------

    def sprawdz_zamowienie(self, zamowienie_id):
        """
        Kończy zamówienie dopiero wtedy, gdy każdy rower
        osiągnie stan GOTOWY albo ODRZUCONY.
        """
        rowery_zamowienia = self.zamowienia[zamowienie_id]

        liczba_zakonczonych = sum(
            1
            for rower_id in rowery_zamowienia
            if rower_id in self.zakonczone_rowery
        )

        if liczba_zakonczonych != len(rowery_zamowienia):
            return

        zakonczone = self.zegar

        self.czas_zakonczenia_zamowien[
            zamowienie_id
        ] = zakonczone

        with polacz() as conn:
            wynik = conn.execute("""
                SELECT
                    r.status,
                    r.czas_startu_min
                FROM rowery r
                WHERE r.zamowienie_id = ?
            """, (zamowienie_id,)).fetchall()

        liczba_gotowych = sum(
            1 for row in wynik
            if row["status"] == "GOTOWY"
        )
        liczba_odrzuconych = sum(
            1 for row in wynik
            if row["status"] == "ODRZUCONY"
        )

        if liczba_odrzuconych == 0:
            status_zamowienia = "ZREALIZOWANE"
        elif liczba_gotowych == 0:
            status_zamowienia = "ODRZUCONE"
        else:
            status_zamowienia = "CZESCIOWO_ZREALIZOWANE"

        czasy_startu = [
            row["czas_startu_min"]
            for row in wynik
            if row["czas_startu_min"] is not None
        ]
        czas_startu = min(czasy_startu) if czasy_startu else 0

        zakoncz_zamowienie(
            zamowienie_id,
            zakonczone - czas_startu,
            status_zamowienia
        )

        print(
            f"\n[ZAMÓWIENIE ZAKOŃCZONE] {zamowienie_id} | "
            f"Status: {status_zamowienia} | "
            f"Gotowe: {liczba_gotowych} | "
            f"Odrzucone: {liczba_odrzuconych}\n"
        )

        # Po zakończeniu wszystkich rowerów
        # przenosimy oryginalny XML do archiwum.
        archiwizuj_oczekujace_zamowienia()
    # -------------------------------------------------

    def wykonaj(self):
        self.przygotuj()

        while self.zdarzenia or any(
            self.kolejki[nazwa]
            for nazwa in STANOWISKA
        ):
            self.uruchom_stanowiska()

            if not self.zdarzenia:
                if any(self.kolejki[nazwa] for nazwa in STANOWISKA):
                    print(
                        "\n[OSTRZEŻENIE] Pozostały rowery w kolejkach, "
                        "ale nie ma zaplanowanych zdarzeń."
                    )
                break

            (
                czas,
                _,
                rower,
                stanowisko,
                czas_startu,
                czas_trwania
            ) = heapq.heappop(self.zdarzenia)

            self.zegar = czas

            self.zakoncz_operacje(
                rower,
                stanowisko,
                czas_startu,
                czas_trwania
            )

        print("\n========== KONIEC SYMULACJI ==========")

        print(
            f"Czas symulowanej produkcji: "
            f"{self.zegar:.2f} minut"
        )

        print(
            f"Przygotowane rowery: "
            f"{len(self.rowery)}"
        )

        print(
            f"Gotowe rowery: "
            f"{len(self.gotowe_rowery)}"
        )

        print(
            f"Odrzucone rowery: "
            f"{len(self.odrzucone_rowery)}"
        )

        print(
            f"Zrealizowane zamówienia: "
            f"{len(self.czas_zakonczenia_zamowien)}"
        )

        print("\n========== KONTROLA JAKOŚCI ==========")

        print(f"Liczba kontroli: {self.liczba_kontroli}")
        print(f"Wykryte usterki: {self.liczba_wykrytych_usterek}")
        print(f"Wykonane naprawy: {self.liczba_wykonanych_poprawek}")

        self.pokaz_statystyki()

    # -------------------------------------------------

    def pokaz_statystyki(self):
        print("\n========== STANOWISKA ==========")

        for nazwa, dane in self.statystyki_stanowisk.items():
            print(f"\n{nazwa}")

            print(
                f"  Wykonane operacje: "
                f"{dane['operacje']}"
            )

            print(
                f"  Łączny czas pracy: "
                f"{dane['czas_pracy']:.2f} min"
            )

            print(
                f"  Maksymalna zaobserwowana kolejka: "
                f"{dane['maksymalna_kolejka']}"
            )


# =====================================================
# URUCHOMIENIE PROGRAMU
# =====================================================

def uruchom_symulacje():
    inicjalizuj_baze()

    # Najpierw kończymy archiwizację zamówień
    # pozostałych po poprzednim uruchomieniu.
    archiwizuj_oczekujace_zamowienia()

    # Dopiero potem pobieramy rowery do produkcji.
    rowery = pobierz_oczekujace_rowery()

    if not rowery:
        print(
            "Brak oczekujących rowerów. "
            "Nie ma nic do wyprodukowania."
        )
        return

    print("\n======================================")
    print("       SYMULACJA FABRYKI ROWERÓW")
    print("======================================")

    print(
        f"Liczba rowerów do produkcji: "
        f"{len(rowery)}"
    )

    symulacja = SymulacjaProdukcji(rowery)
    symulacja.wykonaj()


if __name__ == "__main__":
    uruchom_symulacje()
